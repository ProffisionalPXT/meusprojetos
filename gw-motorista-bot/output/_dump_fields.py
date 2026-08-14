from dotenv import load_dotenv
load_dotenv(override=True)
import os, json
from pathlib import Path
from playwright.sync_api import sync_playwright

email = os.getenv("GW_EMAIL")
senha = os.getenv("GW_SENHA")
org = os.getenv("ORGANIZACAO", "PURM")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=100)
    page = browser.new_page()
    page.goto("https://webtrans.saas.gwsistemas.com.br/login", wait_until="domcontentloaded", timeout=60000)
    page.fill("#login", email)
    page.fill("#senha", senha)
    page.click("button.button-login")
    page.wait_for_timeout(3000)
    try:
        page.click(f"text={org}", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(2000)
    page.goto(
        "https://webtrans.saas.gwsistemas.com.br/cadmotorista?acao=iniciar",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    page.wait_for_timeout(2500)

    # click Documentação too and dump both
    fields = page.evaluate(
        """() => {
        const els = [...document.querySelectorAll('input, select, textarea')];
        return els.map(e => {
            const tr = e.closest('tr');
            const label = tr ? tr.innerText.slice(0, 100).replace(/\\s+/g, ' ') : '';
            return {
                tag: e.tagName,
                type: e.type || '',
                name: e.name || '',
                id: e.id || '',
                ph: e.placeholder || '',
                vis: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length),
                disabled: !!e.disabled,
                readonly: !!e.readOnly,
                label
            };
        }).filter(x => x.vis);
        }"""
    )
    Path("output/form_fields_pessoais.json").write_text(
        json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("PESSOAIS", len(fields))
    for f in fields:
        if f["name"] or f["id"]:
            print(f"  {f['name'] or f['id']}: {f['label'][:70]}")

    # Documentação tab
    try:
        page.click("text=Documentação", timeout=5000)
        page.wait_for_timeout(1000)
    except Exception as e:
        print("tab doc", e)

    fields2 = page.evaluate(
        """() => {
        const els = [...document.querySelectorAll('input, select, textarea')];
        return els.map(e => {
            const tr = e.closest('tr');
            const label = tr ? tr.innerText.slice(0, 100).replace(/\\s+/g, ' ') : '';
            return {
                tag: e.tagName,
                type: e.type || '',
                name: e.name || '',
                id: e.id || '',
                vis: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length),
                label
            };
        }).filter(x => x.vis);
        }"""
    )
    Path("output/form_fields_doc.json").write_text(
        json.dumps(fields2, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("DOC", len(fields2))
    for f in fields2:
        if f["name"] or f["id"]:
            print(f"  {f['name'] or f['id']}: {f['label'][:70]}")

    # Operacional
    try:
        page.click("text=Dados Operacionais", timeout=5000)
        page.wait_for_timeout(1000)
    except Exception as e:
        print("tab op", e)
    fields3 = page.evaluate(
        """() => {
        const els = [...document.querySelectorAll('input, select, textarea, a, img')];
        return els.slice(0, 80).map(e => {
            const tr = e.closest('tr');
            const label = tr ? tr.innerText.slice(0, 80).replace(/\\s+/g, ' ') : '';
            return {
                tag: e.tagName,
                type: e.type || '',
                name: e.name || '',
                id: e.id || '',
                src: (e.src||'').slice(-40),
                onclick: (e.getAttribute('onclick')||'').slice(0,80),
                vis: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length),
                label
            };
        }).filter(x => x.vis && (x.name || x.id || x.onclick || x.tag==='IMG' || x.tag==='A'));
        }"""
    )
    Path("output/form_fields_oper.json").write_text(
        json.dumps(fields3, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("OPER sample")
    for f in fields3[:40]:
        print(f"  {f}")

    browser.close()
    print("done")
