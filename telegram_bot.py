"""
Bot do Telegram para o GW Motorista Bot.
Permite enviar fotos/PDFs pelo celular via Telegram e cadastrar no GW em segundo plano.
"""
from __future__ import annotations

import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

import json
import os
import sys
import time
import subprocess
from pathlib import Path
import requests
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=PROJECT_DIR / ".env", override=True)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API_URL = f"https://api.telegram.org/bot{TOKEN}"
INPUT_MOTORISTA = PROJECT_DIR / "input" / "motorista"
INPUT_MOTORISTA.mkdir(parents=True, exist_ok=True)


def get_updates(offset: int = 0, timeout: int = 30) -> list:
    if not TOKEN:
        return []
    try:
        r = requests.get(f"{API_URL}/getUpdates", params={"offset": offset, "timeout": timeout}, timeout=timeout + 5)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception as e:
        print(f"[Telegram] Erro getUpdates: {e}")
    return []


def send_message(chat_id: int | str, text: str, reply_markup: dict | None = None) -> bool:
    if not TOKEN:
        return False
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print(f"[Telegram] Erro send_message: {e}")
        return False


def download_file(file_id: str, dest_name: str) -> Path | None:
    try:
        r = requests.get(f"{API_URL}/getFile", params={"file_id": file_id}, timeout=15)
        if r.status_code != 200:
            return None
        file_path = r.json().get("result", {}).get("file_path")
        if not file_path:
            return None
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        r_file = requests.get(file_url, timeout=30)
        if r_file.status_code == 200:
            dest = INPUT_MOTORISTA / dest_name
            dest.write_bytes(r_file.content)
            print(f"[Telegram] Arquivo salvo: {dest.name}")
            return dest
    except Exception as e:
        print(f"[Telegram] Erro ao baixar arquivo: {e}")
    return None


