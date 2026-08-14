"""
Finalização: Salvar (ou dry-run).
Prints desligados por padrão (PRINTS=0).
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from playwright.sync_api import Page

from utils.paths import OUTPUT_DIR, garantir_pastas


def dry_run_ativo() -> bool:
    v = (os.getenv("DRY_RUN", "1") or "1").strip().lower()
    return v not in ("0", "false", "nao", "não", "no", "off")


def prints_ativos() -> bool:
    """PRINTS=0 (padrão) - não tira screenshot."""
    v = (os.getenv("PRINTS", "0") or "0").strip().lower()
    return v in ("1", "true", "yes", "sim", "on")


def tirar_print(page: Page, nome: str) -> Optional[Path]:
    if not prints_ativos():
        return None
    garantir_pastas()
    pasta = OUTPUT_DIR / "prints"
    pasta.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in nome)[:60]
    path = pasta / f"{ts}_{safe}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"[Print] {path}")
    except Exception as e:
        print(f"[Print] Falhou ({nome}): {e}")
    return path


def texto_pagina(page: Page) -> str:
    try:
        return page.inner_text("body") or ""
    except Exception:
        return ""


def detectar_ja_cadastrado(texto: str) -> Optional[str]:
    """
    Detecta mensagens de duplicidade no GW.
    Retorna tipo: motorista | placa | cpf | cnpj | generico | None
    """
    low = (texto or "").lower()
    padroes = [
        (r"j[aá]\s*(existe|cadastrad|registrad).*motorista", "motorista"),
        (r"motorista\s*j[aá]\s*(existe|cadastrad)", "motorista"),
        (r"cpf\s*j[aá]\s*(existe|cadastrad|utiliz)", "cpf"),
        (r"j[aá]\s*(existe|cadastrad).*cpf", "cpf"),
        (r"placa\s*j[aá]\s*(existe|cadastrad|utiliz)", "placa"),
        (r"j[aá]\s*(existe|cadastrad).*placa", "placa"),
        (r"ve[ií]culo\s*j[aá]\s*(existe|cadastrad)", "placa"),
        (r"cnpj\s*j[aá]\s*(existe|cadastrad)", "cnpj"),
        (r"propriet[aá]rio\s*j[aá]\s*(existe|cadastrad)", "proprietario"),
        (r"registro\s*duplicad|duplicidade|j[aá]\s*cadastrado", "generico"),
    ]
    for pat, tipo in padroes:
        if re.search(pat, low):
            return tipo
    return None


def fechar_alerta_se_houver(page: Page) -> Optional[str]:
    """Fecha dialog/alert e devolve o texto se houver."""
    msg = None
    try:
        # dialogs nativos
        # (Playwright: se já foi aceito via handler, body pode ter o texto)
        pass
    except Exception:
        pass
    # botões OK / Fechar em modais GW
    body = texto_pagina(page)
    tipo = detectar_ja_cadastrado(body)
    if tipo:
        msg = tipo
    for seletor in (
        'button:has-text("OK")',
        'button:has-text("Ok")',
        'button:has-text("Fechar")',
        'input[value="OK"]',
        'a:has-text("OK")',
        '.ui-dialog-buttonset button',
    ):
        try:
            loc = page.locator(seletor).first
            if loc.count() and loc.is_visible(timeout=400):
                loc.click(timeout=1000)
                page.wait_for_timeout(300)
                break
        except Exception:
            continue
    return msg


def salvar_motorista(page: Page, *, dry_run: bool | None = None) -> bool:
    if dry_run is None:
        dry_run = dry_run_ativo()

    if dry_run:
        print("[Fase 7] DRY-RUN - NÃO clica em Salvar (nada gravado).")
        return True

    print("[Fase 7] Clicando em Salvar...")
    from utils.ui_i18n import SELETORES_SALVAR

    url_antes = (page.url or "").lower()

    for seletor in SELETORES_SALVAR:
        try:
            loc = page.locator(seletor).first
            if not loc.count() or not loc.is_visible(timeout=150):
                continue
            loc.click(timeout=1500)
            # GW mantém XHR o tempo todo - domcontentloaded pode travar 20s+.
            # Aguarda apenas um curto período para o GW processar.
            page.wait_for_timeout(800)
            break
        except Exception:
            continue
    else:
        print("[Fase 7] Botão Salvar/Save não encontrado.")
        return False

    page.wait_for_timeout(300)
    dup = detectar_ja_cadastrado(texto_pagina(page))
    if dup:
        print(
            f"[Fase 7] [!] GW indica já cadastrado ({dup}). "
            f"Outra pessoa pode ter registrado - confira na consulta."
        )
        fechar_alerta_se_houver(page)
        return False

    return verificar_sucesso(page, url_antes=url_antes)


def verificar_sucesso(page: Page, *, url_antes: str = "") -> bool:
    page.wait_for_timeout(350)
    body = texto_pagina(page).lower()

    if detectar_ja_cadastrado(body):
        print("[Fase 7] [!] Duplicidade detectada após salvar.")
        return False

    from utils.ui_i18n import TEXTOS_FALHA_SALVAR, TEXTOS_SUCESSO

    sucesso_palavras = TEXTOS_SUCESSO + ("sucesso", "salvo", "gravado", "saved")
    erro_palavras = TEXTOS_FALHA_SALVAR + ("erro", "obrigatório", "inválido", "falha", "error")

    # Erros de validação detectados -> falha definitiva
    if any(p in body for p in erro_palavras):
        print("[Fase 7] [!] Campo obrigatório / erro de validação detectado.")
        return False

    if any(p in body for p in sucesso_palavras):
        print("[Fase 7] ✅ Parece ter salvado com sucesso.")
        return True

    for seletor in (".notification", ".toast", ".alert", ".message", ".snackbar"):
        try:
            txt = page.locator(seletor).first.inner_text(timeout=1500)
            print(f"[Fase 7] Mensagem na tela: {txt}")
            if detectar_ja_cadastrado(txt):
                return False
            if any(p in txt.lower() for p in sucesso_palavras):
                return True
        except Exception:
            continue

    # GW às vezes redireciona para a consulta (URL muda) sem mensagem de sucesso
    url_agora = (page.url or "").lower()
    if url_antes and url_agora != url_antes:
        # saiu do form de edição -> considerado salvo
        if "cadmotorista" not in url_agora or "consulta" in url_agora:
            print("[Fase 7] ✅ URL mudou após Salvar - considerado salvo com sucesso.")
            return True

    # Permanece na aba Operacional do mesmo cadastro - GW às vezes não mostra msg
    if "cadmotorista" in url_agora and ("acao=editar" in url_agora or "id=" in url_agora):
        # verifica se ainda há erros visíveis na página
        if not any(p in body for p in erro_palavras):
            print("[Fase 7] ✅ Ainda no cadastro sem erro - considerado salvo.")
            return True

    print("[Fase 7] [!] Não confirmou sucesso automaticamente - confira no GW.")
    return False
