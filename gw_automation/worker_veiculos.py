# gw_automation/worker_veiculos.py
"""
Processo worker independente para cadastrar Proprietário e Veículos em segundo plano.
Executa em um subprocesso Python com sua própria instância do Playwright,
reutilizando o estado de autenticação (cookies) exportado da sessão principal.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

# Ajusta path para importar módulos do projeto
project_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_dir))

from playwright.sync_api import sync_playwright

from gw_automation.login import browser_mode
from gw_automation.lookup import _salvar_com_confirmacao
from gw_automation.urls import NOVO_VEICULO
from gw_automation.veiculo import preencher_form_veiculo_completo
from ocr.extrair_dados import DadosProprietario, DadosVeiculo


def _tratar_dialog_veiculo(dialog):
    msg = (dialog.message or "").lower()
    print(f"[Worker Veículo alerta] {msg}")
    try:
        dialog.accept()
    except Exception:
        pass


def cadastrar_veiculo_isolado(page, dados_v: DadosVeiculo, prop: DadosProprietario | None) -> bool:
    if not dados_v or not dados_v.placa:
        return True

    print(f"[Worker] Cadastrando em segundo plano: {dados_v.tipo or 'Veículo'} placa={dados_v.placa}...")
    try:
        page.goto(NOVO_VEICULO, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(500)
    except Exception as e:
        print(f"[Worker] Erro ao abrir form {NOVO_VEICULO}: {e}")
        return False

    # Preenche formulário completo
    try:
        preencher_form_veiculo_completo(page, dados_v, proprietario=prop)
        page.wait_for_timeout(400)
        
        # Salva o cadastro
        salvou = _salvar_com_confirmacao(page)
        if salvou:
            print(f"[Worker] [OK] Veículo {dados_v.placa} salvo com sucesso!")
            return True
        else:
            print(f"[Worker] [!] Falha ao salvar veículo {dados_v.placa}.")
            return False
    except Exception as e:
        print(f"[Worker] Exceção ao preencher/salvar veículo {dados_v.placa}: {e}")
        traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 3:
        print("Uso: worker_veiculos.py <caminho_dados_json> <caminho_resultado_json>")
        sys.exit(1)

    caminho_dados = sys.argv[1]
    caminho_resultado = sys.argv[2]

    try:
        with open(caminho_dados, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"[Worker] Erro ao ler payload {caminho_dados}: {e}")
        sys.exit(1)

    storage_state_path = payload.get("storage_state_path")
    veiculo_dict = payload.get("veiculo")
    carreta_dict = payload.get("carreta")
    prop_dict = payload.get("proprietario")

    def _criar_dados_veiculo(v_dict):
        if not v_dict:
            return None
        v_copy = dict(v_dict)
        p_dict = v_copy.get("proprietario")
        if p_dict and isinstance(p_dict, dict):
            v_copy["proprietario"] = DadosProprietario(**p_dict)
        return DadosVeiculo(**v_copy)

    dados_veiculo = _criar_dados_veiculo(veiculo_dict)
    dados_carreta = _criar_dados_veiculo(carreta_dict)
    dados_prop = DadosProprietario(**prop_dict) if prop_dict else None

    # Se não houver placas a registrar, sai com sucesso
    if not (dados_veiculo and dados_veiculo.placa) and not (dados_carreta and dados_carreta.placa):
        print("[Worker] Nenhum veículo para cadastrar.")
        with open(caminho_resultado, "w", encoding="utf-8") as f:
            json.dump({"status": "ok", "mensagem": "Sem veículos"}, f)
        sys.exit(0)

    sucesso = True
    mensagem = "OK"

    try:
        with sync_playwright() as pw:
            # Modo sempre headless para o worker em segundo plano
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            context = browser.new_context(
                storage_state=storage_state_path,
                viewport={"width": 1366, "height": 768},
                locale="pt-BR",
            )
            page = context.new_page()
            page.on("dialog", _tratar_dialog_veiculo)

            # 1. Cavalo / Veículo principal
            if dados_veiculo and dados_veiculo.placa:
                ok_vei = cadastrar_veiculo_isolado(page, dados_veiculo, dados_prop)
                if not ok_vei:
                    sucesso = False
                    mensagem = f"Falha no veículo {dados_veiculo.placa}"

            # 2. Carreta
            if sucesso and dados_carreta and dados_carreta.placa:
                ok_car = cadastrar_veiculo_isolado(page, dados_carreta, dados_prop)
                if not ok_car:
                    sucesso = False
                    mensagem = f"Falha na carreta {dados_carreta.placa}"

            context.close()
            browser.close()
    except Exception as e:
        sucesso = False
        mensagem = f"Exceção no worker: {e}"
        print(f"[Worker] {mensagem}")
        traceback.print_exc()

    resultado = {
        "status": "ok" if sucesso else "erro",
        "mensagem": mensagem,
    }

    try:
        with open(caminho_resultado, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False)
    except Exception as e:
        print(f"[Worker] Erro ao gravar resultado: {e}")

    sys.exit(0 if sucesso else 1)


if __name__ == "__main__":
    main()
