"""
Preenche o cadastro com dados MOCK (como se o Gemini tivesse lido)
e tira print a cada etapa. DRY-RUN: NÃO salva.

Etapas de print:
  01_login_tela
  02_login_preenchido
  03_purm
  04_menu
  05_cadastro_aberto
  06_dados_pessoais_preenchidos
  07_documentacao_preenchida
  08_operacional
  09_apos_veiculo_proprietario
  10_final_sem_salvar
"""
from __future__ import annotations

import os
import sys
import time
import traceback

from dotenv import load_dotenv

from dados.gabriel_mock import dados_gabriel
from gw_automation.login import browser_mode, lancar_browser
from gw_automation.motorista import preencher_dados_pessoais, preencher_documentacao
from gw_automation.navegacao import ir_para_novo_motorista
from gw_automation.operacional import vincular_veiculos
from gw_automation.salvar import tirar_print
from utils.paths import OUTPUT_DIR, garantir_pastas

load_dotenv(override=True)

# Força dry-run
os.environ["DRY_RUN"] = "1"


def limpar_prints() -> None:
    pasta = OUTPUT_DIR / "prints"
    pasta.mkdir(parents=True, exist_ok=True)
    for f in pasta.glob("*"):
        try:
            f.unlink()
        except Exception:
            pass
    print(f"[Prints] Pasta limpa: {pasta}")


def main() -> None:
    garantir_pastas()
    limpar_prints()

    email = os.getenv("GW_EMAIL")
    senha = os.getenv("GW_SENHA")
    org = os.getenv("ORGANIZACAO", "PURM")
    if not email or not senha:
        print("Falta GW_EMAIL/GW_SENHA no .env")
        return

    dados = dados_gabriel()
    m = dados.motorista
    print("=== MOCK Gemini (gabriel) ===")
    print(f"  Nome: {m.nome}")
    print(f"  CPF: {m.cpf} | Nasc: {m.data_nascimento} | Nat: {m.naturalidade}")
    print(f"  Pai: {m.nome_pai}")
    print(f"  Mãe: {m.nome_mae}")
    print(f"  RG: {m.rg} | Órgão: {m.orgao_emissor}")
    print(f"  CNH: {m.cnh} | Val: {m.validade_cnh} | Cat: {m.categoria_cnh} | 1ª: {m.data_primeira_habilitacao}")
    print(f"  End: {m.endereco}, {m.bairro} - {m.cidade}/{m.uf} CEP {m.cep}")
    print(f"  Veículo: {dados.veiculo.tipo} {dados.veiculo.placa} cap/tara={dados.veiculo.cap_carga}")
    print(f"  Prop: {dados.proprietario.nome} RNTRC={dados.rntrc_tac}")
    print("  DRY_RUN=1 - NÃO salva\n")

    playwright = browser = page = None
    try:
        playwright, browser, context, page = lancar_browser()

        # --- LOGIN ---
        print("[1] Abrindo login...")
        page.goto(
            "https://webtrans.saas.gwsistemas.com.br/login",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_timeout(800)
        tirar_print(page, "01_login_tela")

        page.fill("#login", email)
        page.fill("#senha", senha)
        page.wait_for_timeout(400)
        tirar_print(page, "02_login_preenchido")

        page.click("button.button-login")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # --- PURM ---
        print(f"[2] Selecionando organização {org}...")
        try:
            page.click(f"text={org}", timeout=10000)
            print(f"  [OK] {org}")
        except Exception as e:
            print(f"  [!] org: {e}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        tirar_print(page, "03_purm")

        # menu
        try:
            if "/menu" not in (page.url or ""):
                page.goto(
                    "https://webtrans.saas.gwsistemas.com.br/menu",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                page.wait_for_timeout(800)
        except Exception:
            pass
        tirar_print(page, "04_menu")

        # --- NOVO MOTORISTA ---
        print("[3] Abrindo cadastro de motorista...")
        ir_para_novo_motorista(page, usar_url_direta=True)
        page.wait_for_timeout(1000)
        tirar_print(page, "05_cadastro_aberto")

        # --- DADOS PESSOAIS ---
        print("[4] Preenchendo Dados Pessoais...")
        preencher_dados_pessoais(page, dados.motorista)
        page.wait_for_timeout(600)
        tirar_print(page, "06_dados_pessoais_preenchidos")

        # --- DOCUMENTAÇÃO ---
        print("[5] Preenchendo Documentação...")
        preencher_documentacao(page, dados.motorista)
        page.wait_for_timeout(600)
        tirar_print(page, "07_documentacao_preenchida")

        # --- OPERACIONAL / VEÍCULO / PROPRIETÁRIO ---
        print("[6] Dados Operacionais + Veículo/Proprietário...")
        # print da aba antes
        try:
            page.locator("text=Dados Operacionais").first.click(timeout=4000)
            page.wait_for_timeout(600)
        except Exception:
            pass
        tirar_print(page, "08_operacional_antes")

        vincular_veiculos(
            page,
            veiculo=dados.veiculo,
            carreta=dados.carreta,
            proprietario=dados.proprietario,
            tipo_motorista=dados.motorista.tipo_motorista or "Carreteiro",
        )
        page.wait_for_timeout(800)
        tirar_print(page, "09_apos_veiculo_proprietario")

        # final - NÃO salva
        print("[7] DRY-RUN final (sem Salvar)...")
        tirar_print(page, "10_final_sem_salvar")

        prints = sorted((OUTPUT_DIR / "prints").glob("*.png"))
        print("\n=== Concluído (nada gravado) ===")
        print(f"Prints ({len(prints)}):")
        for p in prints:
            print(f"  - {p.name}")

        if browser_mode() == "headless":
            print("\nHeadless - prints em output/prints/ (fechando em 2s).")
            time.sleep(2)
        else:
            print("\nMantendo browser 15s...")
            time.sleep(15)

    except Exception as e:
        print(f"ERRO: {e}")
        traceback.print_exc()
        if page:
            try:
                tirar_print(page, "99_ERRO")
            except Exception:
                pass
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
