"""
Classificação dos documentos que o usuário recebe.

Aceita qualquer formato (foto jpg/png, PDF digital, PDF escaneado, misturado).
Classifica por:
  1) nome do arquivo (se tiver dica: cnh.jpg, tac.pdf, DWU9135.png)
  2) conteúdo do texto/OCR (quando o nome for WhatsApp/IMG/sem dica)
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class TipoDocumento(str, Enum):
    TAC = "tac"
    CNH = "cnh"
    CRLV = "crlv"
    COMPROVANTE = "comprovante"
    OUTRO = "outro"
    IGNORAR = "ignorar"  # rastreador/omnilink/etc. - não entra no cadastro


# NÃO são documento de carro/motorista (só poluem OCR)
# Ficha Omnilink, rastreador, espelhamento... mesmo com placa no nome
_IRRELEVANTES_NOME = (
    "omnilink",
    "ficha de ativ",
    "ficha_ativ",
    "ficha-ativ",
    "ativacao omnilink",
    "ativação omnilink",
    "rastreador",
    "sascar",
    "autoban",
    "onixsat",
    "positron",
    "espelhamento",
    "gerenciadora de risco",
    "fichaativacao",
    "meu.omnilink",
)

_IRRELEVANTES_TEXTO = (
    r"FICHA\s*DE\s*ATIVA[CÇ][AÃ]O\s*OMNILINK",
    r"\bOMNILINK\b",
    r"ESPELHAMENTO\s*DE\s*SINAL",
    r"GERENCIADORA\s*DE\s*RISCO",
    r"BASE\s*CENTRAL",
    r"meu\.omnilink\.com",
)


def documento_irrelevante(path: Path, texto: str = "") -> bool:
    """
    True = NÃO usar no cadastro GW (não é CNH/CRLV/TAC/comprovante).
    Ex.: Ficha de Ativação Omnilink ONB7E61.pdf - tem placa no nome mas não é CRLV.
    """
    nome = Path(path).stem.lower()
    if any(x in nome for x in _IRRELEVANTES_NOME):
        return True
    # "ficha" + "ativ" no nome (variações de acento)
    if "ficha" in nome and "ativ" in nome:
        return True
    t = (texto or "").upper()
    if t:
        for pat in _IRRELEVANTES_TEXTO:
            if re.search(pat, t, re.I):
                # se também for CRLV real (RENAVAM+CHASSI+SENATRAN), não ignora
                if "RENAVAM" in t and "CHASSI" in t and "SENATRAN" in t:
                    if "CERTIFICADO DE REGISTRO E LICENCIAMENTO" in t:
                        return False
                return True
    return False


# palavras no NOME do arquivo
_REGRAS: List[Tuple[TipoDocumento, tuple]] = [
    (TipoDocumento.TAC, ("tac", "antt", "rntrc", "transportador")),
    (TipoDocumento.CNH, ("cnh", "habilit", "carteira", "cnh-e", "cnhe")),
    (
        TipoDocumento.CRLV,
        (
            "crlv",
            "crv",
            "dut",
            "veiculo",
            "veículo",
            "placa",
            "renavam",
            "crlv-e",
            "crlve",
        ),
    ),
    (
        TipoDocumento.COMPROVANTE,
        (
            "comprovante",
            "endereco",
            "endereço",
            "residencia",
            "residência",
            "energia",
            "luz",
            "agua",
            "água",
            "equatorial",
            "neoenergia",
            "enel",
            "conta",
            "cep",
            "fatura",
        ),
    ),
]


def classificar_arquivo(path: Path) -> TipoDocumento:
    """Classifica só pelo nome (rápido). Pode ser OUTRO se for foto genérica."""
    path = Path(path)
    if documento_irrelevante(path):
        return TipoDocumento.IGNORAR
    nome = path.stem.lower()
    for tipo, palavras in _REGRAS:
        if any(p in nome for p in palavras):
            return tipo
    # placa no nome (ex: DWU9135.jpg ou "... -TGB-6B52 - ANDRE.pdf")
    # NÃO se for omnilink/rastreador (já filtrado acima)
    if _parece_placa(nome) or _placa_no_nome(path.stem):
        return TipoDocumento.CRLV
    # razão social + LTDA no nome costuma ser CRLV do prop (ex.: CARROCERIAS...TGB-6B52)
    if re.search(r"\b(ltda|eireli|s\.?a\.?)\b", nome) and _placa_no_nome(path.stem):
        return TipoDocumento.CRLV
    # CPF no nome -> costuma ser TAC
    digitos = "".join(c for c in nome if c.isdigit())
    if len(digitos) >= 11 and not _parece_foto_generica(nome):
        return TipoDocumento.TAC
    return TipoDocumento.OUTRO


def _parece_foto_generica(nome: str) -> bool:
    """WhatsApp, IMG_, Screenshot, photo_... sem dica de tipo."""
    n = nome.lower()
    genericos = (
        "whatsapp",
        "img_",
        "img-",
        "image",
        "foto",
        "photo",
        "screenshot",
        "captura",
        "received",
        "download",
        "file",
        "documento",
        "scan",
        "scanned",
    )
    return any(g in n for g in genericos)


def classificar_por_conteudo(texto: str) -> Optional[TipoDocumento]:
    """
    Infere o tipo pelo texto lido (PDF ou OCR de foto).
    Retorna None se não houver sinais claros.
    IGNORAR (omnilink etc.) se o texto for só rastreador/ficha.
    """
    if not (texto or "").strip():
        return None
    t = texto.upper()

    # Ficha Omnilink / rastreador - NÃO é CRLV mesmo com placa
    if documento_irrelevante(Path("x"), texto):
        # CRLV digital verdadeiro tem bloco SENATRAN + RENAVAM + CHASSI
        eh_crlv_real = (
            "CERTIFICADO DE REGISTRO E LICENCIAMENTO" in t
            and "RENAVAM" in t
            and ("CHASSI" in t or re.search(r"\b[A-HJ-NPR-Z0-9]{17}\b", t))
        )
        if not eh_crlv_real:
            return TipoDocumento.IGNORAR

    scores: Dict[TipoDocumento, int] = {
        TipoDocumento.CNH: 0,
        TipoDocumento.CRLV: 0,
        TipoDocumento.TAC: 0,
        TipoDocumento.COMPROVANTE: 0,
    }

    # --- CNH ---
    if re.search(r"HABILITA[CÇ][AÃ]O|CARTE[I]?RA\s*NACIONAL", t):
        scores[TipoDocumento.CNH] += 4
    if re.search(r"N[ºO°.]?\s*REGIS(TRO)?|CAT\.?\s*HAB|1[ªA]\s*HABILITA", t):
        scores[TipoDocumento.CNH] += 3
    if ("FILIA" in t or "IAGAO" in t) and ("CPF" in t or re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", t)):
        scores[TipoDocumento.CNH] += 2
    if ("SENATRAN" in t or "VALIDADE" in t) and "RENAVAM" not in t:
        scores[TipoDocumento.CNH] += 1

    # --- CRLV (só se parecer licenciamento de verdade) ---
    if "RENAVAM" in t or "CHASSI" in t:
        scores[TipoDocumento.CRLV] += 4
    if re.search(r"MARCA\s*/\s*MODELO|LICENCIAMENTO\s*DE\s*VE[IÍ]CULO|CRLV", t):
        scores[TipoDocumento.CRLV] += 3
    if re.search(r"\b[A-Z]{3}\d[A-Z0-9]\d{2}\b", t) and (
        "RENAVAM" in t or "CHASSI" in t or "CERTIFICADO DE REGISTRO" in t
    ):
        scores[TipoDocumento.CRLV] += 3
    if re.search(r"SEMI[-\s]?REBOQUE|CAMINH[AÃ]O\s*TRATOR|ESP[EÉ]CIE\s*/\s*TIPO", t):
        scores[TipoDocumento.CRLV] += 2

    # --- TAC / ANTT / ETC (certificado RNTRC) ---
    if "RNTRC" in t or re.search(r"TRANSPORTADOR\s*AUT[OÔ]NOMO", t):
        scores[TipoDocumento.TAC] += 5
    if re.search(r"\bANTT\b|AG[EÊ]NCIA\s*NACIONAL\s*DE\s*TRANSPORTES", t):
        scores[TipoDocumento.TAC] += 4
    # OCR sujo: "AMAT AGEN CIA", "AGENCIANACIONALDE", "AGENCIA NACIONAL DE TEE"
    if re.search(r"AGEN\w{0,8}\s*NACIONAL|AGENCIANACIONAL", t):
        scores[TipoDocumento.TAC] += 3
    if re.search(r"TRANSPORTADORES\s*RODOVI[AÁ]RIOS", t):
        scores[TipoDocumento.TAC] += 3
    # OCR: TRANSPORTADORES RODOVIARI / SDOVIARIOS DE CARGAS / RODOVIA
    if re.search(r"TRANSPORTADOR\w*\s+RODOVI|RODOVI\w*\s+DE\s+CARG", t):
        scores[TipoDocumento.TAC] += 3
    if re.search(r"\b(?:TAC|ETC|CTC)\b", t) and (
        "CATEGORIA" in t or "CADASTRADO" in t or "RNTRC" in t or "ANTT" in t
        or re.search(r"\d{6,}", t)
    ):
        scores[TipoDocumento.TAC] += 3
    # foto WhatsApp do certificado: "TAC 049285533" / "ETC 052599399"
    if re.search(r"\b(?:TAC|ETC|CTC)\s*[:\.]?\s*\d{6,}", t):
        scores[TipoDocumento.TAC] += 5
    if re.search(r"CERTIFICADO\s*DE\s*REGISTRO\s*NACIONAL\s*DE\s*TRANSPORT", t):
        scores[TipoDocumento.TAC] += 4
    # OCR parcial: CERTIFICADO DE REGISTRO / SEERTIFICADO DE REGISTRC
    if re.search(r"CERTIFICADO\s+DE\s+REGISTR", t) and (
        "ANTT" in t or "TRANSPORT" in t or "RODOVI" in t or "CARGAS" in t
    ):
        scores[TipoDocumento.TAC] += 4
    if re.search(r"TRANSPORTADORES?\s+RODOVI[AÁ]RIOS?\s+DE\s+CARGAS", t):
        scores[TipoDocumento.TAC] += 3
    if re.search(r"CERTIFICADO\s+DE\s+REGISTRO\s+NACIONAL", t) and (
        "ANTT" in t or "TAC" in t or "RNTRC" in t or "ETC" in t
    ):
        scores[TipoDocumento.TAC] += 2

    # --- Comprovante ---
    if re.search(r"\b\d{5}-?\d{3}\b", t) and re.search(
        r"RUA|AVENIDA|AV\.|BAIRRO|CEP", t
    ):
        scores[TipoDocumento.COMPROVANTE] += 3
    if re.search(
        r"NEOENERGIA|EQUATORIAL|ENEL|kWh|ENERGIA\s*EL[EÉ]TRICA|COMPANHIA\s*DE\s*[AÁ]GUA|"
        r"SANEAMENTO|FATURA|CONTA\s*DE\s*(LUZ|[AÁ]GUA)",
        t,
    ):
        scores[TipoDocumento.COMPROVANTE] += 4

    melhor = max(scores, key=scores.get)
    if scores[melhor] >= 3:
        return melhor
    return None


def classificar_arquivo_e_conteudo(
    path: Path, texto: str = ""
) -> Tuple[TipoDocumento, str]:
    """
    Nome do arquivo + conteúdo.
    Retorna (tipo, origem) origem = nome|conteudo|nome+conteudo|ignorar
    """
    path = Path(path)
    if documento_irrelevante(path, texto or ""):
        return TipoDocumento.IGNORAR, "ignorar"

    por_nome = classificar_arquivo(path)
    if por_nome == TipoDocumento.IGNORAR:
        return TipoDocumento.IGNORAR, "ignorar"

    por_texto = classificar_por_conteudo(texto) if texto else None
    if por_texto == TipoDocumento.IGNORAR:
        return TipoDocumento.IGNORAR, "ignorar_conteudo"

    if por_nome != TipoDocumento.OUTRO and por_texto is None:
        return por_nome, "nome"
    if por_nome == TipoDocumento.OUTRO and por_texto:
        return por_texto, "conteudo"
    if por_nome != TipoDocumento.OUTRO and por_texto:
        if por_nome == por_texto:
            return por_nome, "nome+conteudo"
        # conflito: confia mais no conteúdo (foto com nome errado)
        # mas NÃO deixa omnilink virar crlv
        if por_texto == TipoDocumento.IGNORAR:
            return TipoDocumento.IGNORAR, "ignorar"
        return por_texto, f"conteudo(nome_era_{por_nome.value})"
    return TipoDocumento.OUTRO, "indefinido"


def _parece_placa(nome: str) -> bool:
    limpo = "".join(c for c in nome.upper() if c.isalnum())
    if len(limpo) == 7 and limpo[:3].isalpha() and any(c.isdigit() for c in limpo[3:]):
        return True
    return False


def _placa_no_nome(nome: str) -> Optional[str]:
    """Extrai placa Mercosul/antiga do nome do arquivo (TGB-6B52, ONB7E61...)."""
    u = (nome or "").upper()
    m = re.search(r"\b([A-Z]{3})[-\s]?(\d[A-Z0-9]\d{2})\b", u)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    m = re.search(r"\b([A-Z]{3})[-\s]?(\d{4})\b", u)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return None


def nome_empresa_no_arquivo(path: Path) -> str:
    """
    Ex.: 'CARROCERIAS METALICAS SOLDA FORTE LTDA -TGB-6B52 - ANDRE.pdf'
      -> 'CARROCERIAS METALICAS SOLDA FORTE LTDA'
    """
    stem = Path(path).stem
    # corta a partir da placa
    m = re.search(
        r"^(.+?)[\s\-_]+[A-Z]{3}[-\s]?\d[A-Z0-9]\d{2}\b",
        stem,
        re.I,
    )
    trecho = m.group(1) if m else stem
    trecho = re.sub(r"[\-_]+", " ", trecho)
    trecho = re.sub(r"\s+", " ", trecho).strip(" -_.")
    if re.search(r"\b(LTDA|EIRELI|S\.?A\.?|ME|EPP)\b", trecho, re.I):
        return trecho.upper()
    return ""


def agrupar_por_tipo(arquivos: List[Path]) -> dict:
    grupos = {t: [] for t in TipoDocumento}
    for a in arquivos:
        grupos[classificar_arquivo(a)].append(a)
    return grupos
