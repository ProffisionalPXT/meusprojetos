"""Login no GW, tira screenshot e mantém o browser aberto."""
import os
import time
from dotenv import load_dotenv
from gw_automation.login import fazer_login_gw

load_dotenv()

os.makedirs("output", exist_ok=True)

email = os.getenv("GW_EMAIL")
senha = os.getenv("GW_SENHA")
organizacao = os.getenv("ORGANIZACAO", "PURM")

print("Fazendo login...")
page, context, browser, playwright = fazer_login_gw(email, senha, organizacao)

# Aguarda a home carregar e tira print
time.sleep(3)
shot = "output/posicao_atual.png"
page.screenshot(path=shot, full_page=True)
print(f"Screenshot salvo em: {shot}")
print(f"URL atual: {page.url}")
print(f"Titulo: {page.title()}")

# Mantém aberto para o usuário navegar e mandar prints
print("Browser aberto por 20 minutos. Navegue e mande os prints aqui no chat.")
try:
    time.sleep(20 * 60)
finally:
    browser.close()
    playwright.stop()
    print("Browser fechado.")
