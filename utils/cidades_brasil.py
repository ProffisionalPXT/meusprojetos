from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path
from typing import Optional, List, Dict

_ARQUIVO_JSON = Path(__file__).parent / "cidades_ibge.json"
_MUNICIPIOS: Dict[str, List[str]] = {}

def _carregar_municipios() -> Dict[str, List[str]]:
    global _MUNICIPIOS
    if not _MUNICIPIOS and _ARQUIVO_JSON.exists():
        try:
            _MUNICIPIOS = json.loads(_ARQUIVO_JSON.read_text(encoding="utf-8"))
        except Exception:
            _MUNICIPIOS = {}
    return _MUNICIPIOS

def normalizar_texto_cidade(s: str) -> str:
    s = (s or "").strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

_PREFIXOS_LIXO_CIDADE = re.compile(
    r"^(?:LOCAL|CIDADE|MUNICIPIO|MUNIC[IÍ]PIO|MUNIC|MUN|UF|ÁREA|AREA|REA|AKK|AK|OAR|OEA|OER|EEA|SECRETARIA|DETRAN)\s+",
    re.I,
)

def limpar_prefixo_cidade(cidade: str) -> str:
    s = (cidade or "").strip()
    for _ in range(3):
        m = _PREFIXOS_LIXO_CIDADE.sub("", s).strip()
        if m == s:
            break
        s = m
    return s

def eh_cidade_valida_brasil(cidade: str, uf: Optional[str] = None) -> bool:
    if not cidade:
        return False
    cid_limpa = limpar_prefixo_cidade(cidade)
    cid_norm = normalizar_texto_cidade(cid_limpa)
    if not cid_norm or len(cid_norm) < 3:
        return False
    muns = _carregar_municipios()
    if not muns:
        return True
    return cid_norm in muns

def obter_cidade_corrigida(cidade: str, uf: Optional[str] = None) -> str:
    if not cidade:
        return ""
    return limpar_prefixo_cidade(cidade)
