"""Normalização de texto para o GW (sem acento, maiúsculas)."""
from __future__ import annotations

import re
import unicodedata


def sem_acentos(s: str) -> str:
    """
    Remove acentos: Í->I, Ã->A, Ç->C, etc.
    Necessário para lookup do GW (PALMEIRA DOS INDIOS, não ÍNDIOS).
    """
    if not s:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def gw_texto(s: str, *, upper: bool = True) -> str:
    """Texto pronto para digitar no GW: sem acento, espaços limpos."""
    s = sem_acentos(s or "")
    s = re.sub(r"\s+", " ", s).strip()
    # remove ? de encoding quebrado
    s = s.replace("?", "")
    if upper:
        s = s.upper()
    return s
