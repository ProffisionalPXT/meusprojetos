from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

from gw_automation.regras_veiculo import (
    FROTA_CARRETEIRO,
    aplicar_cap_tara,
    normalizar_tipo_frota,
)
from ocr.parsers_locais import so_digitos


@dataclass
class DadosMotorista:
    """Campos do cadmotorista (prints reais)."""
    categoria: str = "Motorista (Transporte)"
    cpf: str = ""
    nome: str = ""
    apelido: str = ""
    telefone_fixo: str = ""
    telefone_celular: str = ""
    data_nascimento: str = ""
    sexo: str = ""
    cep: str = ""
    endereco: str = ""
    bairro: str = ""
    complemento: str = ""
    cidade: str = ""
    uf: str = ""
    naturalidade: str = ""
    nacionalidade: str = "BRASILEIRO"
    estado_civil: str = ""
    nome_pai: str = ""
    nome_mae: str = ""
    rg: str = ""
    orgao_emissor: str = ""
    cnh: str = ""
    validade_cnh: str = ""
    data_emissao_cnh: str = ""  # dataemissaocnh no GW
    local_emissao_cnh: str = ""  # localemissaocnh
    categoria_cnh: str = ""
    data_primeira_habilitacao: str = ""
    tipo_motorista: str = "Carreteiro"
    placa_veiculo: str = ""
    placa_carreta: str = ""
    fotos: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DadosVeiculo:
    categoria: str = "Veículo Terrestre"
    placa: str = ""
    renavam: str = ""
    chassi: str = ""
    # CRLV "MARCA / MODELO / VERSÃO" -> 3 campos no GW
    marca_modelo_versao: str = ""
    modelo: str = ""
    marca: str = ""
    ano_mod: str = ""
    ano_fab: str = ""
    cor: str = ""
    tipo: str = ""
    tipo_frota: str = FROTA_CARRETEIRO
    cidade: str = ""
    uf: str = ""
    cap_carga: str = ""
    tara: str = ""
    proprietario_nome: str = ""
    # Dono DESTE CRLV (pode diferir entre cavalo e carreta)
    proprietario: Optional["DadosProprietario"] = None
    fotos: List[str] = field(default_factory=list)

    def texto_marca_modelo(self) -> str:
        return (
            (self.marca_modelo_versao or "").strip()
            or (self.marca or "").strip()
            or (self.modelo or "").strip()
        )

    def aplicar_marca_modelo_nos_tres_campos(self) -> None:
        t = self.texto_marca_modelo()
        if not t:
            return
        if not self.marca_modelo_versao:
            self.marca_modelo_versao = t
        if not self.marca:
            self.marca = t
        if not self.modelo:
            self.modelo = t

    def aplicar_regras_tipo(self) -> None:
        if self.tipo:
            self.tipo = self.tipo.strip().upper()
        self.tipo_frota = normalizar_tipo_frota(self.tipo_frota)
        aplicar_cap_tara(self)
        self.aplicar_marca_modelo_nos_tres_campos()

    def sincronizar_cidade_proprietario(self, prop: Optional["DadosProprietario"]) -> None:
        if prop and prop.cidade:
            self.cidade = prop.cidade
            if prop.uf:
                self.uf = prop.uf


@dataclass
class DadosProprietario:
    nome: str = ""
    cpf_cnpj: str = ""
    tipo_doc: str = ""
    rg: str = ""
    inscricao_estadual: str = ""
    cidade: str = ""
    uf: str = ""
    rntrc: str = ""
    fotos: List[str] = field(default_factory=list)

    def aplicar_regras_gw(self) -> None:
        digitos = so_digitos(self.cpf_cnpj)
        if len(digitos) == 11:
            self.tipo_doc = "CPF"
            self.rg = self.rg or "0000000"
        elif len(digitos) == 14:
            self.tipo_doc = "CNPJ"
            self.inscricao_estadual = self.inscricao_estadual or "0000000"


@dataclass
class DadosCaso:
    caso_nome: str
    motorista: DadosMotorista = field(default_factory=DadosMotorista)
    veiculo: Optional[DadosVeiculo] = None
    carreta: Optional[DadosVeiculo] = None
    # 3º CRLV -> Bi-Trem | 4º CRLV -> 3º Reboque (tipo CARRETA no cadastro)
    bitrem: Optional[DadosVeiculo] = None
    tri_reboque: Optional[DadosVeiculo] = None
    proprietario: Optional[DadosProprietario] = None
    # TAC: 1 doc serve p/ todos os props; vários -> tenta casar por nome
    rntrc_tac: str = ""
    tacs: List[Dict[str, Any]] = field(default_factory=list)
    arquivos: List[str] = field(default_factory=list)
    extracoes_gemini: Dict[str, Any] = field(default_factory=dict)
    fonte_ocr: str = ""  # local | gemini | auto | cache
    # Avisos de OCR (baixa confiança) - mostrados na confirmação
    avisos_ocr: List[str] = field(default_factory=list)

    def veiculos_composicao(self) -> List[Tuple[str, Optional[DadosVeiculo]]]:
        """Slots na ordem do GW: Veículo, Carreta, Bi-Trem, 3º Reboque."""
        return [
            ("veiculo", self.veiculo),
            ("carreta", self.carreta),
            ("bitrem", self.bitrem),
            ("tri_reboque", self.tri_reboque),
        ]

    def iter_veiculos(self) -> List[DadosVeiculo]:
        return [v for _, v in self.veiculos_composicao() if v]
