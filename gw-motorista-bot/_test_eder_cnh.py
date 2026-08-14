"""Teste rápido CNH EDER - campos que falhavam (sexo, CAT, pai)."""
from pathlib import Path
from ocr.local_ocr import extrair_texto_arquivo
from ocr.parsers_locais import parse_cnh

p = Path(__file__).resolve().parent / "input" / "EDER" / "CNH-e.pdf.pdf"
print(f"Lendo {p.name}...")
txt = extrair_texto_arquivo(p)
d = parse_cnh(txt)
keys = (
    "nome",
    "cpf",
    "sexo",
    "categoria_cnh",
    "nome_pai",
    "nome_mae",
    "cnh",
    "rg",
    "data_nascimento",
    "validade_cnh",
    "data_emissao_cnh",
    "data_primeira_habilitacao",
    "naturalidade",
    "local_emissao_cnh",
)
print("=== PARSE CNH EDER ===")
for k in keys:
    print(f"  {k}: {d.get(k)!r}")

checks = {
    "categoria_cnh=AE": d.get("categoria_cnh") == "AE",
    "sexo=Masculino": d.get("sexo") == "Masculino",
    "nome_pai": "MOACIR" in (d.get("nome_pai") or ""),
    "nome_mae": "MARIA" in (d.get("nome_mae") or ""),
    "cpf": d.get("cpf") == "00083672133",
    "cnh": d.get("cnh") == "02878161902",
    "1a_hab=27/05/2003": d.get("data_primeira_habilitacao") == "27/05/2003",
    "emissao=08/11/2022": d.get("data_emissao_cnh") == "08/11/2022",
}
print()
for nome, ok in checks.items():
    print(f"  [{'OK' if ok else 'FALHA'}] {nome}")
print()
print("RESULTADO:", "OK" if all(checks.values()) else "AINDA FALHA")