def limpar_pasta_input() -> int:
    INPUT_MOTORISTA.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in list(INPUT_MOTORISTA.iterdir()):
        if f.is_file() and not f.name.endswith(".bat"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
    return count


def executar_cadastro_gw(chat_id: int | str) -> None:
    arqs = [f for f in INPUT_MOTORISTA.iterdir() if f.is_file() and not f.name.endswith(".bat") and f.name != "dados_manuais.json"]
    if not arqs:
        send_message(
            chat_id,
            "⚠️ *Nenhum documento encontrado na pasta!*\n\n"
            "Por favor, me envie as fotos ou PDFs da CNH, CRLVs e ANTT antes de cadastrar."
        )
        return

    send_message(
        chat_id,
        f"⏳ *Analisando {len(arqs)} documento(s)...*\n_Extraindo dados da CNH, CRLVs e ANTT..._"
    )

    try:
        from ler_documentos_rapido import ler_e_salvar_dados_rapido
        dados = ler_e_salvar_dados_rapido()
        m = dados.motorista
        v = dados.veiculo
        c = dados.carreta
        
        resumo = f"📋 *Dados Identificados:*\n\n" \
                 f"👤 *Motorista:* `{m.nome}`\n" \
                 f"🆔 *CPF:* `{m.cpf}` | *CNH:* `{m.cnh}` (Espelho: `{m.cnh_espelho}`)\n"
        if v:
            resumo += f"🚛 *Veículo ({v.tipo}):* `{v.placa}` ({v.marca_modelo_versao})\n"
            if v.proprietario:
                resumo += f"   └ *Proprietário:* `{v.proprietario.nome}` (`{v.proprietario.cpf_cnpj}`)\n"
        if c:
            resumo += f"🚛 *Carreta ({c.tipo}):* `{c.placa}` ({c.marca_modelo_versao})\n"
            if c.proprietario:
                resumo += f"   └ *Proprietário:* `{c.proprietario.nome}` (`{c.proprietario.cpf_cnpj}`)\n"
        if dados.rntrc_tac:
            resumo += f"🏢 *ANTT / RNTRC:* `{dados.rntrc_tac}`\n"
        
        resumo += "\n⏳ *Acessando GW Webtrans em segundo plano...*"
        send_message(chat_id, resumo)
    except Exception as e:
        print(f"[Telegram] Erro na pré-extração: {e}")
        send_message(chat_id, f"⏳ *Iniciando robô no GW Webtrans...*")

    cmd = [sys.executable, str(PROJECT_DIR / "main.py")]
    try:
        env = os.environ.copy()
        env["BROWSER_MODE"] = "headless"
        env["CONFIRMAR_DADOS"] = "0"
        env["INTERVENCAO_MANUAL"] = "0"
        
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        
        stdout, _ = proc.communicate(timeout=240)
        
        if "Salvo com sucesso" in stdout or "concluído com sucesso" in stdout or "Salvar final" in stdout or "URL mudou após Salvar" in stdout or proc.returncode == 0:
            teclado = {
                "inline_keyboard": [
                    [{"text": "🧹 Limpar para o Próximo Motorista", "callback_data": "limpar"}]
                ]
            }
            send_message(
                chat_id,
                "🎉 *CADASTRO REALIZADO COM SUCESSO NO GW!* ✅\n\n"
                "O motorista e os veículos foram registrados e vinculados no GW Webtrans.\n"
                "Quando tiver outro motorista, basta enviar as fotos aqui!",
                reply_markup=teclado
            )
        else:
            send_message(
                chat_id,
                f"⚠️ *Aviso do Robô:*\n\n```\n{stdout[-600:]}\n```"
            )
    except subprocess.TimeoutExpired:
        send_message(chat_id, "⚠️ *Tempo limite excedido no cadastro.* Verifique o sistema.")
    except Exception as e:
        send_message(chat_id, f"❌ *Erro ao executar robô:* {e}")


def processar_mensagem(update: dict) -> None:
    msg = update.get("message") or update.get("callback_query", {}).get("message")
    if not msg:
        return
    
    chat_id = msg["chat"]["id"]
    texto = (msg.get("text") or "").strip()

    # Tratamento de botões inline
    if "callback_query" in update:
        data = update["callback_query"].get("data")
        if data == "cadastrar":
            executar_cadastro_gw(chat_id)
            return
        elif data == "limpar":
            qtd = limpar_pasta_input()
            send_message(chat_id, f"🧹 *Pasta limpa!* {qtd} arquivo(s) removido(s). Pronto para o próximo motorista.")
            return

    # Comandos
    if texto in ("/start", "/help", "/ajuda"):
        teclado = {
            "inline_keyboard": [
                [{"text": "🚀 Cadastrar no GW Agora", "callback_data": "cadastrar"}],
                [{"text": "🧹 Limpar Pasta (Novo Motorista)", "callback_data": "limpar"}],
            ]
        }
        send_message(
            chat_id,
            "👋 *Olá! Sou o Robô GW de Cadastro de Motoristas.*\n\n"
            "📲 *Como usar pelo celular:*\n"
            "1. Envie aqui as **fotos ou PDFs** (CNH, CRLVs, ANTT);\n"
            "2. Quando terminar de enviar os arquivos, clique no botão **Cadastrar** abaixo ou digite `/cadastrar`;\n"
            "3. O robô faz tudo silenciosamente no computador e te avisa aqui quando terminar!",
            reply_markup=teclado
        )
        return

    if texto == "/limpar":
        qtd = limpar_pasta_input()
        send_message(chat_id, f"🧹 *Pasta limpa!* {qtd} arquivo(s) removido(s). Pode enviar os documentos do novo motorista.")
        return

    if texto in ("/cadastrar", "/executar", "cadastrar", "Cadastrar", "executar"):
        executar_cadastro_gw(chat_id)
        return

    # Recebimento de Documentos (PDF / imagens como arquivo)
    if "document" in msg:
        doc = msg["document"]
        file_id = doc["file_id"]
        file_name = doc.get("file_name") or f"doc_{int(time.time())}.pdf"
        salvo = download_file(file_id, file_name)
        if salvo:
            total = len([f for f in INPUT_MOTORISTA.iterdir() if f.is_file() and not f.name.endswith(".bat") and f.name != "dados_manuais.json"])
            teclado = {
                "inline_keyboard": [
                    [{"text": f"🚀 Cadastrar Agora ({total} doc(s))", "callback_data": "cadastrar"}],
                    [{"text": "🧹 Limpar Fila", "callback_data": "limpar"}]
                ]
            }
            send_message(
                chat_id,
                f"📥 *Documento recebido:* `{file_name}`\n"
                f"📊 *Total na fila:* {total} documento(s).\n\n"
                "_Envie os outros documentos ou toque no botão abaixo para iniciar o cadastro:_",
                reply_markup=teclado
            )
        return

    # Recebimento de Fotos enviadas como imagem
    if "photo" in msg:
        fotos = msg["photo"]
        maior_foto = fotos[-1]
        file_id = maior_foto["file_id"]
        file_name = f"foto_{int(time.time())}.jpg"
        salvo = download_file(file_id, file_name)
        if salvo:
            total = len([f for f in INPUT_MOTORISTA.iterdir() if f.is_file() and not f.name.endswith(".bat") and f.name != "dados_manuais.json"])
            teclado = {
                "inline_keyboard": [
                    [{"text": f"🚀 Cadastrar via Robô ({total} docs)", "callback_data": "cadastrar"}],
                    [{"text": "🧹 Limpar Fila", "callback_data": "limpar"}]
                ]
            }
            send_message(
                chat_id,
                f"📥 *Foto recebida e salva na pasta!*\n"
                f"📊 *Total na fila:* {total} documento(s).\n\n"
                "💡 _Você pode enviar mais documentos ou ir no seu navegador remoto e digitar 'ler documentos'._\n"
                "Ou se preferir, toque no botão abaixo para o robô cadastrar direto:",
                reply_markup=teclado
            )
        return


def rodar_bot() -> None:
    if not TOKEN:
        print("\n" + "=" * 60)
        print("  [!] TELEGRAM_BOT_TOKEN NÃO CONFIGURADO NO .env")
        print("  Crie seu bot no @BotFather do Telegram e cole o TOKEN no .env")
        print("=" * 60 + "\n")
        return

    print("\n" + "=" * 60)
    print("  🤖 BOT TELEGRAM DO GW MOTORISTA INICIADO COM SUCESSO!")
    print("  Aguardando mensagens e documentos pelo celular...")
    print("=" * 60 + "\n")

    offset = 0
    while True:
        try:
            updates = get_updates(offset=offset, timeout=20)
            for upd in updates:
                offset = upd["update_id"] + 1
                processar_mensagem(upd)
        except KeyboardInterrupt:
            print("\n[Telegram] Bot encerrado.")
            break
        except Exception as e:
            print(f"[Telegram] Erro no loop: {e}")
            time.sleep(3)


if __name__ == "__main__":
    rodar_bot()
