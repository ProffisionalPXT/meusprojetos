"""
Intervenção manual no browser.

Padrão do robô:
  1ª tentativa - automática
  2ª tentativa - automática
  3ª - você faz; o robô PARA, espera, e RECONHECE o que já está na tela
    (nome na lista, campo preenchido, form aberto) e segue a próxima operação.

Ativo por padrão se BROWSER_MODE=visible ou minimized.
Desligar: INTERVENCAO_MANUAL=0 no .env
"""
from __future__ import annotations

import os
import sys
from typing import Any, Callable, Optional


def intervencao_manual_ativa() -> bool:
    """
    INTERVENCAO_MANUAL:
      - não definido: liga se browser não for headless
      - 1 / true / sim -> sempre liga (se houver terminal)
      - 0 / false / nao -> nunca pausa
    """
    if not sys.stdin.isatty():
        return False
    raw = (os.getenv("INTERVENCAO_MANUAL") or "").strip().lower()
    if raw in ("0", "false", "nao", "não", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "sim", "on"):
        return True
    try:
        from gw_automation.login import browser_mode

        return browser_mode() != "headless"
    except Exception:
        mode = (os.getenv("BROWSER_MODE") or "headless").strip().lower()
        return mode not in ("headless", "")


def max_tentativas_auto() -> int:
    """Quantas tentativas o robô faz sozinho antes de passar para você (padrão 2)."""
    try:
        n = int(os.getenv("TENTATIVAS_AUTO", "2") or "2")
        return max(1, min(n, 5))
    except Exception:
        return 2


def _campo_preenchido(page: Any, seletor: str) -> bool:
    if not page or not seletor:
        return False
    try:
        if page.is_closed():
            return False
    except Exception:
        return False
    try:
        val = (page.input_value(seletor, timeout=800) or "").strip()
        return bool(val)
    except Exception:
        try:
            val = (page.locator(seletor).first.input_value(timeout=500) or "").strip()
            return bool(val)
        except Exception:
            return False


def pausar_para_manual(
    motivo: str,
    *,
    dica: str = "",
    page: Any = None,
    seletor_campo: str = "",
    tentativa: int | None = 3,
    total_auto: int | None = None,
) -> str:
    """
    Para o robô (nenhum clique automático) e deixa você mexer no GW.

    Returns:
      "ok"       - ENTER: continue (robô reconhece o estado e segue)
      "skip"     - s / pular: não tente de novo este passo
      "disabled" - intervenção desligada; segue sem pausar
    """
    if not intervencao_manual_ativa():
        return "disabled"

    if seletor_campo and _campo_preenchido(page, seletor_campo):
        print(f"[Manual] Campo já preenchido ({seletor_campo}) - sem pausa.")
        return "ok"

    try:
        if page is not None and not page.is_closed():
            page.bring_to_front()
    except Exception:
        pass

    auto_n = total_auto if total_auto is not None else max_tentativas_auto()
    cab = "3ª tentativa - você faz"
    if tentativa is not None:
        cab = f"Tentativa {tentativa} - você faz (robô já tentou {auto_n}x sozinho)"

    print()
    print("=" * 58)
    print(f"  ⏸  {cab}")
    print("=" * 58)
    print(f"  Motivo: {motivo}")
    if dica:
        print(f"  Dica:   {dica}")
    if seletor_campo:
        print(f"  Campo:  {seletor_campo}")
    print()
    print("  O robô NÃO clica enquanto espera aqui.")
    print("  Faça o que faltar no GW (ex.: filtro CPF + Pesquisar).")
    print("  Quando o resultado/nome aparecer na tela:")
    print("    ENTER  ->  robô RECONHECE o que já está feito e continua")
    print("    s      ->  pular este passo")
    print("-" * 58)

    while True:
        try:
            cmd = input("  Sua resposta: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  [Manual] Cancelado - tratando como pular.")
            return "skip"

        if cmd in ("", "ok", "c", "continuar", "enter"):
            if seletor_campo and page is not None:
                if _campo_preenchido(page, seletor_campo):
                    print(f"  [Manual] [OK] Campo {seletor_campo} já preenchido.")
                else:
                    print(
                        "  [Manual] Vou olhar a tela (lista / campos) e seguir o que der."
                    )
            else:
                print("  [Manual] Reconhecendo o que já está na tela...")
            print("=" * 58)
            print()
            return "ok"

        if cmd in ("s", "skip", "p", "pular", "n", "nao", "não"):
            print("  [Manual] Passo pulado.")
            print("=" * 58)
            print()
            return "skip"

        print("  Digite ENTER (continuar) ou s (pular).")


def apos_manual_campo_ok(page: Any, seletor_campo: str) -> bool:
    """True se, após intervenção, o seletor já tem valor."""
    return _campo_preenchido(page, seletor_campo)


def reconhecer(
    page: Any,
    checagens: list[tuple[str, Callable[[], bool]]],
) -> Optional[str]:
    """
    Roda checagens em ordem. Retorna o nome da primeira que der True.
    checagens: [("form_aberto", fn), ("lista_com_nome", fn), ...]
    """
    for nome, fn in checagens:
        try:
            if fn():
                print(f"[Manual] [OK] Reconhecido: {nome}")
                return nome
        except Exception as e:
            print(f"[Manual] checagem {nome}: {e}")
    print("[Manual] [!] Nada reconhecido ainda na tela")
    return None
