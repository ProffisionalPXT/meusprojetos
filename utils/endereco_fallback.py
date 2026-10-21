"""
Endereço fallback quando NÃO vem comprovante de residência.

Regra de ouro (pedido operação):
  SEM comprovante -> SEMPRE usar a CIDADE DE NASCIMENTO (naturalidade da CNH).
  Nunca usar cidade do CRLV/proprietário no lugar da naturalidade.

Ex.: nasceu em Arapiraca/AL -> CEP/bairro de Arapiraca-AL.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import re
import unicodedata


@dataclass(frozen=True)
class EnderecoPadrao:
    cidade: str
    uf: str
    cep: str
    endereco: str
    bairro: str
    complemento: str = ""


# CEPs genéricos / centrais por cidade (válidos para o lookup do GW)
# Amplie a lista conforme a operação precisar.
_ENDERECOS: dict[str, EnderecoPadrao] = {
    # PE
    "recife": EnderecoPadrao("RECIFE", "PE", "50010000", "RUA DA AURORA", "BOA VISTA"),
    "paulista": EnderecoPadrao("PAULISTA", "PE", "53401000", "AVENIDA DR CLOVIS COUTINHO", "CENTRO"),
    "olinda": EnderecoPadrao("OLINDA", "PE", "53010000", "AVENIDA GETULIO VARGAS", "BAIRRO NOVO"),
    "jaboatao": EnderecoPadrao("JABOATAO DOS GUARARAPES", "PE", "54010000", "AVENIDA BARRETO DE MENEZES", "PRAZERES"),
    "jaboatao dos guararapes": EnderecoPadrao(
        "JABOATAO DOS GUARARAPES", "PE", "54010000", "AVENIDA BARRETO DE MENEZES", "PRAZERES"
    ),
    "caruaru": EnderecoPadrao("CARUARU", "PE", "55002000", "RUA SAO FRANCISCO", "NOSSA SENHORA DAS DORES"),
    "petrolina": EnderecoPadrao("PETROLINA", "PE", "56304000", "AVENIDA SOUZA FILHO", "CENTRO"),
    # PB
    "joao pessoa": EnderecoPadrao("JOAO PESSOA", "PB", "58010000", "AVENIDA EPITACIO PESSOA", "ESTADOS"),
    "campina grande": EnderecoPadrao("CAMPINA GRANDE", "PB", "58400050", "AVENIDA FLORIANO PEIXOTO", "CENTRO"),
    # RN
    "natal": EnderecoPadrao("NATAL", "RN", "59010000", "AVENIDA RIO BRANCO", "CIDADE ALTA"),
    # AL
    "maceio": EnderecoPadrao("MACEIO", "AL", "57020000", "RUA DO COMERCIO", "CENTRO"),
    "arapiraca": EnderecoPadrao("ARAPIRACA", "AL", "57300005", "RUA DO COMERCIO", "CENTRO"),
    "palmeira dos indios": EnderecoPadrao("PALMEIRA DOS INDIOS", "AL", "57600005", "RUA DO COMERCIO", "CENTRO"),
    "rio largo": EnderecoPadrao("RIO LARGO", "AL", "57100000", "RUA DO COMERCIO", "CENTRO"),
    # SE
    "aracaju": EnderecoPadrao("ARACAJU", "SE", "49010000", "AVENIDA IVO DO PRADO", "CENTRO"),
    "barra dos coqueiros": EnderecoPadrao(
        "BARRA DOS COQUEIROS", "SE", "49140000", "AVENIDA OCEANICA", "CENTRO"
    ),
    "coqueiros": EnderecoPadrao(
        "BARRA DOS COQUEIROS", "SE", "49140000", "AVENIDA OCEANICA", "CENTRO"
    ),
    # BA
    "salvador": EnderecoPadrao("SALVADOR", "BA", "40020000", "AVENIDA SETE DE SETEMBRO", "CENTRO"),
    "feira de santana": EnderecoPadrao("FEIRA DE SANTANA", "BA", "44001000", "AVENIDA GETULIO VARGAS", "CENTRO"),
    # CE
    "fortaleza": EnderecoPadrao("FORTALEZA", "CE", "60010000", "RUA MAJOR FACUNDO", "CENTRO"),
    # PI
    "teresina": EnderecoPadrao("TERESINA", "PI", "64000020", "AVENIDA FREI SERAFIM", "CENTRO"),
    # MA
    "sao luis": EnderecoPadrao("SAO LUIS", "MA", "65010000", "AVENIDA DOS HOLANDESES", "CALHAU"),
    # GO / DF
    "goiania": EnderecoPadrao("GOIANIA", "GO", "74003010", "AVENIDA GOIAS", "CENTRO"),
    "aparecida de goiania": EnderecoPadrao(
        "APARECIDA DE GOIANIA", "GO", "74905020", "AVENIDA INDEPENDENCIA", "CIDADE LIVRE"
    ),
    "anapolis": EnderecoPadrao("ANAPOLIS", "GO", "75020010", "AVENIDA BRASIL", "CENTRO"),
    "brasilia": EnderecoPadrao("BRASILIA", "DF", "70040900", "SDS BLOCO A", "ASA SUL"),
    # SP
    "sao paulo": EnderecoPadrao("SAO PAULO", "SP", "01001000", "PRACA DA SE", "SE"),
    "campinas": EnderecoPadrao("CAMPINAS", "SP", "13010000", "AVENIDA FRANCISCO GLICERIO", "CENTRO"),
    "santos": EnderecoPadrao("SANTOS", "SP", "11010000", "RUA XV DE NOVEMBRO", "CENTRO"),
    "guarulhos": EnderecoPadrao("GUARULHOS", "SP", "07010000", "RUA DOM PEDRO II", "CENTRO"),
    # RJ
    "rio de janeiro": EnderecoPadrao("RIO DE JANEIRO", "RJ", "20040020", "AVENIDA RIO BRANCO", "CENTRO"),
    # MG
    "belo horizonte": EnderecoPadrao("BELO HORIZONTE", "MG", "30130000", "AVENIDA AFONSO PENA", "CENTRO"),
    "uberlandia": EnderecoPadrao("UBERLANDIA", "MG", "38400040", "AVENIDA AFONSO PENA", "CENTRO"),
    # PR
    "curitiba": EnderecoPadrao("CURITIBA", "PR", "80010000", "RUA XV DE NOVEMBRO", "CENTRO"),
    # SC
    "florianopolis": EnderecoPadrao("FLORIANOPOLIS", "SC", "88010000", "RUA FELIPE SCHMIDT", "CENTRO"),
    "ararangua": EnderecoPadrao("ARARANGUA", "SC", "88900000", "AVENIDA SETE DE SETEMBRO", "CENTRO"),
    # RS
    "porto alegre": EnderecoPadrao("PORTO ALEGRE", "RS", "90010000", "RUA DOS ANDRADAS", "CENTRO HISTORICO"),
    # MT / MS
    "cuiaba": EnderecoPadrao("CUIABA", "MT", "78005000", "AVENIDA HISTORIADOR RUBENS DE MENDONCA", "BOSQUE DA SAUDE"),
    "campo grande": EnderecoPadrao("CAMPO GRANDE", "MS", "79002000", "AVENIDA AFONSO PENA", "CENTRO"),
    # ES
    "vitoria": EnderecoPadrao("VITORIA", "ES", "29010000", "AVENIDA JERONIMO MONTEIRO", "CENTRO"),
    # PA / AM
    "belem": EnderecoPadrao("BELEM", "PA", "66010000", "AVENIDA PRESIDENTE VARGAS", "CAMPINA"),
    "manaus": EnderecoPadrao("MANAUS", "AM", "69005040", "AVENIDA EDUARDO RIBEIRO", "CENTRO"),
}

# Capital da UF (quando a cidade de nascimento não está na tabela)
_CAPITAL_UF: dict[str, str] = {
    "AC": "rio branco",
    "AL": "maceio",
    "AP": "macapa",
    "AM": "manaus",
    "BA": "salvador",
    "CE": "fortaleza",
    "DF": "brasilia",
    "ES": "vitoria",
    "GO": "goiania",
    "MA": "sao luis",
    "MT": "cuiaba",
    "MS": "campo grande",
    "MG": "belo horizonte",
    "PA": "belem",
    "PB": "joao pessoa",
    "PR": "curitiba",
    "PE": "recife",
    "PI": "teresina",
    "RJ": "rio de janeiro",
    "RN": "natal",
    "RS": "porto alegre",
    "RO": "porto velho",
    "RR": "boa vista",
    "SC": "florianopolis",
    "SP": "sao paulo",
    "SE": "aracaju",
    "TO": "palmas",
}

# Fallback nacional se nada casar
_DEFAULT = EnderecoPadrao("RECIFE", "PE", "50010000", "RUA DA AURORA", "BOA VISTA")

_UFS = set(_CAPITAL_UF.keys())


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # tira " - PE", "/PE", etc.
    for sep in (" - ", "/", ",", " ("):
        if sep in s:
            s = s.split(sep)[0]
    s = " ".join(s.split())
    return s


def _extrair_cidade_uf(raw: str) -> tuple[str, str]:
    """
    'ARAPIRACA, AL' | 'ARAPIRACA/AL' | 'ARAPIRACA - AL' | 'ARAPIRACA AL'
    -> ('arapiraca', 'AL')
    """
    s = (raw or "").strip()
    if not s:
        return "", ""
    m = re.search(
        r"^(.+?)[\s,/\-]+([A-Za-z]{2})\s*$",
        s,
    )
    if m and m.group(2).upper() in _UFS:
        return _norm(m.group(1)), m.group(2).upper()
    return _norm(s), ""


def _uf_do_motorista(motorista) -> str:
    """UF de nascimento: naturalidade, órgão emissor (SSP AL), depois uf do form."""
    nat = getattr(motorista, "naturalidade", "") or ""
    _, uf = _extrair_cidade_uf(nat)
    if uf:
        return uf
    # uf embutida em local_emissao_cnh só se naturalidade já trouxe cidade sem UF
    org = (getattr(motorista, "orgao_emissor", "") or "").upper()
    m = re.search(r"\b([A-Z]{2})\b", org)
    if m and m.group(1) in _UFS:
        return m.group(1)
    return (getattr(motorista, "uf", "") or "").strip().upper()


def _lookup_tabela(chave: str) -> Optional[EnderecoPadrao]:
    n = _norm(chave)
    if not n:
        return None
    if n in _ENDERECOS:
        return _ENDERECOS[n]
    for k, end in _ENDERECOS.items():
        if k in n or n in k:
            return end
    return None


def buscar_endereco_regiao(
    cidade: str = "",
    uf: str = "",
    naturalidade: str = "",
) -> Optional[EnderecoPadrao]:
    """
    Procura endereço padrão.
    Preferência: naturalidade -> cidade informada -> capital da UF.
    """
    # 1) naturalidade (nascimento)
    cid_nat, uf_nat = _extrair_cidade_uf(naturalidade)
    if cid_nat:
        end = _lookup_tabela(cid_nat)
        if end:
            return end
    # 2) cidade explícita
    cid = _norm(cidade)
    if cid:
        end = _lookup_tabela(cid)
        if end:
            return end
    # 3) capital da UF (da naturalidade ou informada)
    uf_u = (uf_nat or uf or "").strip().upper()
    if uf_u in _CAPITAL_UF:
        end = _lookup_tabela(_CAPITAL_UF[uf_u])
        if end:
            return end
    return None


def _endereco_cidade_desconhecida(cidade: str, uf: str) -> Optional[EnderecoPadrao]:
    """
    Cidade de nascimento fora da tabela:
      1) ViaCEP (Centro)
      2) capital da UF na tabela
    """
    cid = _norm(cidade)
    if not cid:
        return None
    uf_u = (uf or "").strip().upper()
    cidade_show = " ".join(w.capitalize() for w in cid.split()).upper()

    # ViaCEP
    try:
        from utils.cep_por_cidade import buscar_cep_viacep

        cep = buscar_cep_viacep(
            cidade_show.title() if cidade_show.isupper() else cidade_show,
            uf_u or "PE",
            logradouro="Centro",
        )
        if cep and len(cep) == 8:
            print(f"[Endereço] ViaCEP {cidade_show}/{uf_u or '?'} -> {cep}")
            return EnderecoPadrao(
                cidade=cidade_show,
                uf=uf_u or "PE",
                cep=cep,
                endereco="RUA DO COMERCIO",
                bairro="CENTRO",
            )
    except Exception as e:
        print(f"[Endereço] ViaCEP falhou ({cidade_show}): {e}")

    # capital da UF
    if uf_u in _CAPITAL_UF:
        end = _lookup_tabela(_CAPITAL_UF[uf_u])
        if end:
            print(
                f"[Endereço] Cidade '{cidade_show}' fora da tabela -> "
                f"capital {end.cidade}/{end.uf}"
            )
            return end
    return None


def _endereco_residencia_inutil(motorista) -> bool:
    """
    True se o que veio do OCR/comprovante NÃO serve como residência:
      - vazio
      - frase de aviso (AVISO DE DÉBITO...)
      - CEP sem logradouro/cidade
      - cidade lixo
    """
    cep = (getattr(motorista, "cep", None) or "").strip()
    end = (getattr(motorista, "endereco", None) or "").strip()
    cid = (getattr(motorista, "cidade", None) or "").strip()
    bairro = (getattr(motorista, "bairro", None) or "").strip()

    if not cep and not end and not cid:
        return True

    eu = end.upper()
    if any(
        x in eu
        for x in (
            "AVISO DE", "DEBITO", "DÉBITO", "NECESSARIO", "NECESSÁRIO",
            "ENTRE EM CONTATO", "ENTRE OF CONTATO", "FALE CONOSCO",
            "DOCUMENTO EMITIDO", "ASSINADO DIGITAL",
        )
    ):
        return True

    # CEP sozinho sem rua e sem cidade -> incompleto
    if cep and not end and not cid:
        return True

    # tem "endereço" mas não parece rua
    if end and not re.search(
        r"\b(RUA|R\.|AV|AVENIDA|TRAVESSA|ALAMEDA|RODOVIA|ESTRADA|PRACA|PRAÇA)\b",
        eu,
    ):
        if len(end) > 25 or any(x in eu for x in ("AVISO", "CONTATO", "DEBITO")):
            return True

    # cidade preenchida com lixo
    cu = cid.upper()
    if cid and any(
        x in cu
        for x in ("DOCUMENTO", "DETRAN", "EMITIDO", "ASSINADO", "DIGITAL")
    ):
        return True

    # tem CEP+endereço válidos e cidade -> ok, não fallback
    if cep and end and cid and re.search(r"\b(RUA|AV|AVENIDA|TRAVESSA)\b", eu):
        return False
    # tem endereço de rua + cidade mesmo sem CEP -> ok (CEP pode vir do fallback parcial)
    if end and cid and re.search(r"\b(RUA|AV|AVENIDA|TRAVESSA)\b", eu):
        return False
    # só bairro/cidade sem rua -> ainda tenta melhorar com naturalidade se cidade vazia
    if not end or not cid:
        return True
    return False


def aplicar_fallback_residencia(motorista) -> bool:
    """
    Preenche residência com naturalidade quando:
      - não há comprovante útil, OU
      - comprovante veio lixo (AVISO DE DÉBITO, CEP errado, etc.)

    Returns True se aplicou/completou fallback.
    """
    if not _endereco_residencia_inutil(motorista):
        # só completa CEP se faltar e já tem cidade
        cid = (getattr(motorista, "cidade", "") or "").strip()
        uf = (getattr(motorista, "uf", "") or "").strip()
        if cid and not (getattr(motorista, "cep", "") or "").strip():
            end = _lookup_tabela(cid) or _endereco_cidade_desconhecida(cid, uf)
            if end and end.cep:
                motorista.cep = end.cep
                print(f"[Endereço] Completou CEP via cidade {end.cidade}: {end.cep}")
                return True
        return False

    nat = (getattr(motorista, "naturalidade", "") or "").strip()
    cid_nat, uf_nat = _extrair_cidade_uf(nat)
    if not uf_nat:
        uf_nat = _uf_do_motorista(motorista)

    # se comprovante trouxe cidade real, usa ela; senão naturalidade
    cid_comp = (getattr(motorista, "cidade", "") or "").strip()
    if cid_comp and not any(
        x in cid_comp.upper()
        for x in ("DOCUMENTO", "DETRAN", "EMITIDO", "AVISO")
    ):
        # cidade ok mas resto lixo - completa com tabela da cidade do comprovante
        end_c = _lookup_tabela(cid_comp) or _endereco_cidade_desconhecida(
            cid_comp, (getattr(motorista, "uf", "") or uf_nat)
        )
        if end_c:
            if _endereco_parece_logradouro_ruim(getattr(motorista, "endereco", "")):
                motorista.endereco = end_c.endereco
                motorista.bairro = motorista.bairro or end_c.bairro
            motorista.cep = end_c.cep
            motorista.cidade = end_c.cidade
            motorista.uf = end_c.uf or motorista.uf
            print(
                f"[Endereço] Comprovante incompleto/lixo - "
                f"completou com cidade do doc {end_c.cidade}/{end_c.uf}"
            )
            print(
                f"[Endereço] Fallback: {motorista.endereco}, {motorista.bairro} - "
                f"{motorista.cidade}/{motorista.uf} CEP {motorista.cep}"
            )
            return True

    end: Optional[EnderecoPadrao] = None
    origem = ""

    # --- 1) SEMPRE naturalidade primeiro ---
    if cid_nat:
        end = _lookup_tabela(cid_nat)
        if end:
            origem = f"nascimento ({end.cidade}/{end.uf})"
        else:
            end = _endereco_cidade_desconhecida(cid_nat, uf_nat)
            if end:
                origem = f"nascimento/ViaCEP ({end.cidade}/{end.uf})"

    # --- 2) naturalidade vazia: capital da UF do doc ---
    if end is None and uf_nat:
        cap = _CAPITAL_UF.get(uf_nat)
        if cap:
            end = _lookup_tabela(cap)
            if end:
                origem = f"capital da UF de nascimento ({end.cidade}/{end.uf})"

    # --- 3) último recurso: padrão Recife ---
    if end is None:
        end = _DEFAULT
        origem = f"padrão nacional {_DEFAULT.cidade}/{_DEFAULT.uf}"
        print(
            f"[Endereço] Sem comprovante útil e naturalidade fraca - "
            f"usando {origem}"
        )
    else:
        print(f"[Endereço] Residência via naturalidade - {origem}")

    from utils.texto import gw_texto

    motorista.cep = end.cep
    motorista.endereco = gw_texto(end.endereco)
    motorista.bairro = gw_texto(end.bairro)
    motorista.cidade = gw_texto(end.cidade)
    motorista.uf = gw_texto(end.uf)[:2]
    # naturalidade também sem acento (lookup Cidade_Naturalidade no GW)
    if getattr(motorista, "naturalidade", None):
        motorista.naturalidade = gw_texto(motorista.naturalidade)

    print(
        f"[Endereço] Fallback: {motorista.endereco}, {motorista.bairro} - "
        f"{motorista.cidade}/{motorista.uf} CEP {motorista.cep}"
    )
    return True


def _endereco_parece_logradouro_ruim(end: str) -> bool:
    u = (end or "").upper()
    if not u.strip():
        return True
    if any(x in u for x in ("AVISO", "DEBITO", "DÉBITO", "CONTATO", "DOCUMENTO EMITIDO")):
        return True
    if not re.search(r"\b(RUA|AV|AVENIDA|TRAVESSA|ALAMEDA|ESTRADA)\b", u):
        return True
    return False
