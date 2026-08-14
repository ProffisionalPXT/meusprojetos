"""
Testa só OCR local + confirmação humana (sem abrir o GW).

  python testar_ocr_local.py
  python testar_ocr_local.py --sem-confirmar
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ.setdefault("OCR_ENGINE", "local")
os.environ.setdefault("CONFIRMAR_DADOS", "1")

from ocr.confirmar import confirmar_dados_caso
from ocr.extrair_dados import extrair_dados_do_caso, motor_ocr
from utils.paths import garantir_pastas
from utils.receber_fotos import listar_casos, resumo_casos


def main() -> None:
    garantir_pastas()
    sem_conf = "--sem-confirmar" in sys.argv
    if sem_conf:
        os.environ["CONFIRMAR_DADOS"] = "0"

    print(f"=== Teste OCR local (engine={motor_ocr()}) ===\n")
    casos = listar_casos()
    print(resumo_casos(casos))
    if not casos:
        print("Nenhum caso em input/")
        return

    for caso in casos:
        print(f"\n--- {caso.nome} ---")
        dados = extrair_dados_do_caso(caso)
        if not sem_conf:
            dados = confirmar_dados_caso(dados)
            if dados is None:
                print("Cancelado.")
                continue
        print("\nResumo final OK.")


if __name__ == "__main__":
    main()
