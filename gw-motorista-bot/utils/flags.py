"""
Flags de comportamento (tudo reverso no .env).

Padrão: melhorias LIGADAS.
Para reverter se o robô piorar, coloque =0 no .env e rode de novo.
"""
from __future__ import annotations

import os


def _on(nome: str, padrao: str = "1") -> bool:
    v = (os.getenv(nome, padrao) or padrao).strip().lower()
    return v not in ("0", "false", "nao", "não", "no", "off")


def salvar_detectar_falha() -> bool:
    """Detecta se o GW recusou o Salvar (form ainda aberto / mensagem)."""
    return _on("SALVAR_DETECTAR_FALHA", "1")


def recriar_se_zero_resultados() -> bool:
    """Se após 'salvar' a pesquisa der 0 registros, tenta Novo Cadastro de novo."""
    return _on("RECRIAR_SE_ZERO_RESULTADOS", "1")


def lookup_max_tentativas_pesquisa() -> int:
    """Quantas vezes pesquisa após cadastro (evita loop longo)."""
    try:
        n = int(os.getenv("LOOKUP_MAX_TENTATIVAS_PESQUISA", "2") or "2")
        return max(1, min(n, 5))
    except Exception:
        return 2


def gemini_validar_nomes() -> bool:
    """
    Gemini completa campos vazios E nomes que parecem lixo (AXR, CPEY...).
    Não inventa no OCR local - pede ao Gemini só nesses casos.
    """
    return _on("GEMINI_VALIDAR_NOMES", "1")


def intervencao_manual() -> bool:
    """
    Quando o robô falha um passo, pausa e deixa você clicar no browser.
    Padrão: ligado se BROWSER_MODE != headless. INTERVENCAO_MANUAL=0 desliga.
    """
    from utils.manual import intervencao_manual_ativa

    return intervencao_manual_ativa()


def imprimir_flags() -> None:
    from utils.manual import max_tentativas_auto

    print(
        "[Flags] "
        f"SALVAR_DETECTAR_FALHA={int(salvar_detectar_falha())} "
        f"RECRIAR_SE_ZERO={int(recriar_se_zero_resultados())} "
        f"LOOKUP_MAX_PESQ={lookup_max_tentativas_pesquisa()} "
        f"GEMINI_VALIDAR_NOMES={int(gemini_validar_nomes())} "
        f"INTERVENCAO_MANUAL={int(intervencao_manual())} "
        f"TENTATIVAS_AUTO={max_tentativas_auto()}"
    )
