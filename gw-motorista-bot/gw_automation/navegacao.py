"""
Fase 2 - Navegar até Novo Motorista.

Caminho real (prints):
  menu -> Cadastros -> Operacional -> Motoristas
  -> Consulta de Motoristas (codTela=60)
  -> botão "Novo Motorista"
  -> cadmotorista?acao=iniciar
"""
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from gw_automation.urls import CONSULTA_MOTORISTAS, MENU, NOVO_MOTORISTA


def ir_para_novo_motorista(page: Page, usar_url_direta: bool = False) -> None:
    """
    Abre o formulário de Novo Motorista.

    usar_url_direta=True: vai direto em cadmotorista?acao=iniciar (mais rápido).
    False (padrão): segue o menu como o usuário faz.
    """
    if usar_url_direta:
        print("[Fase 2] Abrindo Novo Motorista por URL direta...")
        page.goto(NOVO_MOTORISTA)
        page.wait_for_load_state("networkidle")
        print("[Fase 2] Formulário cadmotorista aberto.")
        return

    print("[Fase 2] Cadastros -> Operacional -> Motoristas -> Novo Motorista")

    # Garante que estamos no menu (pós-login)
    if "/menu" not in (page.url or ""):
        try:
            page.goto(MENU, wait_until="networkidle", timeout=30000)
        except Exception:
            pass

    _abrir_submenu_cadastros_operacional(page)
    _clicar_item("Motoristas", page)

    page.wait_for_load_state("networkidle")
    # Tela: Consulta de Motoristas
    print(f"[Fase 2] URL consulta: {page.url}")

    _clicar_novo_motorista(page)
    page.wait_for_load_state("networkidle")
    print(f"[Fase 2] Formulário aberto: {page.url}")


def ir_para_consulta_motoristas(page: Page) -> None:
    """Atalho: abre a consulta de motoristas (codTela=60)."""
    page.goto(CONSULTA_MOTORISTAS)
    page.wait_for_load_state("networkidle")


def _abrir_submenu_cadastros_operacional(page: Page) -> None:
    """Abre Cadastros e depois Operacional (menus com hover)."""
    # Topo: Cadastros
    for seletor in (
        'a:has-text("Cadastros")',
        'span:has-text("Cadastros")',
        'text=Cadastros',
        'li:has-text("Cadastros")',
    ):
        try:
            loc = page.locator(seletor).first
            loc.hover(timeout=5000)
            page.wait_for_timeout(400)
            loc.click(timeout=3000)
            print("[Fase 2] Menu: Cadastros")
            break
        except Exception:
            continue
    else:
        raise RuntimeError("Não encontrou o menu 'Cadastros'.")

    page.wait_for_timeout(500)

    # Submenu: Operacional
    for seletor in (
        'a:has-text("Operacional")',
        'li:has-text("Operacional")',
        'span:has-text("Operacional")',
        'text=Operacional',
    ):
        try:
            loc = page.locator(seletor).first
            loc.hover(timeout=5000)
            page.wait_for_timeout(400)
            # só hover pode bastar para abrir o 3º nível; tenta click também
            try:
                loc.click(timeout=2000)
            except Exception:
                pass
            print("[Fase 2] Menu: Operacional")
            page.wait_for_timeout(500)
            return
        except Exception:
            continue

    raise RuntimeError("Não encontrou o submenu 'Operacional'.")


def _clicar_item(texto: str, page: Page) -> None:
    for seletor in (
        f'a:has-text("{texto}")',
        f'li:has-text("{texto}")',
        f'span:has-text("{texto}")',
        f'text={texto}',
    ):
        try:
            page.locator(seletor).first.click(timeout=5000)
            print(f"[Fase 2] Clicou: {texto}")
            return
        except PlaywrightTimeoutError:
            continue
    raise RuntimeError(f"Não encontrou o item de menu '{texto}'.")


def _clicar_novo_motorista(page: Page) -> None:
    """Botão azul 'Novo Motorista' na Consulta de Motoristas."""
    for seletor in (
        'button:has-text("Novo Motorista")',
        'a:has-text("Novo Motorista")',
        'input[value="Novo Motorista"]',
        'text=Novo Motorista',
    ):
        try:
            page.locator(seletor).first.click(timeout=6000)
            print("[Fase 2] Botão: Novo Motorista")
            return
        except PlaywrightTimeoutError:
            continue

    # Fallback: URL direta do formulário
    print("[Fase 2] Botão não encontrado - abrindo URL direta do formulário...")
    page.goto(NOVO_MOTORISTA)
