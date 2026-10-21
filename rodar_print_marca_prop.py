"""
DRY-RUN: abre cadastro de veículo e:
  1) Clica ... Marca -> pega o PRIMEIRO da lista (print)
  2) Replica em Modelo + Marca de baixo
  3) Clica ... Proprietário -> pega o PRIMEIRO da lista (print)
  4) Preenche tipo/cap/tara básicos
  5) Prints em cada etapa

NÃO salva.
"""
from __future__ import annotations

import os
import time
import traceback

from dotenv import load_dotenv
from dados.gabriel_mock import dados_gabriel
from gw_automation.login import lancar_browser
from gw_automation.salvar import tirar_print
from gw_automation.veiculo import preencher_form_veiculo_completo
from utils.paths import OUTPUT_DIR, garantir_pastas

load_dotenv(override=True)
os.environ["DRY_RUN"] = "1"


def limpar_prints() -> None:
    pasta = OUTPUT_DIR / "prints"
    pasta.mkdir(parents=True, exist_ok=True)
    for f in pasta.glob("*"):
        try:
            f.unlink()
        except Exception:
            pass


def main() -> None:
    garantir_pastas()
    limpar_prints()
    email = os.getenv("GW_EMAIL")
    senha = os.getenv("GW_SENHA")
    org = os.getenv("ORGANIZACAO", "PURM")
    dados = dados_gabriel()

    print("=== Print: 1ª marca + 1º proprietário (DRY-RUN) ===\n")
    pw = browser = page = None
    try:
        pw, browser, context, page = lancar_browser()

        page.goto(
            "https://webtrans.saas.gwsistemas.com.br/login",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.fill("#login", email)
        page.fill("#senha", senha)
        tirar_print(page, "01_login")
        page.click("button.button-login")
        page.wait_for_timeout(2500)
        try:
            page.click(f"text={org}", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        tirar_print(page, "02_purm")

        page.goto(
            "https://webtrans.saas.gwsistemas.com.br/cadveiculo?acao=iniciar",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_timeout(1500)
        tirar_print(page, "03_veiculo_vazio")

        preencher_form_veiculo_completo(page, dados.veiculo, proprietario=dados.proprietario)
        page.wait_for_timeout(800)
        tirar_print(page, "04_veiculo_marca_prop_preenchidos")

        prints = sorted((OUTPUT_DIR / "prints").glob("*.png"))
        print(f"\nPrints ({len(prints)}):")
        for p in prints:
            print(f"  - {p.name}")
        print("\nNada foi salvo. Prints em output/prints/ (sem janela na tela).")
        time.sleep(2)
    except Exception as e:
        print("ERRO", e)
        traceback.print_exc()
        if page:
            try:
                tirar_print(page, "99_erro")
            except Exception:
                pass
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()


if __name__ == "__main__":
    main()
