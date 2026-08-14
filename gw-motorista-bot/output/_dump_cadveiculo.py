"""Dump dos names do formulário cadveiculo (preenchido ou vazio)."""
from dotenv import load_dotenv
load_dotenv(override=True)
import os, json
from pathlib import Path
from playwright.sync_api import sync_playwright

email = os.getenv("GW_EMAIL")
senha = os.getenv("GW_SENHA")
org = os.getenv("ORGANIZACAO", "PURM")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=50)
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
    page.goto("https://webtrans.saas.gwsistemas.com.br/cadveiculo?acao=iniciar", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    fields = page.evaluate("""() => {
      return [...document.querySelectorAll('input,select,textarea')].map(e => {
        const tr = e.closest('tr');
        return {
          tag: e.tagName, type: e.type||'', name: e.name||'', id: e.id||'',
          vis: !!(e.offsetWidth||e.offsetHeight),
          ro: !!e.readOnly, dis: !!e.disabled,
          label: tr ? tr.innerText.replace(/\\s+/g,' ').trim().slice(0,100) : ''
        };
      }).filter(x => x.vis && (x.name || x.id));
    }""")
    Path("output/form_cadveiculo_fields.json").write_text(json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8")
    for f in fields:
        print(f"{f['name'] or f['id']:30} | {f['label'][:70]}")
    browser.close()
    print("OK", len(fields))
