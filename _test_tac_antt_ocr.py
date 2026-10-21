# -*- coding: utf-8 -*-
"""Re-OCR do cartão ANTT com crops TAC + zoom forçado."""
from pathlib import Path
from ocr.local_ocr import extrair_texto_arquivo
from ocr.parsers_locais import parse_tac, parsear_arquivo
from ocr.tipos_documento import classificar_arquivo_e_conteudo, TipoDocumento

p = Path("input/motorista/WhatsApp Image 2026-07-17 at 07.00.37.jpeg")

print("=== OCR normal ===")
t1 = extrair_texto_arquivo(p)
print(t1[:600])
print("---")
d1 = parse_tac(t1)
print("parse1", d1.get("nome"), d1.get("rntrc"), d1.get("cnpj"), d1.get("categoria"))

print("\n=== OCR zoom 4x ===")
t2 = extrair_texto_arquivo(p, forcar_zoom=4.0)
print(t2[:800])
print("---")
d2 = parse_tac(t2)
print("parse2", d2.get("nome"), d2.get("rntrc"), d2.get("cnpj"), d2.get("categoria"))
tip, orig = classificar_arquivo_e_conteudo(p, t2)
print("tipo", tip, orig)
d3 = parsear_arquivo(p, t2, tip)
print("parsear", d3.get("nome"), d3.get("rntrc"), d3.get("cnpj"), d3.get("_tipo"))

Path("output/_ocr_antt_zoom.txt").write_text(t2 or "", encoding="utf-8")
print("salvo output/_ocr_antt_zoom.txt")
