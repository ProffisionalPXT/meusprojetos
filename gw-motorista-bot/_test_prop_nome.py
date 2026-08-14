# -*- coding: utf-8 -*-
from pathlib import Path
from ocr.local_ocr import extrair_texto_arquivo
from ocr.parsers_locais import (
    parse_crlv,
    parse_tac,
    _limpar_nome_proprietario_final,
    _nome_prop_parece_lixo,
)

assert _nome_prop_parece_lixo("CPEY CHD)")
assert _nome_prop_parece_lixo("CPEY CHD")
assert not _nome_prop_parece_lixo("CLEONALDO FERREIRA CARNEIRO")

print(
    "clean1",
    _limpar_nome_proprietario_final(
        'FLEE ATS =" I CLEONALDO FERREIRA CARNEIRO ME'
    ),
)
print(
    "clean2",
    _limpar_nome_proprietario_final(
        "TRANSPORTADORES RODOVIARIOS DE CARGAS CLEONALDO FERREIRA CARNEIRO CADASTRADO DESDE"
    ),
)

t_tac = extrair_texto_arquivo(
    Path("input/motorista/WhatsApp Image 2026-07-15 at 10.44.28.jpeg")
)
d = parse_tac(t_tac)
print("TAC", d.get("nome"), d.get("rntrc"), d.get("cnpj"))

t_crlv = extrair_texto_arquivo(
    Path("input/motorista/WhatsApp Image 2026-07-15 at 10.44.29.jpeg")
)
d2 = parse_crlv(t_crlv)
print("CRLV", d2.get("proprietario_nome"), d2.get("proprietario_cpf_cnpj"))

nome = (d.get("nome") or d2.get("proprietario_nome") or "").upper()
assert "CLEONALDO" in nome, nome
assert "CPEY" not in nome
assert "TRANSPORTADORES" not in nome
print("OK")
