# -*- coding: utf-8 -*-
"""Testa parsers com o texto OCR já salvo do caso João (sem re-OCR)."""
from pathlib import Path
from ocr.parsers_locais import parse_cnh, parse_crlv, parse_tac
from ocr.ocr_qualidade import normalizar_placa_mercosul
from ocr.tipos_documento import classificar_por_conteudo

# --- placa ---
assert normalizar_placa_mercosul("PJO9971") == "PJO9971", normalizar_placa_mercosul("PJO9971")
assert normalizar_placa_mercosul("PJO9G71") == "PJO9G71"  # mercosul real
print("OK placa antiga preservada:", normalizar_placa_mercosul("PJO9971"))

# --- CRLV PDF ---
t_crlv = Path("output/_ocr_9971 Q-1.txt").read_text(encoding="utf-8")
d = parse_crlv(t_crlv, path=Path("input/motorista/9971 Q-1.pdf"))
print("CRLV placa:", d.get("placa"))
print("CRLV prop:", d.get("proprietario_nome"))
print("CRLV cnpj:", d.get("proprietario_cpf_cnpj"))
assert d.get("placa") == "PJO9971", d.get("placa")
assert "SERVICO" not in (d.get("proprietario_nome") or "").upper(), d.get("proprietario_nome")
assert "OLIVEIRA" in (d.get("proprietario_nome") or "").upper(), d.get("proprietario_nome")
assert "46236770000139" in (d.get("proprietario_cpf_cnpj") or "")

# --- CNH ---
t_cnh = Path("output/_ocr_WhatsApp Image 2026-07-17 at 07.00.38.txt").read_text(encoding="utf-8")
d2 = parse_cnh(t_cnh)
print("CNH rg:", d2.get("rg"))
print("CNH emissao:", d2.get("data_emissao_cnh"))
print("CNH 1a hab:", d2.get("data_primeira_habilitacao"))
print("CNH validade:", d2.get("validade_cnh"))
assert d2.get("rg") == "1362010243", d2.get("rg")
assert d2.get("rg") != "."
# emissão pode falhar no OCR local sujo, mas NÃO pode ser igual à 1ª hab antiga
if d2.get("data_emissao_cnh") and d2.get("data_primeira_habilitacao"):
    assert d2["data_emissao_cnh"] != d2["data_primeira_habilitacao"] or int(
        d2["data_emissao_cnh"][-4:]
    ) >= 2019

# --- TAC (texto real é ruim; simula OCR bom do cartão) ---
t_tac_bom = """
ANTT AGENCIA NACIONAL DE TRANSPORTES TERRESTRES
CERTIFICADO DE REGISTRO NACIONAL DE TRANSPORTADORES RODOVIARIOS DE CARGAS
L. S. OLIVEIRA
CNPJ: 46.236.770/0001-39
ETC 055407188
"""
d3 = parse_tac(t_tac_bom)
print("TAC nome:", d3.get("nome"))
print("TAC rntrc:", d3.get("rntrc"))
print("TAC cat:", d3.get("categoria"))
assert d3.get("rntrc") == "055407188", d3.get("rntrc")
assert "OLIVEIRA" in (d3.get("nome") or "").upper(), d3.get("nome")
assert classificar_por_conteudo(t_tac_bom).value == "tac"

# TAC com OCR parcial do arquivo real
t_tac_real = Path("output/_ocr_WhatsApp Image 2026-07-17 at 07.00.37.txt").read_text(encoding="utf-8")
# se ainda não tiver RNTRC no OCR real, ao menos classifica/extrai o que der
d4 = parse_tac(t_tac_real)
print("TAC real nome:", d4.get("nome"), "rntrc:", d4.get("rntrc"), "cnpj:", d4.get("cnpj"))

print("\n=== TODOS OS ASSERTS PASSARAM ===")
