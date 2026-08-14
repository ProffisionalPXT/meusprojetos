# gw_automation/login.py
"""
Login no GW Webtrans.

BROWSER_MODE no .env (não atrapalha a tela):
  headless   - sem janela (padrão). Prints e automação funcionam igual.
  minimized  - janela existe mas minimizada na barra de tarefas.
  visible    - janela na frente (só para debug / ver o robô).
"""
from __future__ import annotations

import os
from typing import Any, Tuple

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


def browser_mode() -> str:
    """headless | minimized | visible"""
    # HEADLESS=1 ainda funciona (legado)
    h = (os.getenv("HEADLESS") or "").strip().lower()
    if h in ("1", "true", "yes", "sim"):
        return "headless"
    if h in ("0", "false", "no", "nao", "não"):
        return "visible"
    m = (os.getenv("BROWSER_MODE") or "headless").strip().lower()
    if m in ("headless", "minimized", "min", "minimizado", "visible", "visivel", "visível", "headed"):
        if m in ("min", "minimizado"):
            return "minimized"
        if m in ("visivel", "visível", "headed"):
            return "visible"
        return m
    return "headless"


def lancar_browser(playwright: Playwright | None = None) -> Tuple[Playwright, Browser, BrowserContext, Page]:
    """
    Abre Chromium conforme BROWSER_MODE.
    Retorna (playwright, browser, context, page).
    Se playwright for None, cria um novo.
    """
    own_pw = playwright is None
    pw = playwright or sync_playwright().start()
    mode = browser_mode()

    # SLOW_MO: atraso em CADA ação do Playwright (ms).
    # Padrão 0 - 250 faz o robô "pensar" 5s entre digitar e clicar.
    # Para debug lento: SLOW_MO=100 no .env
    slow = int(os.getenv("SLOW_MO", "0") or "0")
    args = [
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    if mode == "headless":
        print("[Browser] Modo HEADLESS - sem janela (não ocupa a tela).")
        browser = pw.chromium.launch(headless=True, slow_mo=slow, args=args)
    elif mode == "minimized":
        print("[Browser] Modo MINIMIZADO - janela na barra de tarefas.")
        # Chrome/Chromium no Windows: inicia minimizado
        browser = pw.chromium.launch(
            headless=False,
            slow_mo=slow,
            args=args + ["--start-minimized"],
        )
    else:
        print("[Browser] Modo VISÍVEL - janela na tela (debug).")
        browser = pw.chromium.launch(headless=False, slow_mo=slow, args=args)

    # viewport fixo (headless também)
    context = browser.new_context(
        viewport={"width": 1366, "height": 768},
        locale="pt-BR",
    )
    page = context.new_page()

    def _on_dialog(dialog) -> None:
        msg = dialog.message or ""
        print(f"[GW alerta] {msg}")
        low = msg.lower()
        # "Motorista já cadastrado, deseja visualizá-lo?" -> OK (abre o cadastro)
        if "visualiz" in low or "já cadastrad" in low or "ja cadastrad" in low:
            print("[GW alerta] -> aceitando OK para abrir motorista existente")
            try:
                dialog.accept()
            except Exception:
                pass
            return
        try:
            from gw_automation.salvar import detectar_ja_cadastrado

            tipo = detectar_ja_cadastrado(msg)
            if tipo:
                print(f"[GW alerta] -> duplicidade ({tipo}) - OK")
        except Exception:
            pass
        try:
            dialog.accept()
        except Exception:
            pass

    page.on("dialog", _on_dialog)
    return pw, browser, context, page


def fazer_login_gw(
    email: str, senha: str, organizacao: str = "PURM"
) -> Tuple[Page, BrowserContext, Browser, Playwright]:
    """
    Faz login no GW Webtrans e seleciona a organização.
    Retorna page, context, browser, playwright.
    """
    playwright, browser, context, page = lancar_browser()

    print("[1/4] Abrindo página de login...")
    page.goto(
        "https://webtrans.saas.gwsistemas.com.br/login",
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.fill("#login", email)
    page.fill("#senha", senha)
    page.click("button.button-login")

    print("[2/4] Aguardando tela de seleção de organização...")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        page.wait_for_timeout(2000)

    try:
        page.click(f"text={organizacao}", timeout=8000)
        print(f"[3/4] Organização '{organizacao}' selecionada.")
    except Exception:
        print(f"[AVISO] Não encontrou organização '{organizacao}' automaticamente.")

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        page.wait_for_timeout(1000)
    print("[4/4] Login concluído com sucesso!")

    return page, context, browser, playwright
