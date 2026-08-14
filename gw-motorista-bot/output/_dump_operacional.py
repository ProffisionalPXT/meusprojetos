"""Mapeia a aba Dados Operacionais do cadastro de motorista."""
from dotenv import load_dotenv

load_dotenv(override=True)

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

email = os.getenv("GW_EMAIL")
senha = os.getenv("GW_SENHA")
org = os.getenv("ORGANIZACAO", "PURM")
out = Path("output")
out.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=80)
    page = browser.new_page()
    page.goto(
        "https://webtrans.saas.gwsistemas.com.br/login",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    page.fill("#login", email)
    page.fill("#senha", senha)
    page.click("button.button-login")
    page.wait_for_timeout(2500)
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
    page.wait_for_timeout(2000)

    # Abre aba Dados Operacionais
    for sel in (
        "text=Dados Operacionais",
        'a:has-text("Dados Operacionais")',
        'td:has-text("Dados Operacionais")',
    ):
        try:
            page.locator(sel).first.click(timeout=4000)
            page.wait_for_timeout(1200)
            print("Aba aberta:", sel)
            break
        except Exception as e:
            print("falha aba", sel, e)

    page.screenshot(path=str(out / "map_operacional.png"), full_page=True)

    data = page.evaluate(
        """() => {
        const rows = [];
        // todos inputs/selects visíveis
        for (const e of document.querySelectorAll('input, select, textarea, a, img, button')) {
            const r = e.getBoundingClientRect();
            if (r.width < 2 && r.height < 2) continue;
            if (e.offsetParent === null && e.tagName !== 'A' && e.tagName !== 'IMG') {
                // pode estar em display; ainda captura se tem size
                if (r.width === 0) continue;
            }
            const tr = e.closest('tr');
            const label = tr ? tr.innerText.replace(/\\s+/g, ' ').trim().slice(0, 120) : '';
            rows.push({
                tag: e.tagName,
                type: e.type || '',
                name: e.name || '',
                id: e.id || '',
                value: (e.value || '').toString().slice(0, 40),
                src: (e.getAttribute('src') || '').slice(-60),
                href: (e.getAttribute('href') || '').slice(0, 80),
                onclick: (e.getAttribute('onclick') || '').slice(0, 120),
                title: e.title || e.alt || '',
                className: (e.className || '').toString().slice(0, 60),
                label,
                x: Math.round(r.x),
                y: Math.round(r.y),
                w: Math.round(r.width),
                h: Math.round(r.height),
            });
        }
        return rows;
        }"""
    )

    # filtra linhas que mencionam veiculo/carreta/placa/motorista
    keys = (
        "veic",
        "carret",
        "placa",
        "reboque",
        "truck",
        "cavalo",
        "tipo",
        "frota",
        "alocado",
        "cliente",
        "operac",
    )
    relevantes = [
        d
        for d in data
        if any(k in (d.get("label") or "").lower() for k in keys)
        or any(k in (d.get("name") or "").lower() for k in keys)
        or any(k in (d.get("id") or "").lower() for k in keys)
        or "localiza" in (d.get("onclick") or "").lower()
        or "lupa" in (d.get("src") or "").lower()
        or "search" in (d.get("src") or "").lower()
        or "find" in (d.get("src") or "").lower()
        or "..." in (d.get("value") or "")
    ]

    (out / "form_operacional_all.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "form_operacional_veiculo.json").write_text(
        json.dumps(relevantes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=== RELEVANTES (veículo/carreta/lookup) ===")
    for d in relevantes:
        print(
            f"{d['tag']:6} name={d['name']!r:25} id={d['id']!r:20} "
            f"onclick={d['onclick'][:50]!r} label={d['label'][:70]!r}"
        )

    print(f"\nTotal elementos: {len(data)} | relevantes: {len(relevantes)}")
    print("Salvo: output/form_operacional_veiculo.json + map_operacional.png")
    browser.close()
