"""
Dados completos do caso GABRIEL — simulando Gemini + prints reais do formulário.
"""
from __future__ import annotations

from ocr.extrair_dados import (
    DadosCaso,
    DadosMotorista,
    DadosProprietario,
    DadosVeiculo,
)
from gw_automation.regras_veiculo import TIPO_TRUCK, FROTA_CARRETEIRO


def dados_gabriel() -> DadosCaso:
    motorista = DadosMotorista(
        categoria="Motorista (Transporte)",
        cpf="10603030432",
        nome="GABRIEL DO NASCIMENTO PEIXOTO",
        data_nascimento="15/08/1998",
        sexo="Masculino",
        cep="53401000",
        endereco="AVENIDA DR CLOVIS COUTINHO",
        bairro="CENTRO",
        complemento="",
        # Cidade de residência / naturalidade: PAULISTA - PE (NÃO Bragança Paulista)
        cidade="PAULISTA",
        uf="PE",
        naturalidade="PAULISTA",
        nacionalidade="BRASILEIRO",
        estado_civil="Solteiro",
        nome_pai="CASSIO DE MACEDO PEIXOTO",
        nome_mae="EDILENE MARIA DO NASCIMENTO",
        rg="9284351",
        orgao_emissor="SDS PE",
        cnh="06783402482",
        validade_cnh="09/09/2031",
        categoria_cnh="AB",
        data_primeira_habilitacao="25/01/2017",
        tipo_motorista="Carreteiro",
        placa_veiculo="HNW6501",
        placa_carreta="",
    )

    # Preenchimento no padrão do print completo (todos os campos do form)
    # No CRLV: campo MARCA/MODELO/VERSÃO → mesmo texto em 3 campos do GW
    mmv = "VW GOL 1.0"
    veiculo = DadosVeiculo(
        categoria="Veículo Terrestre",
        placa="HNW6501",
        renavam="00222527706",
        chassi="9BAA05U2BP043185",
        marca_modelo_versao=mmv,  # do documento
        marca=mmv,                # 1) *Marca (lookup)
        modelo=mmv,               # 2) Modelo
        # 3) marca_rastreador (abaixo cestos) = mesmo texto no fill
        ano_mod="2011",
        ano_fab="2010",
        cor="PRATA",
        tipo=TIPO_TRUCK,
        tipo_frota=FROTA_CARRETEIRO,
        cidade="PAULISTA",
        uf="PE",
        cap_carga="12000",
        tara="12000",
        proprietario_nome="GABRIEL DO NASCIMENTO PEIXOTO",
    )
    veiculo.aplicar_regras_tipo()

    proprietario = DadosProprietario(
        nome="GABRIEL DO NASCIMENTO PEIXOTO",
        cpf_cnpj="10603030432",
        tipo_doc="CPF",
        rg="0000000",
        cidade="PAULISTA",
        uf="PE",
        # RNTRC do TAC que veio no lote (não inventar)
        rntrc="059276500",
    )
    proprietario.aplicar_regras_gw()

    return DadosCaso(
        caso_nome="gabriel",
        motorista=motorista,
        veiculo=veiculo,
        carreta=None,
        proprietario=proprietario,
        rntrc_tac="059276500",
        arquivos=[],
    )
