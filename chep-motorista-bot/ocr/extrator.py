import json
import time
from playwright.sync_api import sync_playwright

def extrair_dados_coleta(caminhos_imagens=None):
    print(f"[SCRAPER] Iniciando extração direta do site de controle operacional...")
    
    # Busca os dados complementares (CPF e Placa) no banco de dados local
    try:
        with open("motoristas.json", "r", encoding="utf-8") as f:
            bd_motoristas = json.load(f)
    except FileNotFoundError:
        bd_motoristas = {}
        
    motoristas_conhecidos = list(bd_motoristas.keys())
    dados_extraidos = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto('https://controle-operacional-1njm.onrender.com/')
            
            print("[SCRAPER] Aguardando a tabela carregar...")
            page.wait_for_selector('table', timeout=15000)
            time.sleep(2) # Pausa extra para garantir renderização
            
            # Encontra as abas de datas e tenta clicar na aba de amanhã
            js_click_amanha = """
            () => {
                const spans = Array.from(document.querySelectorAll('span'));
                const hojeSpan = spans.find(s => s.textContent.includes('(HOJE)'));
                if (hojeSpan) {
                    let el = hojeSpan;
                    while(el && el.tagName !== 'BODY') {
                        if (el.nextElementSibling && el.parentElement.children.length > 5) {
                            el.nextElementSibling.click();
                            return true;
                        }
                        el = el.parentElement;
                    }
                }
                return false;
            }
            """
            
            print("[SCRAPER] Buscando a aba do dia seguinte...")
            clicou = page.evaluate(js_click_amanha)
            if clicou:
                print("[SCRAPER] Clicando na aba do dia seguinte...")
                time.sleep(4) # Aguarda a tabela de amanhã carregar
            else:
                print("[SCRAPER] ATENÇÃO: Não foi possível identificar a aba de amanhã automaticamente. Lendo a aba atual.")
            
            # Ler a tabela de forma precisa nas caixas de input
            print("[SCRAPER] Lendo as linhas da tabela...")
            linhas = page.locator('table tbody tr').all()
            for row in linhas:
                try:
                    motorista_raw = row.locator('select.driver-select').evaluate("sel => sel.options[sel.selectedIndex].text")
                    motorista_raw = motorista_raw.replace(' ▼', '').strip()
                    
                    motorista_nome = ""
                    if "SELECIONE" not in motorista_raw.upper():
                        # Verifica se o motorista selecionado bate com algum do banco de dados local
                        for known in motoristas_conhecidos:
                            if known in motorista_raw.upper():
                                motorista_nome = known
                                break
                    
                    delivery = row.locator('input.input-delivery').input_value().strip()
                    cliente = row.locator('input.input-cliente').input_value().strip()
                    
                    # Só adiciona se tiver motorista e delivery preenchidos
                    if motorista_nome and delivery:
                        coleta = {
                            "id_delivery": delivery,
                            "nome": motorista_nome,
                            "busca": cliente
                        }
                        
                        # Enriquece com CPF e placas do JSON
                        coleta['cpf'] = bd_motoristas[motorista_nome].get('cpf', '')
                        coleta['placa_cavalo'] = bd_motoristas[motorista_nome].get('placa_cavalo', '')
                        coleta['placa_reboque'] = bd_motoristas[motorista_nome].get('placa_reboque', '')
                        
                        dados_extraidos.append(coleta)
                except Exception as e:
                    print(f"[SCRAPER] Erro ao ler linha da tabela: {e}")
                    continue
            
            browser.close()
            
    except Exception as e:
        print(f"[SCRAPER] Erro fatal ao acessar o site: {e}")
        
    print(f"[SCRAPER] Foram extraídas {len(dados_extraidos)} entregas preenchidas do painel.")
    return dados_extraidos

