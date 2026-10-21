import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr.local_ocr import extrair_texto_arquivo
from ocr.parsers_locais import parse_cnh

p = Path(__file__).resolve().parent / "input" / "lindomar" / "CNH-e.pdf.pdf"
t = extrair_texto_arquivo(p)
d = parse_cnh(t)
print("=== CNH Lindomar ===")
for k in (
    "nome",
    "cpf",
    "data_nascimento",
    "data_emissao_cnh",
    "validade_cnh",
    "data_primeira_habilitacao",
    "categoria_cnh",
    "cnh",
    "rg",
    "orgao_emissor",
    "nome_mae",
    "naturalidade",
    "local_emissao_cnh",
):
    print(f"  {k}: {d.get(k)!r}")

mae_ok = (d.get("nome_mae") or "").startswith("MARIA DALVA")
ok = (
    (d.get("nome") or "").startswith("LINDOMAR")
    and d.get("data_nascimento") == "22/08/1962"
    and d.get("data_emissao_cnh") == "12/04/2023"
    and d.get("validade_cnh") == "05/04/2028"
    and d.get("data_primeira_habilitacao") == "28/03/1998"
    and d.get("categoria_cnh") == "E"
    and d.get("cnh") == "00575345816"
    and mae_ok
    and "EI" not in (d.get("nome_mae") or "")
)
print()
print("RESULTADO:", "OK - pode rodar o bot" if ok else "AINDA FALHA")
print("  mae limpa?", mae_ok, repr(d.get("nome_mae")))
