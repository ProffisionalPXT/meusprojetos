# -*- coding: utf-8 -*-
"""Caso completo João - valida os 5 campos que falharam na confirmação."""
import os
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
from pathlib import Path
from dotenv import load_dotenv
project_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=project_dir / ".env", override=True)

os.environ["CONFIRMAR_DADOS"] = "0"
# força reprocessar (sem cache velho sem data_emissao)
os.environ.setdefault("OCR_ENGINE", "auto")
os.environ.setdefault("GEMINI_SE_VAZIO", "1")

from utils.receber_fotos import CasoCadastro
from ocr.extrair_dados import extrair_dados_do_caso

pasta = Path("input/motorista")
arquivos = sorted(
    p
    for p in pasta.iterdir()
    if p.is_file() and p.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png"}
)
print("Arquivos:", [a.name for a in arquivos])
caso = CasoCadastro(nome="motorista", pasta=pasta, arquivos=arquivos)
dados = extrair_dados_do_caso(caso)

m = dados.motorista
v = dados.veiculo
p = dados.proprietario

print("\n=== RESULTADO ===")
print("rg:", m.rg)
print("data_emissao_cnh:", m.data_emissao_cnh)
print("data_primeira:", m.data_primeira_habilitacao)
print("placa:", v.placa if v else None)
print("prop nome:", p.nome if p else None)
print("prop rntrc:", p.rntrc if p else None)
print("rntrc_tac:", dados.rntrc_tac)
print("prop cnpj:", p.cpf_cnpj if p else None)

erros = []
if m.rg != "1362010243":
    erros.append(f"rg={m.rg!r} (esperado 1362010243)")
if m.data_emissao_cnh != "04/11/2024":
    erros.append(f"emissao={m.data_emissao_cnh!r} (esperado 04/11/2024)")
if not v or v.placa != "PJO9971":
    erros.append(f"placa={getattr(v,'placa',None)!r} (esperado PJO9971)")
if not p or "OLIVEIRA" not in (p.nome or "").upper():
    erros.append(f"prop={getattr(p,'nome',None)!r} (esperado L.S.OLIVEIRA)")
if "SERVICO" in (getattr(p, "nome", "") or "").upper():
    erros.append("prop ainda é SERVICOS DE TRANSITO")
if not p or p.rntrc != "055407188":
    erros.append(f"rntrc={getattr(p,'rntrc',None)!r} (esperado 055407188)")

if erros:
    print("\nFALHAS:")
    for e in erros:
        print(" -", e)
    raise SystemExit(1)
print("\n[OK] TODOS OS 5 CAMPOS CORRETOS")
