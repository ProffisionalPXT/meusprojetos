from playwright.sync_api import sync_playwright
import os

os.makedirs("output", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(
        "https://webtrans.saas.gwsistemas.com.br/login",
        wait_until="networkidle",
        timeout=60000,
    )
    print("URL:", page.url)
    print("TITLE:", page.title())

    with open("output/login_page.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    for i, el in enumerate(page.locator("input").all()):
        info = el.evaluate(
            """e => ({
            type: e.type, name: e.name, id: e.id,
            placeholder: e.placeholder,
            className: e.className,
            outer: e.outerHTML.slice(0, 250)
        })"""
        )
        print(f"INPUT[{i}]:", info)

    for i, el in enumerate(page.locator("button").all()):
        info = el.evaluate(
            """e => ({
            type: e.type, id: e.id, text: (e.innerText||"").trim(),
            className: e.className, outer: e.outerHTML.slice(0, 250)
        })"""
        )
        print(f"BUTTON[{i}]:", info)

    # submit inputs
    for i, el in enumerate(page.locator("input[type=submit], input[type=button]").all()):
        info = el.evaluate(
            """e => ({
            type: e.type, id: e.id, value: e.value,
            className: e.className, outer: e.outerHTML.slice(0, 250)
        })"""
        )
        print(f"SUBMIT[{i}]:", info)

    print("FORMS:", page.locator("form").count())
    page.screenshot(path="output/login_page.png", full_page=True)
    print("done")
    browser.close()
