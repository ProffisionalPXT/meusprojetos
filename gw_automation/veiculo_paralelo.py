# gw_automation/veiculo_paralelo.py
"""
Orquestrador de cadastro de veículos em segundo plano (Processamento Paralelo).
Permite que o cadastro de veículos e proprietário ocorra simultaneamente
ao preenchimento dos dados pessoais do motorista, com fallback robusto.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import BrowserContext

project_dir = Path(__file__).resolve().parent.parent


class GerenciadorVeiculoParalelo:
    """Gerencia a execução isolada do worker de veículos em subprocesso."""

    def __init__(self, context: BrowserContext, dados: Any) -> None:
        self.context = context
        self.dados = dados
        self.ativo = os.getenv("PARALELO_VEICULOS", "1").strip().lower() not in ("0", "false", "nao", "não", "off")
        self.processo: Optional[subprocess.Popen] = None
        self.temp_state_file: Optional[str] = None
        self.temp_dados_file: Optional[str] = None
        self.temp_res_file: Optional[str] = None

    def iniciar(self) -> bool:
        """Inicia o worker em segundo plano."""
        if not self.ativo:
            print("[Paralelo] Modo paralelo desativado via configuração.")
            return False

        # Verifica se há veículos para cadastrar
        tem_veiculo = bool(self.dados.veiculo and getattr(self.dados.veiculo, "placa", None))
        tem_carreta = bool(self.dados.carreta and getattr(self.dados.carreta, "placa", None))
        if not tem_veiculo and not tem_carreta:
            print("[Paralelo] Sem veículos para registrar em segundo plano.")
            return False

        try:
            # 1. Exporta cookies de sessão do contexto principal
            self.temp_state_file = os.path.join(tempfile.gettempdir(), f"gw_state_{os.getpid()}_{int(time.time())}.json")
            self.context.storage_state(path=self.temp_state_file)

            # 2. Prepara payload JSON com os dados dos veículos
            self.temp_dados_file = os.path.join(tempfile.gettempdir(), f"gw_dados_v_{os.getpid()}_{int(time.time())}.json")
            self.temp_res_file = os.path.join(tempfile.gettempdir(), f"gw_res_v_{os.getpid()}_{int(time.time())}.json")

            def _serializar(obj):
                if obj is None:
                    return None
                try:
                    return asdict(obj)
                except Exception:
                    return getattr(obj, "__dict__", None)

            payload = {
                "storage_state_path": self.temp_state_file,
                "veiculo": _serializar(self.dados.veiculo),
                "carreta": _serializar(self.dados.carreta),
                "proprietario": _serializar(self.dados.proprietario),
            }

            with open(self.temp_dados_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)

            worker_script = str(project_dir / "gw_automation" / "worker_veiculos.py")
            cmd = [sys.executable, worker_script, self.temp_dados_file, self.temp_res_file]

            print(f"[Paralelo] ▶ Iniciando cadastro de veículos em segundo plano (subprocesso)...")
            self.processo = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(project_dir),
            )
            return True
        except Exception as e:
            print(f"[Paralelo] [!] Falha ao iniciar subprocesso de veículos: {e}")
            self.encerrar()
            return False

    def aguardar_ou_fallback(self, timeout: float = 35.0) -> bool:
        """
        Aguarda a conclusão do worker em segundo plano.
        Retorna True se concluído com sucesso.
        Retorna False se houver timeout, erro ou pendência (acionando fallback).
        """
        if not self.processo:
            return False

        print(f"[Paralelo] Aguardando conclusão do cadastro de veículos em segundo plano (limite: {timeout}s)...")
        inicio = time.time()

        while time.time() - inicio < timeout:
            ret = self.processo.poll()
            if ret is not None:
                # Processo terminou
                stdout, stderr = self.processo.communicate()
                print(f"[Paralelo] Subprocesso finalizou (código {ret}).")
                if stdout:
                    for linha in stdout.strip().splitlines()[-4:]:
                        print(f"  [Worker Log] {linha}")

                if ret == 0 and self.temp_res_file and os.path.exists(self.temp_res_file):
                    try:
                        with open(self.temp_res_file, "r", encoding="utf-8") as f:
                            res = json.load(f)
                        if res.get("status") == "ok":
                            print("[Paralelo] [OK] Cadastro em segundo plano concluído com SUCESSO!")
                            self._limpar_arquivos_temp()
                            return True
                        else:
                            print(f"[Paralelo] [!] Worker reportou status diferente: {res}")
                    except Exception as e:
                        print(f"[Paralelo] [!] Erro ao ler resultado do worker: {e}")

                # Se saiu com erro
                if stderr:
                    print(f"[Paralelo] [!] Subprocesso stderr: {stderr.strip()[:200]}")
                break

            time.sleep(0.5)

        # Timeout ou erro: encerra o processo
        print("[Paralelo] [AVISO] Segundo plano não concluiu com sucesso ou excedeu tempo.")
        self.encerrar()
        return False

    def encerrar(self) -> None:
        """Mata o processo se ainda estiver rodando e limpa arquivos temporários."""
        if self.processo and self.processo.poll() is None:
            try:
                print("[Paralelo] Encerrando processo worker secundário...")
                self.processo.kill()
                self.processo.wait(timeout=2)
            except Exception:
                pass
        self._limpar_arquivos_temp()

    def _limpar_arquivos_temp(self) -> None:
        for fpath in (self.temp_state_file, self.temp_dados_file, self.temp_res_file):
            if fpath and os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass
