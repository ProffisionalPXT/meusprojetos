# -*- coding: utf-8 -*-
"""Teste CNH Eduardo - filiação (EVA=mãe) e lixo OCR."""
from pathlib import Path

from ocr.parsers_locais import (
    parse_cnh,
    _nome_parece_lixo_ocr,
    _normalizar_filiacao,
    _prenome_feminino,
)

assert _nome_parece_lixo_ocr("WIT AES RAE AYY")
assert _nome_parece_lixo_ocr("ETARIANACIONALYBE IMI PELEE ROEL")
assert _nome_parece_lixo_ocr("AES EMT RET")
assert not _nome_parece_lixo_ocr("EVA DO NASCIMENTO CARDOSO")
assert not _nome_parece_lixo_ocr("EDUARDO MARTINS CARDOSO")
assert _prenome_feminino("EVA DO NASCIMENTO CARDOSO")
assert not _prenome_feminino("EURIPEDES MARTINS CARDOSO")

# simula o bug da tela: pai=EVA, mae=lixo
out = {
    "nome_pai": "EVA DO NASCIMENTO CARDOSO",
    "nome_mae": "ETARIANACIONALYBE IMI PELEE ROEL",
}
_normalizar_filiacao(out)
assert out["nome_mae"] == "EVA DO NASCIMENTO CARDOSO", out
assert out["nome_pai"] == "", out
print("normalizar_filiacao OK")

# OCR real (arquivo se existir)
ocr_path = Path(__file__).parent / "_ocr_eduardo.txt"
if ocr_path.exists():
    texto = ocr_path.read_text(encoding="utf-8")
else:
    texto = """
fr Wit aes rae ayy
{ EDUARDO MARTINS CARDOSO }
03/12/1973 GOIANIAIGO
AES emt Ret
EVA DONASCIMENTO CARDOSO Lid
WON BETES ATED
02046654953
EDUARDO MARTINS CARDOSO AES
ETARIANACIONALYBE
IMI PELEE ROEL BEE ELATED
LOCAL 14540560438
"""

d = parse_cnh(texto)
print("=== PARSE OCR FOTO ===")
for k in (
    "nome",
    "nome_pai",
    "nome_mae",
    "data_emissao_cnh",
    "validade_cnh",
    "data_primeira_habilitacao",
    "cnh",
    "cpf",
):
    print(f"  {k}: {d.get(k)!r}")

assert d.get("nome") == "EDUARDO MARTINS CARDOSO"
assert "EVA" in (d.get("nome_mae") or "")
assert "CARDOSO" in (d.get("nome_mae") or "")
assert not _nome_parece_lixo_ocr(d.get("nome_mae") or "x")
# pai não pode ser a mãe
assert "EVA" not in (d.get("nome_pai") or "")
assert not _nome_parece_lixo_ocr(d.get("nome_pai") or "ok") or not d.get("nome_pai")
print()
print("RESULTADO: OK")
