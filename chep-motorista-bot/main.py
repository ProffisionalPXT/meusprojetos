import os
import time
from dotenv import load_dotenv
from ocr.extrator import extrair_dados_coleta
from web.navegacao import executar_preenchimento

# Carrega as variáveis do arquivo .env
load_dotenv()

INPUT_DIR = "input"

def monitorar_pasta():
    print(f"Iniciando o robô CHEP. Monitorando a pasta '{INPUT_DIR}'...")
    
    # Criar pasta se não existir
    if not os.path.exists(INPUT_DIR):
        os.makedirs(INPUT_DIR)
        
    # Limpa inicializações pendentes de travamentos anteriores para exigir o botão no Painel
    arquivo_go = os.path.join(INPUT_DIR, "processar.go")
    if os.path.exists(arquivo_go):
        try:
            os.remove(arquivo_go)
            print("[+] Limpando inicialização antiga. Aguardando você colar imagens e clicar em INICIAR no Painel...")
        except: pass
        
    while True:
        arquivos = os.listdir(INPUT_DIR)
        
        # O robô só começa a trabalhar quando o painel soltar o arquivo 'processar.go'
        if "processar.go" in arquivos:
            print("\n=======================================================")
            print("[+] Lote de imagens detectado! Iniciando processamento...")
            print("=======================================================\n")
            
            caminhos_imagens = [os.path.join(INPUT_DIR, f) for f in arquivos if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            
            try:
                # Passo 1: Extrair dados de TODAS as imagens de uma vez
                dados_extraidos = extrair_dados_coleta(caminhos_imagens)
                
                if dados_extraidos:
                    print(f"[+] Inteligência Visual concluiu: {len(dados_extraidos)} coletas mapeadas prontas para o CHEP.")
                    
                    # Lista de perfis puxada do .env
                    perfis = [
                        {"user": os.getenv("CHEP_USER_2"), "pass": os.getenv("CHEP_PASS_2")},
                        {"user": os.getenv("CHEP_USER_3"), "pass": os.getenv("CHEP_PASS_3")}
                    ]
                    
                    # Passo 2: Mandar o Módulo Web preencher no sistema (com roteamento inteligente)
                    coletas_pendentes = dados_extraidos
                    
                    for perfil in perfis:
                        user_id = perfil['user']
                        # Filtra apenas as coletas que pertencem a este perfil OU que ainda não tem perfil descoberto
                        coletas_neste_perfil = [c for c in coletas_pendentes if c.get('perfil') == user_id or not c.get('perfil')]
                        
                        if coletas_neste_perfil:
                            print(f"\n[+] Entrando no perfil {user_id} para processar {len(coletas_neste_perfil)} carga(s)...")
                            restantes = executar_preenchimento(coletas_neste_perfil, user_id, perfil['pass'])
                            
                            # Atualiza as pendentes globais removendo as que deram certo
                            sucessos = [c for c in coletas_neste_perfil if c not in restantes]
                            coletas_pendentes = [c for c in coletas_pendentes if c not in sucessos]
                            
                            if not coletas_pendentes:
                                print(f"[+] Todas as coletas do lote foram preenchidas com sucesso!")
                                break
                        else:
                            print(f"\n[-] Pulando o perfil {user_id} (Nenhuma carga pertence a ele!). Isso poupou muito tempo.")
                            
                    if coletas_pendentes:
                        print("\n=======================================================")
                        print("[-] AVISO: AS SEGUINTES COLETAS NÃO FORAM ENCONTRADAS (PODE SER CASCATA ANTIGA):")
                        for p in coletas_pendentes:
                            nome = p.get('nome', 'N/A')
                            busca = p.get('busca') or p.get('id_delivery', 'N/A')
                            print(f"    -> Motorista: {nome} | Referência: {busca}")
                        print("=======================================================\n")
                    
                else:
                    print("[-] Falha ao extrair dados ou lote vazio.")
            except Exception as e:
                print(f"\n[!] ERRO CRÍTICO NO PROCESSAMENTO DO LOTE: {e}")
                print("[!] O lote atual falhou, mas o robô continuará monitorando a pasta para os próximos lotes.\n")
                
                
            # Limpeza final do lote
            print("\n[+] Limpando pasta de entrada para o próximo lote...")
            for arquivo in arquivos:
                caminho = os.path.join(INPUT_DIR, arquivo)
                try:
                    os.remove(caminho)
                except Exception as e:
                    print(f"Erro ao deletar {arquivo}: {e}")
                    
        time.sleep(2) # Aguarda 2 segundos antes de olhar a pasta de novo

if __name__ == "__main__":
    monitorar_pasta()
