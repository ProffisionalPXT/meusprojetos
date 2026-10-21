# -*- coding: utf-8 -*-
"""Diagnóstico do caso JOAO VIEIRA CAJAIBA - RG, emissão, placa, prop, RNTRC."""
from pathlib import Path
import os

os.environ["OCR_ENGINE"] = "local"
os.environ["GEMINI_SE_VAZIO"] = "0"
os.environ["CONFIRMAR_DADOS"] = "0"

from ocr.local_ocr import extrair_texto_arquivo
from ocr.parsers_locais import parse_cnh, parse_crlv, parse_tac, parsear_arquivo
from ocr.tipos_documento import (
    classificar_arquivo,
    classificar_arquivo_e_conteudo,
    TipoDocumento,
)

files = sorted(Path("input/motorista").glob("*"))
for f in files:
    if f.name.startswith("COMO"):
        continue
    print("=" * 70)
    print(f.name)
    tip = classificar_arquivo(f)
    print("tipo_nome:", tip.value)
    try:
        t = extrair_texto_arquivo(f)
        print("texto_len:", len(t or ""))
        # salva texto para inspeção
        outp = Path("output") / f"_ocr_{f.stem[:40]}.txt"
        outp.write_text(t or "", encoding="utf-8", errors="replace")
        print("texto salvo:", outp)
        print("--- HEAD ---")
        print((t or "")[:1200])
        print("--- FIM HEAD ---")
        tip2, orig = classificar_arquivo_e_conteudo(f, t or "")
        print("tipo_final:", tip2.value, orig)
        d = parsear_arquivo(f, t or "", tip2)
        keys = [
            "nome", "cpf", "rg", "orgao_emissor", "data_emissao_cnh",
            "data_primeira_habilitacao", "validade_cnh", "cnh", "categoria_cnh",
            "placa", "renavam", "chassi", "proprietario_nome", "proprietario_cpf_cnpj",
            "rntrc", "cnpj", "cidade", "uf", "marca_modelo_versao",
        ]
        for k in keys:
            if d.get(k):
                print(f"  {k}: {d.get(k)!r}")
        print("  _duvida:", d.get("_duvida"))
        print("  _fonte:", d.get("_fonte"))
    except Exception as e:
        import traceback
        print("ERR", e)
        traceback.print_exc()
    print()
