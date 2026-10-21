"""Teste rápido: OCR local + zoom no caso JOSE (sem Gemini)."""
import os
from pathlib import Path

os.environ["OCR_ENGINE"] = "local"
os.environ["GEMINI_SE_VAZIO"] = "0"

from utils.receber_fotos import CasoCadastro
from ocr.extrair_dados import extrair_dados_do_caso

pasta = Path("input/motorista")
arqs = sorted(
    p
    for p in pasta.iterdir()
    if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".pdf"}
)
caso = CasoCadastro(nome="motorista", pasta=pasta, arquivos=arqs)
print("arquivos:", [a.name for a in caso.arquivos])
d = extrair_dados_do_caso(caso)
m = d.motorista
print("=== MOTORISTA ===")
for k in (
    "nome",
    "cpf",
    "data_nascimento",
    "sexo",
    "nome_pai",
    "nome_mae",
    "rg",
    "orgao_emissor",
    "cnh",
    "categoria_cnh",
    "validade_cnh",
    "data_emissao_cnh",
    "local_emissao_cnh",
    "data_primeira_habilitacao",
    "naturalidade",
    "nacionalidade",
):
    print(f"  {k}: {getattr(m, k)!r}")
if d.veiculo:
    v = d.veiculo
    print("=== VEICULO ===", v.tipo, v.placa, v.marca_modelo_versao, "cid=", v.cidade)
    if v.proprietario:
        print("  prop", v.proprietario.nome, v.proprietario.cpf_cnpj, v.proprietario.cidade)
if d.carreta:
    c = d.carreta
    print("=== CARRETA ===", c.placa, c.marca_modelo_versao, "cid=", c.cidade)
    if c.proprietario:
        print("  prop", c.proprietario.nome, c.proprietario.cpf_cnpj, c.proprietario.cidade)
print("RNTRC", d.rntrc_tac)
if d.proprietario:
    print("prop principal", d.proprietario.nome, d.proprietario.cpf_cnpj, d.proprietario.cidade)
