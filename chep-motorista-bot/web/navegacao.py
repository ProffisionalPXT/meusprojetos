import asyncio
from playwright.async_api import async_playwright

async def executar_preenchimento_async(dados_extraidos, login_user, login_pass):
    coletas_pendentes = []
    
    async with async_playwright() as p:
        print(f"[WEB] Iniciando Playwright para o perfil {login_user}...")
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context(viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        print("[WEB] Acessando CHEP...")
        try:
            await page.goto("https://chep-aztms-pr1.jdadelivers.com/tm/framework/Frame.jsp", timeout=30000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[WEB] Erro ao acessar a página: {e}")

        # Login
        try:
            target_frame = page.frame('results')
            if target_frame:
                print("[WEB] Preenchendo login...")
                user_input = target_frame.locator('input[type="text"].inputField:visible').first
                pass_input = target_frame.locator('input#dspLoginPassword:visible').first
                
                await user_input.wait_for(state='visible', timeout=10000)
                await pass_input.wait_for(state='visible', timeout=10000)
                
                await user_input.focus()
                await user_input.fill(login_user)
                await pass_input.focus()
                await pass_input.fill(login_pass)
                
                submit_button = target_frame.locator('a img[src*="login"], a:has-text("Login"), input[type="submit"], button:visible').first
                if await submit_button.is_visible():
                    await submit_button.click()
                else:
                    await pass_input.press('Enter')
                
                print("[WEB] Logou! Aguardando menu...")
                
                # Aguarda até 20 segundos pelo link do Smartbench em qualquer frame
                sb_link = None
                for tentativa in range(10):
                    for f in page.frames:
                        locator = f.locator('a:has-text("Transportation Smartbench")').first
                        if await locator.count() > 0 and await locator.is_visible():
                            sb_link = locator
                            break
                    if sb_link:
                        break
                    await page.wait_for_timeout(2000)
                
                if sb_link:
                    print("[WEB] Clicando em Smartbench...")
                    try:
                        async with page.context.expect_page(timeout=5000) as new_page_info:
                            await sb_link.click()
                        new_page = await new_page_info.value
                        target_page = new_page
                    except Exception:
                        try: await sb_link.click()
                        except: pass
                        target_page = page
                        
                    print("[WEB] Aguardando o Smartbench carregar (pode levar alguns segundos)...")
                        
                    prog_amanha = None
                    for tentativa in range(15):
                        for f in target_page.frames:
                            locator = f.locator('td:has-text("PROGRAMAÇÃO AMANHÃ")').first
                            if await locator.count() > 0 and await locator.is_visible():
                                prog_amanha = locator
                                break
                        if prog_amanha:
                            break
                        await target_page.wait_for_timeout(2000)
                    
                    if prog_amanha:
                        print("[WEB] Clicando em PROGRAMAÇÃO AMANHÃ no menu lateral...")
                        await prog_amanha.click()
                        await target_page.wait_for_timeout(1000)
                        await prog_amanha.dblclick()
                        
                        print("[WEB] Aguardando a tabela carregar (espera inteligente)...")
                        results_frame = None
                        for tentativa in range(15):
                            for f in target_page.frames:
                                if await f.locator('table.listTable').count() > 0 or await f.locator('text="ID da carga"').count() > 0:
                                    results_frame = f
                                    break
                            if results_frame:
                                break
                            await target_page.wait_for_timeout(1000)
                            
                        if results_frame:
                            await target_page.wait_for_timeout(500) # Pausa rápida pós-carregamento
                            
                            # ======== MAPEAMENTO DINÂMICO ========
                            col_map = {'nome': 3, 'cpf': 4, 'placa_cavalo': 5, 'placa_reboque': -1}
                            try:
                                headers = await results_frame.locator('table.listTable').first.locator('thead th').all_text_contents()
                                for i, h in enumerate(headers):
                                    h_clean = h.strip().lower()
                                    if 'do reboque' in h_clean and 'placa' not in h_clean:
                                        col_map['nome'] = i
                                    elif 'carteira de habilitação' in h_clean or 'cpf' in h_clean:
                                        col_map['cpf'] = i
                                    elif 'ativo' in h_clean or 'cavalo' in h_clean:
                                        col_map['placa_cavalo'] = i
                                    elif 'placa do reboque' in h_clean or 'da placa' in h_clean:
                                        col_map['placa_reboque'] = i
                                print(f"[WEB] Mapa de colunas dinâmico: {col_map}")
                            except Exception as e:
                                print(f"[WEB] Aviso ao mapear colunas: {e}. Usando posições padrão.")
                            # =====================================
                            
                            qtd_linhas = await results_frame.locator('tr').count()
                            print(f"[WEB] Tabela carregada com {qtd_linhas} linhas. Iniciando preenchimento...")
                            
                            for d in dados_extraidos:
                                # Verifica se é modo Banco de Dados (tem id_delivery) ou WhatsApp (tem busca)
                                termo_busca = d.get('id_delivery') if 'id_delivery' in d else d.get('busca')
                                print(f"[WEB] Procurando por: {termo_busca}")
                                
                                # Busca APENAS nas linhas da tabela principal (que tem mais de 15 colunas)
                                rows_match = await results_frame.locator(f'tr:has-text("{termo_busca}")').all()
                                row = None
                                for r in rows_match:
                                    if await r.locator(':scope > td').count() >= 15:
                                        row = r
                                        break
                                
                                if row is not None:
                                    print(f"[WEB] -> Encontrou a linha para {termo_busca}! Verificando se já está preenchida...")
                                    
                                    # Auditoria completa
                                    precisa_preencher = False
                                    campos_verificar = [('nome', col_map['nome']), ('cpf', col_map['cpf']), ('placa_cavalo', col_map['placa_cavalo'])]
                                    if col_map['placa_reboque'] != -1:
                                        campos_verificar.append(('placa_reboque', col_map['placa_reboque']))
                                        
                                    for chave, col_idx in campos_verificar:
                                        if chave in d and d[chave]:
                                            txt_atual = await row.locator(':scope > td').nth(col_idx).inner_text(timeout=1000)
                                            if not txt_atual.strip():
                                                precisa_preencher = True
                                                break
                                                
                                    if not precisa_preencher:
                                        print(f"[WEB] -> A coleta {termo_busca} já está preenchida com todos os dados. Pulando digitação...")
                                    else:
                                        # Coluna Nome do Motorista
                                        if 'nome' in d and d['nome']:
                                            cell_nome = row.locator(':scope > td').nth(col_map['nome'])
                                            await cell_nome.scroll_into_view_if_needed()
                                            await cell_nome.dblclick()
                                            await target_page.wait_for_timeout(100)
                                            await target_page.keyboard.type(d['nome'])
                                            await target_page.wait_for_timeout(50)
                                            await target_page.keyboard.press('Enter')
                                        
                                        # Coluna CPF
                                        if 'cpf' in d and d['cpf']:
                                            cell_cpf = row.locator(':scope > td').nth(col_map['cpf'])
                                            await cell_cpf.scroll_into_view_if_needed()
                                            await cell_cpf.dblclick()
                                            await target_page.wait_for_timeout(100)
                                            await target_page.keyboard.type(d['cpf'])
                                            await target_page.wait_for_timeout(50)
                                            await target_page.keyboard.press('Enter')
                                            
                                        # Coluna Placa Cavalo
                                        if 'placa_cavalo' in d and d['placa_cavalo']:
                                            cell_placa = row.locator(':scope > td').nth(col_map['placa_cavalo'])
                                            await cell_placa.scroll_into_view_if_needed()
                                            await cell_placa.dblclick()
                                            await target_page.wait_for_timeout(100)
                                            await target_page.keyboard.type(d['placa_cavalo'])
                                            await target_page.wait_for_timeout(50)
                                            await target_page.keyboard.press('Enter')
                                            
                                        # Coluna Placa Reboque
                                        if 'placa_reboque' in d and d['placa_reboque'] and col_map['placa_reboque'] != -1:
                                            cell_reboque = row.locator(':scope > td').nth(col_map['placa_reboque'])
                                            await cell_reboque.scroll_into_view_if_needed()
                                            await cell_reboque.dblclick()
                                            await target_page.wait_for_timeout(100)
                                            await target_page.keyboard.type(d['placa_reboque'])
                                            await target_page.wait_for_timeout(50)
                                            await target_page.keyboard.press('Enter')
                                            
                                        print(f"[WEB] -> Sucesso! Dados preenchidos para {termo_busca}.")
                                        await target_page.wait_for_timeout(1500)
                                else:
                                    print(f"[WEB] -> AVISO: Não achou a linha para '{termo_busca}'. Adicionando aos pendentes.")
                                    coletas_pendentes.append(d)
                            
                            # SALVAR ANTES DA CASCATA SE TEVE SUCESSOS
                            sucessos_fase1 = len(dados_extraidos) - len(coletas_pendentes)
                            if sucessos_fase1 > 0 and coletas_pendentes:
                                print(f"[WEB] Salvando as {sucessos_fase1} coletas preenchidas antes de abrir as Cascatas...")
                                try:
                                    btn_enviar = results_frame.locator('td.otherToolStripButton:has-text("Enviar")').first
                                    if await btn_enviar.is_visible(timeout=3000):
                                        await btn_enviar.click()
                                        await target_page.wait_for_timeout(4000)
                                        # Recarrega a variável results_frame caso a página pisque
                                        for f in target_page.frames:
                                            if await f.locator('table.listTable').count() > 0 or await f.locator('text="ID da carga"').count() > 0:
                                                results_frame = f
                                                break
                                except Exception as e:
                                    print(f"[WEB] Aviso ao clicar em Enviar (Fase 1): {e}")
                            
                            # ==========================================
                            # LÓGICA DE CASCATA (PARA AS COLETAS PENDENTES)
                            # ==========================================
                            if coletas_pendentes:
                                print(f"[WEB] Iniciando busca avançada (Cascata) para coletas pendentes...")
                                cascatas_processadas = set()
                                
                                while coletas_pendentes:
                                    reiniciar_cascata = False
                                    try:
                                        print(f"[WEB] Temos {len(coletas_pendentes)} pendentes. Varrendo tabela para cascatas...")
                                        # DESMARCAR TUDO antes de começar as cascatas
                                        caixinhas_ativas = await results_frame.locator('input[type="checkbox"]:checked').all()
                                        for cx in caixinhas_ativas:
                                            try:
                                                await cx.uncheck(timeout=1000)
                                            except:
                                                pass
                                                
                                        # Pega todas as linhas
                                        linhas = await results_frame.locator('table.listTable tbody tr').all()
                                        
                                        for idx, row in enumerate(linhas):
                                            if not coletas_pendentes:
                                                break # Todas foram resolvidas
                                            
                                            try:
                                                # Evita Timeout em linhas ocultas ou sub-painéis (que tem menos de 15 colunas)
                                                col_count = await row.locator(':scope > td').count()
                                                if col_count < 15:
                                                    continue
                                                
                                                # Colunas: 1 (ID da carga), 2 (ID do fornecimento), 8 (Nome do local de origem)
                                                id_carga = await row.locator(':scope > td').nth(1).inner_text(timeout=1000)
                                                id_fornecimento = await row.locator(':scope > td').nth(2).inner_text(timeout=1000)
                                                texto_linha_principal = await row.inner_text(timeout=1000)
                                            
                                                id_carga = id_carga.strip()
                                                
                                                if id_carga in cascatas_processadas:
                                                    continue
                                                    
                                                id_fornecimento = id_fornecimento.strip()
                                            
                                                # Se tem ID da carga mas NÃO tem ID do fornecimento, é uma Cascata!
                                                if id_carga and not id_fornecimento:
                                                    cascatas_processadas.add(id_carga)
                                                    print(f"[WEB] Analisando Cascata (Carga: {id_carga})...")
                                                
                                                    # 1. Marca a caixinha (coluna 0)
                                                    checkbox = row.locator(':scope > td').nth(0)
                                                    await checkbox.scroll_into_view_if_needed(timeout=1000)
                                                    await checkbox.click(timeout=1000)
                                                    await target_page.wait_for_timeout(1000)
                                                
                                                    # 2. Clica no botão "Cascata" e depois "Fornecimentos" (ou similar)
                                                    try:
                                                        btn_cascata = results_frame.locator('td.otherToolStripButton:has-text("Cascata")').first
                                                        if await btn_cascata.is_visible(timeout=2000):
                                                            await btn_cascata.click(timeout=2000)
                                                            await target_page.wait_for_timeout(1000)
                                                            btn_fornec = results_frame.locator('div[role="presentation"]:has-text("Fornecimentos")').first
                                                            if await btn_fornec.is_visible(timeout=2000):
                                                                await btn_fornec.click(timeout=2000)
                                                    except Exception as menu_e:
                                                        print(f"[WEB] Aviso ao clicar no menu Cascata: {menu_e}")
                                                        # Fallback: clica no link do ID da carga
                                                        try:
                                                            await row.locator('td').nth(1).locator('a').first.click(timeout=2000)
                                                        except:
                                                            pass
                                                
                                                    await target_page.wait_for_timeout(3000) # Aguarda o sub-painel abrir
                                                
                                                    # 3. Analisa o sub-painel
                                                    resolvidos_nesta_cascata = []
                                                    houve_edicao_nesta_cascata = False
                                                    
                                                    for pendente in coletas_pendentes:
                                                        termo_busca = pendente.get('id_delivery') or pendente.get('busca')
                                                    
                                                        # Verifica se o ID está visível em algum lugar da tela (no sub-painel)
                                                        if await results_frame.locator(f'text="{termo_busca}"').count() > 0:
                                                            print(f"[WEB] -> Cascata MATCH! O ID {termo_busca} está dentro da carga {id_carga}.")
                                                        
                                                            # REGRA DE OURO: Verifica se o Cliente bate com a Origem da Linha Principal
                                                            cliente = pendente.get('busca', '').upper() # Ex: "WMS MAX..."
                                                        
                                                            # Como o texto exato pode estar abreviado, pegamos o primeiro nome
                                                            primeiro_nome_cliente = cliente.split()[0] if cliente else ""
                                                        
                                                            if primeiro_nome_cliente and primeiro_nome_cliente in texto_linha_principal.upper():
                                                                print(f"[WEB] -> Validação de Origem APROVADA ({primeiro_nome_cliente}).")
                                                                
                                                                precisa_preencher = False
                                                                if not houve_edicao_nesta_cascata:
                                                                    campos_verificar = [('nome', col_map['nome']), ('cpf', col_map['cpf']), ('placa_cavalo', col_map['placa_cavalo'])]
                                                                    if col_map['placa_reboque'] != -1:
                                                                        campos_verificar.append(('placa_reboque', col_map['placa_reboque']))
                                                                    for chave, col_idx in campos_verificar:
                                                                        if chave in pendente and pendente[chave]:
                                                                            txt_atual = await row.locator(':scope > td').nth(col_idx).inner_text(timeout=1000)
                                                                            if not txt_atual.strip():
                                                                                precisa_preencher = True
                                                                                break
                                                            
                                                                # Só preenche a linha principal SE precisar
                                                                if precisa_preencher:
                                                                    print("[WEB] -> Preenchendo a linha principal do caminhão...")
                                                                    if 'nome' in pendente and pendente['nome']:
                                                                        cell_nome = row.locator(':scope > td').nth(col_map['nome'])
                                                                        await cell_nome.scroll_into_view_if_needed()
                                                                        await cell_nome.dblclick()
                                                                        await target_page.wait_for_timeout(100)
                                                                        await target_page.keyboard.type(pendente['nome'])
                                                                        await target_page.wait_for_timeout(50)
                                                                        await target_page.keyboard.press('Enter')
                                                                
                                                                    if 'cpf' in pendente and pendente['cpf']:
                                                                        cell_cpf = row.locator(':scope > td').nth(col_map['cpf'])
                                                                        await cell_cpf.scroll_into_view_if_needed()
                                                                        await cell_cpf.dblclick()
                                                                        await target_page.wait_for_timeout(100)
                                                                        await target_page.keyboard.type(pendente['cpf'])
                                                                        await target_page.wait_for_timeout(50)
                                                                        await target_page.keyboard.press('Enter')
                                                                    
                                                                    if 'placa_cavalo' in pendente and pendente['placa_cavalo']:
                                                                        cell_placa = row.locator(':scope > td').nth(col_map['placa_cavalo'])
                                                                        await cell_placa.scroll_into_view_if_needed()
                                                                        await cell_placa.dblclick()
                                                                        await target_page.wait_for_timeout(100)
                                                                        await target_page.keyboard.type(pendente['placa_cavalo'])
                                                                        await target_page.wait_for_timeout(50)
                                                                        await target_page.keyboard.press('Enter')
                                                                    
                                                                    if 'placa_reboque' in pendente and pendente['placa_reboque'] and col_map['placa_reboque'] != -1:
                                                                        cell_reboque = row.locator(':scope > td').nth(col_map['placa_reboque'])
                                                                        await cell_reboque.scroll_into_view_if_needed()
                                                                        await cell_reboque.dblclick()
                                                                        await target_page.wait_for_timeout(100)
                                                                        await target_page.keyboard.type(pendente['placa_reboque'])
                                                                        await target_page.wait_for_timeout(50)
                                                                        await target_page.keyboard.press('Enter')
                                                                
                                                                    houve_edicao_nesta_cascata = True
                                                                else:
                                                                    print("[WEB] -> A linha principal já tem todos os dados para esta Carga. Pulando digitação.")
                                                            
                                                                resolvidos_nesta_cascata.append(pendente)
                                                                await target_page.wait_for_timeout(1500)
                                                            else:
                                                                print(f"[WEB] -> Validação de Origem REPROVADA (Cliente {cliente} não bate com a linha principal). Ignorando para não preencher errado.")
                                                    
                                                        # Remove os resolvidos da lista de pendentes
                                                        for r in resolvidos_nesta_cascata:
                                                            if r in coletas_pendentes:
                                                                coletas_pendentes.remove(r)
                                                            
                                                        # Desmarca a caixinha
                                                        try:
                                                            await checkbox.uncheck(timeout=1000)
                                                        except:
                                                            await checkbox.click(timeout=1000)
                                                        await target_page.wait_for_timeout(1000)
                                                    
                                                        # SE PREENCHEU ALGO, SALVA E REINICIA A BUSCA
                                                        if houve_edicao_nesta_cascata:
                                                            print(f"[WEB] Salvando edições da cascata {id_carga} antes de prosseguir...")
                                                            try:
                                                                btn_enviar = results_frame.locator('td.otherToolStripButton:has-text("Enviar")').first
                                                                if await btn_enviar.is_visible(timeout=3000):
                                                                    await btn_enviar.click()
                                                                    await target_page.wait_for_timeout(4000)
                                                                    # Recarrega a variável results_frame caso a página pisque
                                                                    for f in target_page.frames:
                                                                        if await f.locator('table.listTable').count() > 0 or await f.locator('text="ID da carga"').count() > 0:
                                                                            results_frame = f
                                                                            break
                                                            except Exception as e:
                                                                print(f"[WEB] Aviso ao clicar em Enviar (Cascata): {e}")
                                                        
                                                            reiniciar_cascata = True
                                                        
                                            except Exception as row_e:
                                                print(f"[WEB] Erro ao analisar linha principal da cascata: {row_e}")
                                                
                                        if not reiniciar_cascata:
                                            print("[WEB] Varredura de cascatas concluída sem novas edições. Fim da Fase 2.")
                                            break # Termina o while loop
                                            
                                    except Exception as e:
                                        print(f"[WEB] Erro na lógica de cascata: {e}")
                                        break # Evita loop infinito em caso de erro fatal
                            # ==========================================

                            print("[WEB] Preenchimento finalizado neste perfil.")
                            
                            # ================= PRODUÇÃO ATIVADA =================
                            # Clica no botão Enviar para salvar as edições
                            print("[WEB] -> Clicando em ENVIAR para confirmar os Motoristas...")
                            btn_enviar = target_page.locator('td.otherToolStripButton:has-text("Enviar")').first
                            if await btn_enviar.is_visible():
                                await btn_enviar.click()
                                await target_page.wait_for_timeout(3000) # Aguarda salvar
                            # ====================================================
                            
                            # TIRA PRINT DA TELA PARA CONFERÊNCIA
                            print("[WEB] Tirando print da tela para conferência...")
                            import os
                            from datetime import datetime
                            pasta_prints = "prints_conferencia"
                            if not os.path.exists(pasta_prints):
                                os.makedirs(pasta_prints)
                                
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            print_path = os.path.join(pasta_prints, f"conferencia_{login_user}_{timestamp}.png")
                            
                            # Aguarda um momento para garantir que as animações terminaram
                            await target_page.wait_for_timeout(1000)
                            await target_page.screenshot(path=print_path, full_page=True)
                            print(f"[WEB] Print salvo em: {print_path}")
                            print("[WEB] Fechando navegador para trocar de perfil...")
                                
                        else:
                            print("[WEB] Frame da tabela não encontrado.")
                            coletas_pendentes = dados_extraidos
                    else:
                        print("[WEB] Não encontrou PROGRAMAÇÃO AMANHÃ.")
                        coletas_pendentes = dados_extraidos
        except Exception as e:
            print(f"[WEB] Erro crítico: {e}")
            coletas_pendentes = dados_extraidos

        await browser.close()
        return coletas_pendentes

def executar_preenchimento(dados_extraidos, login_user, login_pass):
    return asyncio.run(executar_preenchimento_async(dados_extraidos, login_user, login_pass))
