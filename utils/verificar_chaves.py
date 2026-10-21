"""
Verificador de Status e Cota das Chaves de IA (Gemini, OpenAI, Groq).

Testa a conectividade, saúde dos servidores do Google, latência de cada chave
e exibe um resumo da capacidade diária.
"""
from __future__ import annotations

import os
import sys
import time
import warnings
import logging
from pathlib import Path
from dotenv import load_dotenv

warnings.filterwarnings("ignore", message=".*automatic function calling.*")
logging.getLogger("google.genai.models").setLevel(logging.ERROR)
try:
    from google.genai.models import Models
    Models._logged_afc_warning = True
except Exception:
    pass

# Garante carregamento do .env a partir da raiz do projeto
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _rotulo(chave: str) -> str:
    if not chave:
        return "N/A"
    return f"...{chave[-8:]}" if len(chave) > 12 else chave


def testar_gemini():
    print("\n" + "=" * 70)
    print(" [IA] DIAGNOSTICO EM TEMPO REAL DAS CHAVES GOOGLE GEMINI")
    print("=" * 70)

    chaves = [
        ("Chave Principal", os.getenv("GEMINI_API_KEY", "").strip()),
        ("Chave Backup 1", os.getenv("GEMINI_API_KEY_BACKUP", "").strip()),
        ("Chave Backup 2", os.getenv("GEMINI_API_KEY_BACKUP2", "").strip()),
    ]

    modelo_padrao = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    modelos_teste = [modelo_padrao, "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    modelos_unicos = list(dict.fromkeys(modelos_teste))

    chaves_validas = 0
    total_chaves_configuradas = 0

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("\n[ERRO] Biblioteca 'google-genai' nao encontrada no ambiente Python.")
        return

    for nome_chave, key in chaves:
        if not key or key.startswith("sua_"):
            print(f"\n[-- {nome_chave}]: Nao configurada no .env")
            continue

        total_chaves_configuradas += 1
        print(f"\n[KEY {nome_chave}] (Final: {_rotulo(key)}):")

        client = genai.Client(api_key=key)
        chave_teve_sucesso = False

        for mod in modelos_unicos:
            time.sleep(0.4)  # Evita burst de requisições por segundo
            t0 = time.time()
            try:
                resp = client.models.generate_content(
                    model=mod,
                    contents="Responda estritamente 'OK'.",
                    config=types.GenerateContentConfig(
                        http_options=types.HttpOptions(timeout=10000)
                    ),
                )
                dt = time.time() - t0
                print(f"   +-- Modelo {mod:<18} -> [OK ATIVO] ({dt:.2f}s) - Cota OK")
                chave_teve_sucesso = True
            except Exception as e:
                dt = time.time() - t0
                msg = str(e).lower()
                if "429" in msg or "resource_exhausted" in msg:
                    print(f"   +-- Modelo {mod:<18} -> [COTA ESGOTADA 429] ({dt:.2f}s)")
                elif "503" in msg or "504" in msg or "unavailable" in msg or "deadline" in msg:
                    print(f"   +-- Modelo {mod:<18} -> [SERVIDOR GOOGLE 503 OCUPADO] ({dt:.2f}s)")
                elif "400" in msg or "403" in msg or "invalid" in msg:
                    print(f"   +-- Modelo {mod:<18} -> [CHAVE INVALIDA/EXPIRADA] ({dt:.2f}s)")
                else:
                    print(f"   +-- Modelo {mod:<18} -> [AVISO] ({dt:.2f}s): {str(e)[:50]}")

        if chave_teve_sucesso:
            chaves_validas += 1

    # --- Resumo da Cota ---
    print("\n" + "-" * 70)
    print(" RESUMO DE CAPACIDADE E COTA DIARIA")
    print("-" * 70)
    cota_por_chave = 1500
    cota_total = total_chaves_configuradas * cota_por_chave
    consumo_estimado = 24  # 6 cadastros x 4 docs

    print(f" * Chaves operacionais ativas: {chaves_validas} de {total_chaves_configuradas} configuradas")
    print(f" * Limite gratuito do Google:  {cota_por_chave:,} requisicoes/dia POR CHAVE")
    print(f" * Capacidade total diaria:    {cota_total:,} requisicoes/dia somando suas chaves")
    print(f" * Seu consumo diario medio:   ~{consumo_estimado} requisicoes/dia (6 cadastros)")
    
    if cota_total > 0:
        percentual = (consumo_estimado / cota_total) * 100
        print(f" * Uso estimado da sua cota:   Apenas {percentual:.2f}% por dia (Folga de {100 - percentual:.2f}%)")
    print("-" * 70)


def testar_outros_provedores():
    print("\n" + "=" * 70)
    print(" STATUS DOS PROVEDORES DE CONTINGENCIA (OPENAI & GROQ)")
    print("=" * 70)

    # 1. OpenAI
    oai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if oai_key and not oai_key.startswith("sua_"):
        try:
            import httpx
            t0 = time.time()
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {oai_key}"},
                json={
                    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "messages": [{"role": "user", "content": "OK"}],
                    "max_tokens": 5,
                },
                timeout=8,
            )
            dt = time.time() - t0
            if resp.status_code == 200:
                print(f" [OpenAI GPT-4o-mini]: [OK ATIVO] ({dt:.2f}s) - Saldo disponivel")
            elif resp.status_code == 429:
                print(f" [OpenAI GPT-4o-mini]: [SEM SALDO/CREDITOS] (Erro 429)")
            else:
                print(f" [OpenAI GPT-4o-mini]: [AVISO] Status {resp.status_code} ({resp.text[:50]})")
        except Exception as e:
            print(f" [OpenAI GPT-4o-mini]: [ERRO] Conexao ({e})")
    else:
        print(" [OpenAI GPT-4o-mini]: [--] Chave nao configurada no .env")

    # 2. Groq
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key and not groq_key.startswith("sua_"):
        try:
            import httpx
            t0 = time.time()
            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={
                    "model": os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
                    "messages": [{"role": "user", "content": "OK"}],
                    "max_tokens": 5,
                },
                timeout=8,
            )
            dt = time.time() - t0
            if resp.status_code == 200:
                print(f" [Groq Llama 4 Vision]: [OK ATIVO] ({dt:.2f}s) - Gratuito e operacional")
            else:
                print(f" [Groq Llama 4 Vision]: [AVISO] Status {resp.status_code} ({resp.text[:50]})")
        except Exception as e:
            print(f" [Groq Llama 4 Vision]: [ERRO] Conexao ({e})")
    else:
        print(" [Groq Llama 4 Vision]: [--] Chave nao configurada no .env")

    print("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        testar_gemini()
        testar_outros_provedores()
    except KeyboardInterrupt:
        print("\nTeste cancelado pelo usuario.")
