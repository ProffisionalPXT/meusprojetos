# -*- coding: utf-8 -*-
from pathlib import Path
import re
import ocr.parsers_locais as p

t = Path("output/_ocr_WhatsApp Image 2026-07-17 at 07.00.38.txt").read_text(
    encoding="utf-8"
)
tn = p._norm(t)
out = {
    "nome": "",
    "cpf": "",
    "data_nascimento": "",
    "nome_pai": "",
    "nome_mae": "",
    "rg": "",
    "orgao_emissor": "",
    "cnh": "",
    "categoria_cnh": "",
    "validade_cnh": "",
    "data_emissao_cnh": "",
    "local_emissao_cnh": "",
    "data_primeira_habilitacao": "",
    "sexo": "",
    "nacionalidade": "BRASILEIRO",
    "naturalidade": "",
    "uf_naturalidade": "",
}
datas = re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", tn)
print("datas", datas)
p._classificar_datas_cnh(out, tn, datas)
print(
    "after classificar",
    out["data_emissao_cnh"],
    out["validade_cnh"],
    out["data_primeira_habilitacao"],
)
em = p._extrair_data_emissao_ocr(tn, validade=out.get("validade_cnh") or "")
print("extrair", em)
if not out.get("data_emissao_cnh"):
    out["data_emissao_cnh"] = em
print("after extrair set", out["data_emissao_cnh"])
p._recuperar_datas_cnh_ocr_sujo(out, tn)
print(
    "after recuperar",
    out["data_emissao_cnh"],
    out["validade_cnh"],
    out["data_primeira_habilitacao"],
)
for k in (
    "data_emissao_cnh",
    "validade_cnh",
    "data_primeira_habilitacao",
    "data_nascimento",
):
    v = out.get(k) or ""
    if v and not p._data_valida_cnh(v):
        out[k] = p._corrigir_data_ocr(v) or ""
print("after sanitize", out["data_emissao_cnh"])
prim = out.get("data_primeira_habilitacao") or ""
em = out.get("data_emissao_cnh") or ""
if em and prim and em == prim:
    print("equal prim/em - would clear")
d = p.parse_cnh(t)
print("FULL parse", d.get("data_emissao_cnh"), d.get("rg"), d.get("validade_cnh"))
