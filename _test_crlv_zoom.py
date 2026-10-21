"""Teste rápido: CRLV com zoom 4.5 + crops de quadrante."""
import os
from pathlib import Path

os.environ.setdefault("OCR_FOTO_MIN_PX", "3600")
os.environ.setdefault("OCR_FOTO_ZOOM", "4")

from ocr.local_ocr import extrair_texto_arquivo
from ocr.parsers_locais import parse_crlv

pasta = Path("input/motorista")
# prioriza a (1) = cavalo IVECO da print
cands = sorted(pasta.glob("*.jpeg")) + sorted(pasta.glob("*.jpg"))
for p in cands:
    print("=" * 60)
    print(p.name)
    txt = extrair_texto_arquivo(p, forcar_zoom=4.5)
    print("--- preview ---")
    print((txt or "")[:500].replace("\n", " | "))
    d = parse_crlv(txt or "", path=p)
    print("--- campos ---")
    for k in (
        "placa", "renavam", "chassi", "marca_modelo_versao", "cor",
        "ano_fab", "ano_mod", "cidade", "uf",
        "proprietario_nome", "proprietario_cpf_cnpj",
        "eh_caminhao_trator", "eh_semi_reboque",
    ):
        if d.get(k) not in (None, "", False):
            print(f"  {k}: {d.get(k)!r}")
