"""Testa só: abrir Localizar proprietário e clicar no 1º nome."""
from dotenv import load_dotenv
load_dotenv(override=True)
import os, time
from playwright.sync_api import sync_playwright
from gw_automation.salvar import tirar_print
from utils.paths import OUTPUT_DIR, garantir_pastas

os.environ["DRY_RUN"] = "1"
garantir_pastas()

email = os.getenv("GW_EMAIL")
senha = os.getenv("GW_SENHA")
org = os.getenv("ORGANIZACAO", "PURM")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=150)
    page = browser.new_page()
    page.goto("https://webtrans.saas.gwsistemas.com.br/login", wait_until="domcontentloaded", timeout=60000)
    page.fill("#login", email)
    page.fill("#senha", senha)
    page.click("button.button-login")
    page.wait_for_timeout(2500)
    try:
        page.click(f"text={org}", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(1500)
    page.goto(
        "https://webtrans.saas.gwsistemas.com.br/cadveiculo?acao=iniciar",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    page.wait_for_timeout(1500)

    # abre popup proprietário
    with page.context.expect_page(timeout=8000) as nova:
        page.click("#localiza_proprietario")
    popup = nova.value
    popup.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(800)
    try:
        popup.locator('button:has-text("Pesquisar"), input[value*="Pesquis"]').first.click(timeout=2000)
    except Exception:
        pass
    popup.wait_for_timeout(1000)
    tirar_print(popup, "prop_lista_aberta")

    # dump links
    info = popup.evaluate("""() => {
      const out = [];
      document.querySelectorAll('table a, table tr').forEach((el, i) => {
        if (i > 25) return;
        const t = (el.innerText||'').trim().slice(0,100);
        if (!t) return;
        out.push({tag: el.tagName, t, href: el.getAttribute('href')||'', onclick: (el.getAttribute('onclick')||'').slice(0,80)});
      });
      return out;
    }""")
    for row in info:
        print(row)

    # clica primeiro link de dados na tabela
    clicked = False
    links = popup.locator("table tbody tr td a, table tr td a")
    n = links.count()
    print("links count", n)
    for i in range(min(n, 20)):
        a = links.nth(i)
        txt = (a.inner_text(timeout=500) or "").strip()
        up = txt.upper()
        print(f"  link[{i}] = {txt!r}")
        if not txt or "LOCALIZAR" in up or up in ("NOME", "CIDADE", "UF"):
            continue
        if "NOME" in up and "CIDADE" in up:
            continue
        a.click(timeout=3000)
        print("CLICKED", txt)
        clicked = True
        break

    page.wait_for_timeout(1500)
    try:
        val = page.input_value('input[name="nome_prop"]')
    except Exception:
        val = "?"
    print("nome_prop after =", val)
    tirar_print(page, "prop_apos_selecao")
    time.sleep(5)
    browser.close()
