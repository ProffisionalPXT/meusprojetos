"""
Consulta de Motoristas (codTela=60).

IMPORTANTE (layout real do GW):
  - Sidebar tem abas: Filtros | Ajuda | Auditoria
  - Auditoria tem DATAS - o bot NÃO deve usar isso
  - Busca de motorista: Filtros -> campo CPF -> Pesquisar
"""
from __future__ import annotations

from typing import Optional, Tuple

from playwright.sync_api import Page

from gw_automation.urls import CONSULTA_MOTORISTAS


def avisar_duplicidade_apos_fill(page: Page, contexto: str = "") -> Optional[str]:
    from gw_automation.salvar import detectar_ja_cadastrado, fechar_alerta_se_houver, texto_pagina

    page.wait_for_timeout(400)
    tipo = detectar_ja_cadastrado(texto_pagina(page))
    if tipo:
        print(
            f"[Existente] [!] Já cadastrado ({tipo}) "
            f"{('em ' + contexto) if contexto else ''}"
        )
        fechar_alerta_se_houver(page)
        return tipo
    return None


def tratar_dialog_motorista_ja_cadastrado(page: Page, timeout_ms: int = 4000) -> bool:
    """Dialog: Motorista já cadastrado, deseja visualizá-lo? -> OK."""
    try:
        page.wait_for_timeout(500)
        for _ in range(int(timeout_ms / 400)):
            url = page.url or ""
            if "acao=editar" in url or ("cadmotorista" in url and "id=" in url):
                print("[Existente] [OK] Cadastro existente aberto")
                return True
            for sel in (
                'button:has-text("OK")',
                'button:has-text("Ok")',
                'input[value="OK"]',
                '.ui-dialog-buttonset button:has-text("OK")',
            ):
                try:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible(timeout=200):
                        loc.click(timeout=1000)
                        print("[Existente] OK em 'já cadastrado'")
                        page.wait_for_timeout(1000)
                        break
                except Exception:
                    continue
            page.wait_for_timeout(400)
        url = page.url or ""
        return "editar" in url or ("cadmotorista" in url and "id=" in url)
    except Exception as e:
        print(f"[Existente] dialog: {e}")
        return False


def veiculo_ja_vinculado(page: Page, seletor: str = "#vei_placa") -> bool:
    try:
        val = (page.input_value(seletor, timeout=1000) or "").strip()
        return len(val) >= 6
    except Exception:
        return False


def ir_para_consulta_motoristas(page: Page) -> bool:
    try:
        page.goto(CONSULTA_MOTORISTAS, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1200)
        return True
    except Exception as e:
        print(f"[Consulta] [!] Não abriu: {e}")
        return False


def _form_motorista_aberto(page: Page) -> bool:
    """True se o cadastro do motorista (editar/iniciar) já está aberto."""
    try:
        url = (page.url or "").lower()
        if "cadmotorista" in url and (
            "acao=editar" in url or "acao=alterar" in url or "id=" in url
        ):
            return True
        if "cadmotorista" in url and page.locator(
            'input[name="cpf"], #cpf, input[name="nome"]'
        ).count():
            return True
        for fr in page.frames:
            u = (fr.url or "").lower()
            if "cadmotorista" in u and ("editar" in u or "id=" in u):
                return True
    except Exception:
        pass
    return False


def _tem_nome_na_lista(page: Page) -> bool:
    """
    True se a grid principal da consulta tem linha de resultado com NOME
    (mesmo se o CPF na tela estiver formatado diferente).
    """
    try:
        return bool(
            page.evaluate(
                """() => {
                    const rows = Array.from(document.querySelectorAll(
                        'table tbody tr, table tr'
                    ));
                    for (const tr of rows) {
                        const r = tr.getBoundingClientRect();
                        if (r.width < 250 || r.left < 200) continue;
                        const t = (tr.innerText || '').replace(/\\s+/g, ' ').trim();
                        if (t.length < 8) continue;
                        const u = t.toUpperCase();
                        if (u.includes('NENHUM') || u.startsWith('NOME') && u.includes('CPF'))
                            continue;
                        // nome de pessoa: letras + espaço, ou link azul
                        if (/[A-Za-zÁ-ú]{3,}\\s+[A-Za-zÁ-ú]{2,}/.test(t)) return true;
                        const links = tr.querySelectorAll('a');
                        for (const a of links) {
                            const n = (a.innerText || '').trim();
                            if (n.length >= 4 && /[A-Za-zÁ-ú]{3,}/.test(n)
                                && !/^\\d+$/.test(n)
                                && !/editar|excluir|pesquisar/i.test(n)) {
                                return true;
                            }
                        }
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


def _abrir_editar_primeira_linha(page: Page) -> bool:
    """Quando a lista tem 1 resultado (você pesquisou) e o robô não achou o CPF no texto."""
    try:
        clicou = page.evaluate(
            """() => {
                const rows = Array.from(document.querySelectorAll(
                    'table tbody tr, table tr'
                )).filter(tr => {
                    const r = tr.getBoundingClientRect();
                    if (r.width < 250 || r.left < 200) return false;
                    const t = (tr.innerText || '').trim();
                    return t.length > 8 && !/nenhum/i.test(t);
                });
                if (!rows.length) return '';
                const tr = rows[0];
                // lápis / edit
                const els = Array.from(tr.querySelectorAll('a, button, img, i, span'));
                for (const el of els) {
                    const meta = (
                        (el.getAttribute('title')||'') + ' ' +
                        (el.getAttribute('href')||'') + ' ' +
                        (el.getAttribute('src')||'') + ' ' +
                        (el.className||'')
                    ).toLowerCase();
                    if (meta.includes('edit') || meta.includes('editar') ||
                        meta.includes('pencil') || meta.includes('lapis') ||
                        meta.includes('lápis') || meta.includes('glyphicon-pencil')) {
                        (el.closest('a') || el).click();
                        return 'pencil';
                    }
                }
                const icons = Array.from(tr.querySelectorAll('td a, td img, td button'))
                    .filter(el => {
                        const rr = el.getBoundingClientRect();
                        return rr.width > 0 && rr.height > 0 && rr.width < 48;
                    });
                if (icons.length >= 2) {
                    (icons[1].closest('a') || icons[1]).click();
                    return '2nd-icon';
                }
                const nameLinks = Array.from(tr.querySelectorAll('a')).filter(a => {
                    const n = (a.innerText || '').trim();
                    return n.length >= 4 && /[A-Za-zÁ-ú]{3,}/.test(n) && !/^\\d+$/.test(n);
                });
                if (nameLinks.length) {
                    nameLinks[0].click();
                    return 'name';
                }
                tr.dispatchEvent(new MouseEvent('dblclick', {bubbles:true}));
                return 'dblclick';
            }"""
        )
        if not clicou:
            return False
        page.wait_for_timeout(900)
        try:
            tratar_dialog_motorista_ja_cadastrado(page, timeout_ms=1500)
        except Exception:
            pass
        for _ in range(10):
            if _form_motorista_aberto(page):
                print(f"[Consulta] [OK] Editar 1ª linha da lista ({clicou})")
                return True
            page.wait_for_timeout(350)
        return _form_motorista_aberto(page)
    except Exception as e:
        print(f"[Consulta] 1ª linha: {e}")
        return False


def _reconhecer_e_continuar_consulta(page: Page, dig: str) -> Tuple[bool, str]:
    """
    Depois da 3ª tentativa (você fez filtro/pesquisa):
    olha o que já está na tela e executa a próxima operação (Editar).
    """
    dig = "".join(c for c in (dig or "") if c.isdigit())
    print("[Consulta] Reconhecendo o que já está na tela...")

    if _form_motorista_aberto(page):
        print("[Consulta] [OK] Form do motorista já estava aberto")
        return True, "aberto_existente"

    # Nome / CPF já na lista -> clica Editar
    if _tem_resultado_cpf(page, dig):
        print(f"[Consulta] [OK] CPF {dig} na lista - abrindo Editar")
        if _abrir_editar_motorista(page, dig):
            return True, "aberto_existente"
        if _abrir_editar_motorista(page, dig, forcar_botao_editar=True):
            return True, "aberto_existente"
        if _abrir_editar_primeira_linha(page):
            return True, "aberto_existente"
        return True, "existe_nao_abriu"

    if _tem_nome_na_lista(page) and not _lista_vazia(page):
        print("[Consulta] [OK] Nome apareceu na lista - abrindo Editar")
        if dig and _abrir_editar_motorista(page, dig):
            return True, "aberto_existente"
        if _abrir_editar_primeira_linha(page):
            return True, "aberto_existente"
        if dig and _abrir_editar_motorista(page, dig, forcar_botao_editar=True):
            return True, "aberto_existente"
        return True, "existe_nao_abriu"

    # Você só trocou o filtro - se já for CPF, tenta 1x digitar+pesquisar sem loop
    if _filtro_atual_eh_cpf(page):
        print("[Consulta] Filtro já em CPF - uma tentativa rápida de digitar+Pesquisar")
        if _pesquisar_cpf_na_aba_filtros(page, dig, so_digitar_se_filtro_ok=True):
            return _reconhecer_e_continuar_consulta_apos_pesq(page, dig)

    if _lista_vazia(page):
        print(f"[Consulta] Lista vazia após intervenção - CPF {dig} não encontrado")
        return False, "nao_encontrado"

    print("[Consulta] [!] Não reconheci resultado útil - tenta Editar genérico")
    if dig and _abrir_editar_motorista(page, dig, forcar_botao_editar=True):
        return True, "aberto_existente"
    if _abrir_editar_primeira_linha(page):
        return True, "aberto_existente"
    return False, "manual_sem_resultado"


def _reconhecer_e_continuar_consulta_apos_pesq(page: Page, dig: str) -> Tuple[bool, str]:
    if _form_motorista_aberto(page):
        return True, "aberto_existente"
    if not _tem_resultado_cpf(page, dig) and _lista_vazia(page):
        return False, "nao_encontrado"
    if _abrir_editar_motorista(page, dig) or _abrir_editar_motorista(
        page, dig, forcar_botao_editar=True
    ):
        return True, "aberto_existente"
    if _tem_nome_na_lista(page) and _abrir_editar_primeira_linha(page):
        return True, "aberto_existente"
    if not _lista_vazia(page):
        return True, "existe_nao_abriu"
    return False, "nao_encontrado"


def _tentar_abrir_editar_apos_lista(page: Page, dig: str) -> Tuple[bool, str]:
    page.wait_for_timeout(200)
    if not _tem_resultado_cpf(page, dig) and _lista_vazia(page):
        print(f"[Consulta] CPF {dig} não encontrado na lista")
        return False, "nao_encontrado"

    if not _tem_resultado_cpf(page, dig):
        print(
            f"[Consulta] [!] Lista tem linhas mas CPF {dig} não identificado - "
            "tenta Editar (lápis) mesmo assim"
        )

    # Nome já na lista -> clica lápis AGORA (não fica parado)
    print("[Consulta] Clicando no lápis Editar da linha...")
    if _abrir_editar_motorista(page, dig):
        print(f"[Consulta] [OK] Editar motorista {dig}")
        page.wait_for_timeout(400)
        return True, "aberto_existente"

    page.wait_for_timeout(250)
    if _abrir_editar_motorista(page, dig, forcar_botao_editar=True):
        print(f"[Consulta] [OK] Editar motorista {dig} (2ª no Editar)")
        page.wait_for_timeout(400)
        return True, "aberto_existente"

    if _tem_nome_na_lista(page) and _abrir_editar_primeira_linha(page):
        page.wait_for_timeout(400)
        return True, "aberto_existente"

    print("[Consulta] [!] Resultado na lista mas botão Editar não abriu o form")
    return True, "existe_nao_abriu"


def pesquisar_motorista_por_cpf(page: Page, cpf: str) -> Tuple[bool, str]:
    """
    1ª e 2ª: robô sozinho (Filtro CPF -> digita -> Pesquisar -> Editar)
    3ª: você faz; o robô reconhece nome/lista e clica Editar
    """
    from utils.manual import max_tentativas_auto, pausar_para_manual

    dig = "".join(c for c in (cpf or "") if c.isdigit())
    if len(dig) < 11:
        return False, "cpf inválido"

    max_auto = max_tentativas_auto()
    print(
        f"[Consulta] Fluxo: CPF -> Pesquisar -> Editar | CPF={dig} "
        f"(auto {max_auto}x + manual)"
    )

    for t in range(1, max_auto + 1):
        print(f"\n[Consulta] ▶ Tentativa automática {t}/{max_auto}")
        if _form_motorista_aberto(page):
            print("[Consulta] [OK] Form já aberto")
            return True, "aberto_existente"

        if not ir_para_consulta_motoristas(page):
            print(f"[Consulta] Auto {t}: consulta offline")
            continue

        _fechar_auditoria_abrir_filtros(page)

        if not _pesquisar_cpf_na_aba_filtros(page, dig):
            print(f"[Consulta] Auto {t}: pesquisa falhou (filtro/digitar/Pesquisar)")
            continue

        ok, det = _tentar_abrir_editar_apos_lista(page, dig)
        if ok and det == "aberto_existente":
            return True, det
        if det == "nao_encontrado":
            # motorista novo - não é falha de UI
            return False, "nao_encontrado"
        if ok and det == "existe_nao_abriu":
            print(f"[Consulta] Auto {t}: lista ok, Editar falhou - tenta de novo se houver")
            continue

    # ----- 3ª: você -----
    r = pausar_para_manual(
        f"Não abri o motorista pelo CPF {dig} em {max_auto} tentativas automáticas.",
        dica=(
            "Na Consulta: troque Filtro -> CPF, digite o CPF, clique Pesquisar. "
            "Quando o NOME do motorista aparecer na lista, aperte ENTER - "
            "o robô reconhece e clica Editar (lápis)."
        ),
        page=page,
        tentativa=max_auto + 1,
        total_auto=max_auto,
    )
    if r == "skip":
        return False, "manual_pulado"
    if r == "disabled":
        return False, "falhou_auto"

    return _reconhecer_e_continuar_consulta(page, dig)


def reabrir_motorista_por_cpf(page: Page, cpf: str) -> bool:
    dig = "".join(c for c in (cpf or "") if c.isdigit())
    if len(dig) < 11:
        return False
    print(f"[Consulta] Reabrir: Pesquisar CPF={dig} -> clicar Editar")
    ok, det = pesquisar_motorista_por_cpf(page, dig)
    if ok and det == "aberto_existente":
        return True
    if ok and det == "existe_nao_abriu":
        print("[Consulta] Lista tinha resultado - tentando Editar de novo...")
        if _abrir_editar_motorista(page, dig, forcar_botao_editar=True):
            return True
        if _abrir_editar_primeira_linha(page):
            return True
        # última chance: você de novo só no Editar
        from utils.manual import pausar_para_manual

        r = pausar_para_manual(
            "Nome/CPF na lista mas o form não abriu.",
            dica="Clique no lápis Editar (ou no nome). Quando o form abrir, ENTER.",
            page=page,
            tentativa=3,
            total_auto=2,
        )
        if r == "ok":
            if _form_motorista_aberto(page):
                return True
            if _abrir_editar_primeira_linha(page) or _abrir_editar_motorista(
                page, dig, forcar_botao_editar=True
            ):
                return _form_motorista_aberto(page)
    return False


# ---------------------------------------------------------------------------
# Sidebar: Filtros vs Auditoria
# ---------------------------------------------------------------------------

def _painel_filtros_ja_aberto(page: Page) -> bool:
    """True se a sidebar de Filtros já está aberta (não Auditoria)."""
    try:
        return bool(
            page.evaluate(
                """() => {
                    // botão vertical "Ocultar filtros" = painel aberto
                    const nodes = Array.from(document.querySelectorAll(
                        'button, a, span, div, td, li, label'
                    ));
                    for (const el of nodes) {
                        if (el.offsetParent === null) continue;
                        const t = (el.innerText || el.textContent || '')
                            .replace(/\\s+/g, ' ').trim().toLowerCase();
                        if (t === 'ocultar filtros' || t === 'ocultar filtro') return true;
                    }
                    // label "Filtro" + combo Nome/CPF (mesmo se select nativo estiver display:none)
                    const hasLabel = nodes.some(el => {
                        if (el.offsetParent === null) return false;
                        const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                        return /^Filtro\\s*:?$/i.test(t);
                    });
                    if (!hasLabel) return false;
                    // qualquer select com NOME+CPF (oculto ok - UI custom do GW)
                    for (const s of document.querySelectorAll('select')) {
                        const opts = Array.from(s.options || []).map(
                            o => (o.textContent || '').trim().toUpperCase()
                        );
                        const hasNome = opts.some(t => t === 'NOME' || t.startsWith('NOME'));
                        const hasCpf = opts.some(t => t === 'CPF' || t.startsWith('CPF'));
                        if (hasNome && hasCpf) return true;
                    }
                    // input de pesquisa na sidebar esquerda
                    for (const el of document.querySelectorAll('input')) {
                        if (el.offsetParent === null) continue;
                        const ty = (el.type || '').toLowerCase();
                        if (ty === 'hidden' || ty === 'date' || ty === 'checkbox') continue;
                        const r = el.getBoundingClientRect();
                        if (r.width >= 80 && r.left < 480 && r.top < 700) return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


def _fechar_auditoria_abrir_filtros(page: Page) -> None:
    """
    Se a aba Auditoria (datas) estiver aberta, fecha e abre Filtros.
    Print real: botões verticais 'Exibir Filtros' / 'Ocultar Auditoria'.

    CUIDADO: NÃO usar seletor genérico text=Filtros - casa com
    "Ocultar filtros" e FECHA o painel (bug que abortava a digitação do CPF).
    """
    # 0) Já aberto? não mexe
    if _painel_filtros_ja_aberto(page):
        print("[Consulta] Painel Filtros já visível")
        return

    # 1) Fechar painel de Auditoria se visível (tem campos de data)
    try:
        if page.locator('text=Auditoria').first.is_visible(timeout=500):
            # se tem input type=date ou "até" + calendário, está na auditoria
            if page.locator('input[type="date"], text=até, text=ate').count():
                for sel in (
                    'button:has-text("Ocultar Auditoria")',
                    'a:has-text("Ocultar Auditoria")',
                    'text=Ocultar Auditoria',
                    '[title*="Ocultar Auditoria" i]',
                ):
                    try:
                        loc = page.locator(sel).first
                        if loc.count() and loc.is_visible(timeout=300):
                            loc.click(timeout=1500)
                            print("[Consulta] Ocultou Auditoria (datas)")
                            page.wait_for_timeout(400)
                            break
                    except Exception:
                        continue
    except Exception:
        pass

    if _painel_filtros_ja_aberto(page):
        print("[Consulta] Painel Filtros já visível")
        return

    # 2) Abrir Filtros se estiverem ocultos
    #    SOMENTE "Exibir Filtros" - nunca "Ocultar filtros" / text=Filtros genérico
    for sel in (
        'button:has-text("Exibir Filtros")',
        'a:has-text("Exibir Filtros")',
        'text=Exibir Filtros',
        '[title*="Exibir Filtros" i]',
        '[title*="Exibir filtro" i]',
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=400):
                txt = ""
                try:
                    txt = (loc.inner_text(timeout=200) or "").strip().lower()
                except Exception:
                    pass
                # blindagem: se o texto for "ocultar...", não clica
                if "ocultar" in txt:
                    continue
                loc.click(timeout=1500)
                print("[Consulta] Clicou Exibir Filtros")
                page.wait_for_timeout(500)
                break
        except Exception:
            continue

    # 3) Garantir que não estamos na aba Auditoria (tabs)
    #    Só clica em tab exatamente "Filtros" (não "Ocultar filtros")
    for sel in (
        '[role="tab"]:has-text("Filtros")',
        'a[role="tab"]:has-text("Filtros")',
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=300):
                t = (loc.inner_text(timeout=200) or "").strip().lower()
                if t in ("filtros", "filtro") or t.startswith("filtros"):
                    if "ocultar" not in t and "exibir" not in t:
                        loc.click(timeout=1000)
                        page.wait_for_timeout(300)
                break
        except Exception:
            continue


def _tem_combo_filtro_cpf_visivel(page: Page) -> bool:
    """True se existe o combo Filtro (Nome|CPF) - select pode estar display:none."""
    try:
        return bool(
            page.evaluate(
                """() => {
                    for (const s of document.querySelectorAll('select')) {
                        const opts = Array.from(s.options||[]).map(
                            o => (o.textContent||'').trim().toUpperCase()
                        );
                        if (!opts.length) continue;
                        const hasNome = opts.some(t => t === 'NOME' || t.startsWith('NOME'));
                        const hasCpf = opts.some(t => t === 'CPF' || t.startsWith('CPF'));
                        if (hasNome && hasCpf
                            && !opts.some(t => t.includes('CRESC') || t.includes('PARTES')))
                            return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


def limpar_filtros_pesquisa_anteriores(page: Page) -> int:
    """Compat: limpa chips + tenta resetar pesquisa salva."""
    _limpar_chips_e_campo_filtro(page)
    return 0


# JS compartilhado: identifica o <select> do campo Filtro (Nome|CPF|...).
# NÃO exige offsetParent - no GW o select nativo costuma estar display:none
# com UI custom por cima (por isso o bot “via” CPF na tela e ainda assim abortava).
_JS_IS_FILTRO_CAMPO = """
function isFiltroCampo(s) {
    if (!s || !s.options || !s.options.length) return false;
    const opts = Array.from(s.options).map(
        o => (o.textContent || '').trim().toUpperCase().replace(/\\s+/g, ' ')
    );
    const hasNome = opts.some(t => t === 'NOME' || t.startsWith('NOME ') || t.startsWith('NOME/'));
    const hasCpf = opts.some(t => t === 'CPF' || t.startsWith('CPF'));
    if (!hasNome || !hasCpf) return false;
    if (opts.some(t => t.includes('CRESC') || t.includes('DECRESC'))) return false;
    if (opts.some(t =>
        t.includes('TODAS AS PARTES') || t.includes('INICIA COM') ||
        t.includes('QUALQUER') || t.includes('TERMINA')
    )) return false;
    return true;
}
function textoOpcao(s) {
    const o = s.options[s.selectedIndex];
    return ((o && o.textContent) || '').trim().toUpperCase().replace(/\\s+/g, ' ');
}
function ehCpf(cur) {
    return cur === 'CPF' || cur.startsWith('CPF ') || cur.startsWith('CPF/') || cur.startsWith('CPF-');
}
"""


def _filtro_atual_eh_cpf(page: Page) -> bool:
    """True se o combo Filtro (Nome/CPF) está em CPF (select oculto ou UI visível)."""
    try:
        return bool(
            page.evaluate(
                f"""() => {{
                    {_JS_IS_FILTRO_CAMPO}
                    // 1) select nativo (mesmo display:none)
                    for (const s of document.querySelectorAll('select')) {{
                        if (!isFiltroCampo(s)) continue;
                        if (ehCpf(textoOpcao(s))) return true;
                    }}
                    // 2) UI custom: texto visível "CPF" logo após o label Filtro
                    const labs = Array.from(document.querySelectorAll(
                        'label, span, div, td, th, strong, b, p'
                    ));
                    for (const lab of labs) {{
                        if (lab.offsetParent === null) continue;
                        const t = (lab.innerText || '').replace(/\\s+/g, ' ').trim();
                        if (!/^Filtro\\s*:?$/i.test(t)) continue;
                        let el = lab.nextElementSibling;
                        for (let i = 0; i < 10 && el; i++) {{
                            const vis = (el.innerText || el.textContent || '')
                                .replace(/\\s+/g, ' ').trim().toUpperCase();
                            // select nativo ou display do chosen/select2
                            if (ehCpf(vis.split('\\n')[0].trim())) return true;
                            const sel = el.tagName === 'SELECT' ? el : el.querySelector('select');
                            if (sel && isFiltroCampo(sel) && ehCpf(textoOpcao(sel))) return true;
                            // option selected text em widgets
                            const a = el.querySelector && el.querySelector(
                                'option:checked, .selected, [aria-selected="true"], .select2-selection__rendered, .chosen-single span'
                            );
                            if (a) {{
                                const at = (a.innerText || a.textContent || '')
                                    .trim().toUpperCase();
                                if (ehCpf(at)) return true;
                            }}
                            el = el.nextElementSibling;
                        }}
                        if (lab.parentElement) {{
                            const box = lab.parentElement;
                            const raw = (box.innerText || '').replace(/\\s+/g, ' ').trim();
                            // "Filtro CPF" / "Filtro\\nCPF"
                            if (/Filtro\\s+CPF\\b/i.test(raw)) return true;
                        }}
                    }}
                    return false;
                }}"""
            )
        )
    except Exception:
        return False


def _selecionar_filtro_cpf(page: Page) -> bool:
    """
    Força o combo da sidebar: Filtro = CPF (não Nome).

    Print real (Consulta Motoristas codTela=60):
      label "Filtro" + <select> com Nome | CPF | ...
      Se ficar em Nome, digitar o CPF cria chip de NOME e a grid traz
      resultado errado (ex.: ALEX V + chip 02269831535 -> outro motorista).
    """
    if _filtro_atual_eh_cpf(page):
        print("[Consulta] [OK] Filtro já está em CPF")
        return True

    # 0) Dump diagnóstico - inclui selects OCULTOS (display:none)
    try:
        info = page.evaluate(
            f"""() => {{
                {_JS_IS_FILTRO_CAMPO}
                const out = [];
                for (const s of document.querySelectorAll('select')) {{
                    const opts = Array.from(s.options||[]).map(o =>
                        ((o.textContent||'').trim() + '|' + (o.value||'')).slice(0,40)
                    );
                    if (!opts.length) continue;
                    const cur = ((s.options[s.selectedIndex]||{{}}).textContent||'').trim();
                    const r = s.getBoundingClientRect();
                    const st = window.getComputedStyle(s);
                    out.push({{
                        cur, opts: opts.slice(0,12),
                        id: s.id||'', name: s.name||'',
                        filtro: isFiltroCampo(s),
                        display: st.display, vis: s.offsetParent !== null,
                        left: Math.round(r.left)
                    }});
                }}
                return out;
            }}"""
        )
        # prioriza os que parecem filtro
        if info:
            relevantes = [x for x in info if x.get("filtro")] or info[:6]
            print(f"[Consulta] selects (diag): {relevantes[:4]}")
    except Exception as e:
        print(f"[Consulta] diag selects: {e}")

    def _set_select_cpf_js() -> bool:
        return bool(
            page.evaluate(
                f"""() => {{
                    {_JS_IS_FILTRO_CAMPO}
                    function forceCpf(s) {{
                        const hit = Array.from(s.options).find(o => {{
                            const t = (o.textContent || '').trim().toUpperCase().replace(/\\s+/g, ' ');
                            return t === 'CPF' || t === 'CPF/CNPJ' || t.startsWith('CPF');
                        }});
                        if (!hit) return false;
                        for (const o of s.options) o.selected = false;
                        hit.selected = true;
                        s.selectedIndex = hit.index;
                        s.value = hit.value;
                        try {{ s.focus(); }} catch(e) {{}}
                        for (const type of ['mousedown','mouseup','click','input','change','blur']) {{
                            try {{
                                s.dispatchEvent(new Event(type, {{bubbles: true, cancelable: true}}));
                            }} catch(e) {{}}
                        }}
                        try {{
                            const ev = document.createEvent('HTMLEvents');
                            ev.initEvent('change', true, false);
                            s.dispatchEvent(ev);
                        }} catch(e) {{}}
                        if (window.jQuery) {{
                            try {{
                                window.jQuery(s).val(hit.value)
                                    .trigger('change')
                                    .trigger('chosen:updated')
                                    .trigger('liszt:updated')
                                    .trigger('select2:select');
                            }} catch(e) {{}}
                        }}
                        try {{ if (typeof s.onchange === 'function') s.onchange(); }} catch(e) {{}}
                        return ehCpf(textoOpcao(s));
                    }}
                    // label Filtro (irmão / pai)
                    for (const lab of document.querySelectorAll('label, span, div, td, th, strong')) {{
                        const t = (lab.innerText || '').trim();
                        if (!/^Filtro\\s*:?$/i.test(t) && t.toUpperCase() !== 'FILTRO') continue;
                        let el = lab.nextElementSibling;
                        for (let i = 0; i < 8 && el; i++) {{
                            if (el.tagName === 'SELECT' && isFiltroCampo(el) && forceCpf(el)) return true;
                            const inn = el.querySelector && el.querySelector('select');
                            if (inn && isFiltroCampo(inn) && forceCpf(inn)) return true;
                            el = el.nextElementSibling;
                        }}
                        if (lab.parentElement) {{
                            const s = lab.parentElement.querySelector('select');
                            if (s && isFiltroCampo(s) && forceCpf(s)) return true;
                        }}
                    }}
                    // qualquer select Nome+CPF (oculto ok)
                    for (const s of document.querySelectorAll('select')) {{
                        if (isFiltroCampo(s) && forceCpf(s)) return true;
                    }}
                    return false;
                }}"""
            )
        )

    # 1) JS direto (funciona com select display:none)
    if _set_select_cpf_js():
        page.wait_for_timeout(350)
        if _filtro_atual_eh_cpf(page):
            print("[Consulta] [OK] Filtro = CPF (JS force)")
            return True
        # JS setou o value mas UI custom pode não refletir - confia no selectedIndex
        print("[Consulta] [OK] Filtro = CPF (JS force, value setado)")
        return True

    # 2) Playwright select_option - também em select NÃO visível (force)
    try:
        n = page.locator("select").count()
        for i in range(min(n, 25)):
            sel = page.locator("select").nth(i)
            try:
                opts = [(o or "").strip() for o in sel.locator("option").all_text_contents()]
                ups = [o.upper().replace("  ", " ") for o in opts]
                if not any(u == "NOME" or u.startswith("NOME") for u in ups):
                    continue
                if not any(u == "CPF" or u.startswith("CPF") for u in ups):
                    continue
                if any("CRESC" in u or "PARTES" in u or "INICIA" in u for u in ups):
                    continue
                idx_cpf = next(
                    (j for j, u in enumerate(ups) if u == "CPF" or u.startswith("CPF")),
                    -1,
                )
                if idx_cpf < 0:
                    continue
                label_cpf = opts[idx_cpf]
                ok_pw = False
                for modo in ("label", "index", "value"):
                    try:
                        if modo == "label":
                            sel.select_option(label=label_cpf, force=True)
                        elif modo == "index":
                            sel.select_option(index=idx_cpf, force=True)
                        else:
                            val = sel.locator("option").nth(idx_cpf).get_attribute("value")
                            if val is None:
                                continue
                            sel.select_option(value=val, force=True)
                        ok_pw = True
                        break
                    except Exception:
                        continue
                if not ok_pw:
                    continue
                try:
                    sel.evaluate(
                        """s => {
                            s.dispatchEvent(new Event('change', {bubbles:true}));
                            if (window.jQuery) try { window.jQuery(s).trigger('change'); } catch(e) {}
                        }"""
                    )
                except Exception:
                    pass
                page.wait_for_timeout(350)
                if _filtro_atual_eh_cpf(page):
                    print(f"[Consulta] [OK] Filtro = CPF (Playwright {label_cpf!r})")
                    return True
                # mesmo sem detecção visual, value foi setado
                print(f"[Consulta] [OK] Filtro = CPF (Playwright force {label_cpf!r})")
                return True
            except Exception:
                continue
    except Exception as e:
        print(f"[Consulta] select Playwright: {e}")

    # 3) Teclado: tenta focar select visível OU o wrapper custom
    try:
        ok_kb = page.evaluate(
            f"""() => {{
                {_JS_IS_FILTRO_CAMPO}
                const s = Array.from(document.querySelectorAll('select')).find(isFiltroCampo);
                if (!s) return false;
                // se oculto, tenta clicar no chosen/select2 irmão
                if (s.offsetParent === null) {{
                    const wrap = s.parentElement;
                    if (wrap) {{
                        const fake = wrap.querySelector(
                            '.chosen-single, .select2-selection, a, button, [role="combobox"]'
                        );
                        if (fake) {{ fake.click(); return true; }}
                    }}
                }}
                try {{ s.focus(); s.click(); }} catch(e) {{}}
                return true;
            }}"""
        )
        if ok_kb:
            for _ in range(6):
                page.keyboard.press("c")
                page.wait_for_timeout(80)
                if _filtro_atual_eh_cpf(page):
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(200)
                    print("[Consulta] [OK] Filtro = CPF (teclado C)")
                    return True
            page.keyboard.press("Home")
            for _ in range(12):
                page.keyboard.press("ArrowDown")
                page.wait_for_timeout(60)
                if _filtro_atual_eh_cpf(page):
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(200)
                    print("[Consulta] [OK] Filtro = CPF (setas)")
                    return True
    except Exception as e:
        print(f"[Consulta] teclado filtro: {e}")

    # 4) Última chance: JS de novo
    if _set_select_cpf_js():
        page.wait_for_timeout(400)
        print("[Consulta] [OK] Filtro = CPF (JS 2ª)")
        return True

    if _filtro_atual_eh_cpf(page):
        print("[Consulta] [OK] Filtro = CPF (confirmado)")
        return True
    print("[Consulta] [!] select CPF NÃO setado - ainda em Nome (chips de nome vão poluir a busca)")
    return False


def _limpar_chips_e_campo_filtro(page: Page) -> None:
    """
    Remove TODOS os chips da sidebar (print: × ALEX V  × 02269831535).
    Se sobrar chip de nome/CPF antigo, a pesquisa mistura e Editar falha.
    """
    removidos = 0
    try:
        for _ in range(40):
            n = page.evaluate(
                """() => {
                    const LEFT = 520;
                    // 0) seletores clássicos de token/chip (bootstrap-tagsinput, chosen, etc.)
                    const css = [
                        '.bootstrap-tagsinput [data-role="remove"]',
                        '.bootstrap-tagsinput .tag [data-role="remove"]',
                        '.token-input-delete-token',
                        '.token .close', '.token-label + a',
                        '.select2-selection__choice__remove',
                        '.chip .close', '.tag .close',
                        '[class*="chip"] [class*="close"]',
                        '[class*="token"] [class*="close"]',
                        '[class*="tag"] [class*="remove"]',
                        'a.close', 'button.close',
                        'span[onclick*="remove"]', 'a[onclick*="remove"]',
                        'a[onclick*="Remove"]', 'span[onclick*="Remove"]',
                    ];
                    for (const sel of css) {
                        for (const el of document.querySelectorAll(sel)) {
                            if (el.offsetParent === null) continue;
                            const r = el.getBoundingClientRect();
                            if (r.left > LEFT || r.width === 0) continue;
                            el.click();
                            return 1;
                        }
                    }
                    // 1) qualquer × / x pequeno na sidebar (filho do chip)
                    const nodes = Array.from(document.querySelectorAll(
                        'span, a, i, button, em, b, div, small, label, font'
                    ));
                    for (const el of nodes) {
                        if (el.offsetParent === null) continue;
                        const r = el.getBoundingClientRect();
                        if (r.left > LEFT || r.top > 780) continue;
                        if (r.width > 48 || r.height > 40) continue;
                        const t = (el.innerText || el.textContent || '').trim();
                        // × sozinho OU "×" com zero-width
                        if (/^[×xX✕✖⊗⨯\\u00d7\\u2715\\u2716]\\s*$/.test(t)) {
                            el.click();
                            return 1;
                        }
                        const cls = (el.className || '').toString().toLowerCase();
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        const title = (el.getAttribute('title') || '').toLowerCase();
                        if (
                            (cls.includes('close') || cls.includes('remove') ||
                             cls.includes('delete') || cls.includes('clear') ||
                             aria.includes('remov') || aria.includes('clear') ||
                             title.includes('remov') || title.includes('limpar') ||
                             title.includes('excluir')) &&
                            r.left < LEFT && r.width < 40
                        ) {
                            el.click();
                            return 1;
                        }
                    }
                    // 2) chip inteiro "× ALEX V" / "× 02269831535" - clica no × (esquerda do chip)
                    for (const el of nodes) {
                        if (el.offsetParent === null) continue;
                        const r = el.getBoundingClientRect();
                        if (r.left > 480 || r.width < 30 || r.width > 320) continue;
                        if (r.height > 50 || r.top > 780) continue;
                        const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                        // começa com × e tem texto de filtro
                        if (!/^[×xX✕✖\\u00d7]\\s*\\S+/.test(t)) continue;
                        if (t.length > 50) continue;
                        // clica na borda esquerda do chip (onde fica o ×)
                        const child = el.querySelector(
                            'a, span, i, b, button, [class*="close"], [class*="remove"]'
                        );
                        if (child) { child.click(); return 1; }
                        // click sintético na esquerda
                        try {
                            const ev = new MouseEvent('click', {
                                bubbles: true, cancelable: true, view: window,
                                clientX: r.left + 8, clientY: r.top + r.height/2
                            });
                            el.dispatchEvent(ev);
                            return 1;
                        } catch(e) {
                            el.click();
                            return 1;
                        }
                    }
                    return 0;
                }"""
            )
            if not n:
                break
            removidos += int(n)
            page.wait_for_timeout(120)
        if removidos:
            print(f"[Consulta] Limpou {removidos} chip(s) de filtro")
    except Exception as e:
        print(f"[Consulta] limpar chips: {e}")

    # Playwright: clica × visíveis na sidebar (texto literal)
    try:
        for _ in range(15):
            clicou = False
            for sel in (
                'text=×',
                'text=✕',
                '[aria-label*="Remover" i]',
                '[title*="Remover" i]',
                '[title*="Excluir" i]',
                '.close',
            ):
                try:
                    locs = page.locator(sel)
                    for i in range(min(locs.count(), 8)):
                        loc = locs.nth(i)
                        if not loc.is_visible(timeout=100):
                            continue
                        box = loc.bounding_box()
                        if not box or box["x"] > 520 or box["width"] > 50:
                            continue
                        loc.click(timeout=500)
                        clicou = True
                        removidos += 1
                        page.wait_for_timeout(100)
                        break
                    if clicou:
                        break
                except Exception:
                    continue
            if not clicou:
                break
    except Exception:
        pass

    # limpa inputs de texto da sidebar (valor digitado antes do chip)
    try:
        page.evaluate(
            """() => {
                for (const el of document.querySelectorAll('input')) {
                    if (el.offsetParent === null) continue;
                    const t = (el.type||'').toLowerCase();
                    if (t === 'date' || t === 'hidden' || t === 'checkbox' || t === 'radio'
                        || t === 'submit' || t === 'button') continue;
                    const r = el.getBoundingClientRect();
                    if (r.width < 60 || r.left > 480) continue;
                    el.focus();
                    el.value = '';
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                    if (window.jQuery) {
                        try { window.jQuery(el).val('').trigger('change'); } catch(e) {}
                    }
                }
            }"""
        )
    except Exception:
        pass

    # reseleciona "Pesquisas salvas" se houver opção vazia / limpar
    try:
        page.evaluate(
            """() => {
                for (const s of document.querySelectorAll('select')) {
                    if (s.offsetParent === null) continue;
                    const r = s.getBoundingClientRect();
                    if (r.left > 520) continue;
                    const opts = Array.from(s.options || []).map(
                        o => (o.textContent || '').trim().toUpperCase()
                    );
                    // combo de pesquisas salvas
                    if (!opts.some(t => t.includes('ULTIMA') || t.includes('ÚLTIMA')
                        || t.includes('PESQUISA') || t.includes('SALVA'))) continue;
                    // tenta opção vazia / "Selecione" / primeira
                    const blank = Array.from(s.options).find(o => {
                        const t = (o.textContent || '').trim();
                        return !t || /^selecione/i.test(t) || t === '-' || t === '-';
                    });
                    if (blank) {
                        s.value = blank.value;
                        s.dispatchEvent(new Event('change', {bubbles:true}));
                    }
                }
            }"""
        )
    except Exception:
        pass

    if removidos:
        print(f"[Consulta] Total chips removidos: {removidos}")


def _clicar_botao_pesquisar(page: Page) -> bool:
    """
    Backup: tenta clicar seta/botão Pesquisar da sidebar.
    Não é mais chamada no fluxo principal - o bot usa Enter após o chip.
    Mantida para uso eventual em reconhecimento manual.
    """
    # -1) Prioridade: Enter diretamente no input da sidebar (mais confiável no GW)
    try:
        entrou = page.evaluate(
            """() => {
                const inputs = Array.from(document.querySelectorAll('input')).filter(el => {
                    if (el.offsetParent === null) return false;
                    const t = (el.type||'').toLowerCase();
                    if (t === 'date' || t === 'hidden' || t === 'checkbox' || t === 'radio'
                        || t === 'submit' || t === 'button') return false;
                    const r = el.getBoundingClientRect();
                    return r.left < 520 && r.width > 60 && r.y < 700;
                });
                if (inputs.length === 0) return false;
                const inp = inputs[0];
                inp.focus();
                inp.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                }));
                inp.dispatchEvent(new KeyboardEvent('keyup', {
                    key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                }));
                return true;
            }"""
        )
        if entrou:
            page.keyboard.press("Enter")
            page.wait_for_timeout(400)
            print("[Consulta] [OK] Pesquisar via Enter no input da sidebar")
            return True
    except Exception as e:
        print(f"[Consulta] Enter sidebar: {e}")

    # 0) Seta / botão ao lado do input de filtro (sidebar esquerda)
    try:
        ok_seta = page.evaluate(
            """() => {
                // botões/setas perto dos inputs da sidebar (left < 620 para cobrir sidebars largas)
                const cands = Array.from(document.querySelectorAll(
                    'button, a, input[type="button"], input[type="submit"], span, i, img'
                ));
                for (const el of cands) {
                    if (el.offsetParent === null) continue;
                    const r = el.getBoundingClientRect();
                    if (r.left > 620 || r.width < 8 || r.width > 80 || r.height < 8) continue;
                    const meta = (
                        (el.getAttribute('title')||'') + ' ' +
                        (el.getAttribute('class')||'') + ' ' +
                        (el.getAttribute('onclick')||'') + ' ' +
                        (el.innerText||'') + ' ' + (el.value||'')
                    ).toLowerCase();
                    // seta / play / search icon na sidebar
                    if (meta.includes('pesquis') || meta.includes('search') ||
                        meta.includes('buscar') || meta.includes('glyphicon-search') ||
                        meta.includes('fa-search') || meta.includes('fa-play') ||
                        meta.includes('arrow') || meta.includes('seta') ||
                        meta.includes('circle-arrow') || meta.includes('chevron') ||
                        (el.tagName === 'BUTTON' && r.width < 40 && r.left < 580)) {
                        // evita "ocultar filtros" / auditoria / ajuda
                        if (meta.includes('ocultar') || meta.includes('auditoria')
                            || meta.includes('ajuda') || meta.includes('help')) continue;
                        el.click();
                        return 'seta';
                    }
                }
                // seta logo após o input de token/chip
                const inputs = Array.from(document.querySelectorAll('input')).filter(el => {
                    if (el.offsetParent === null) return false;
                    const r = el.getBoundingClientRect();
                    return r.left < 520 && r.width > 80 && r.y < 700;
                });
                for (const inp of inputs) {
                    let el = inp.nextElementSibling;
                    for (let i = 0; i < 4 && el; i++) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.width < 60 && r.left < 620) {
                            const t = ((el.innerText||'')+(el.className||'')).toLowerCase();
                            // prevent clicking the 'x' close button on chips
                            if (!t.includes('ocultar') && !t.includes('close') && !t.includes('remove') && t !== '×' && t !== 'x') {
                                if (el.tagName === 'BUTTON' || el.tagName === 'A' || t.includes('pesquis') || t.includes('search') || t.includes('buscar') || t.includes('play') || t.includes('arrow') || t.includes('seta')) {
                                    el.click();
                                    return 'next-sibling';
                                }
                            }
                        }
                        el = el.nextElementSibling;
                    }
                    // parent com botão
                    const p = inp.parentElement;
                    if (p) {
                        const btn = p.querySelector('button, a.btn, input[type="button"]');
                        if (btn && btn.offsetParent !== null) {
                            btn.click();
                            return 'parent-btn';
                        }
                    }
                }
                return '';
            }"""
        )
        if ok_seta:
            print(f"[Consulta] [OK] Clicou Pesquisar/seta ({ok_seta})")
            page.wait_for_timeout(300)
            return True
    except Exception as e:
        print(f"[Consulta] seta Pesquisar: {e}")

    # 1) Botão texto Pesquisar / Search / Buscar
    try:
        ok = page.evaluate(
            """() => {
                const cands = Array.from(document.querySelectorAll(
                    'button, input[type="button"], input[type="submit"], a.btn, a.button'
                ));
                for (const el of cands) {
                    if (el.offsetParent === null) continue;
                    const val = ((el.value || '') + ' ' + (el.innerText || '')).trim().toLowerCase();
                    const isSearch = val === 'pesquisar' || val.includes('pesquisar')
                        || val === 'search' || val.includes('search')
                        || val === 'buscar' || val.includes('buscar');
                    if (!isSearch) continue;
                    let p = el;
                    let audit = false;
                    for (let i = 0; i < 10 && p; i++) {
                        const t = (p.innerText || '').substring(0, 180).toLowerCase();
                        if (t.includes('ocultar auditoria') ||
                            (t.includes('auditoria') && (t.includes('até') || t.includes('ate')))) {
                            audit = true; break;
                        }
                        p = p.parentElement;
                    }
                    if (audit) continue;
                    el.click();
                    return true;
                }
                return false;
            }"""
        )
        if ok:
            print("[Consulta] [OK] Clicou Pesquisar (botão)")
            page.wait_for_timeout(300)
            return True
    except Exception as e:
        print(f"[Consulta] JS Pesquisar: {e}")

    from utils.ui_i18n import SELETORES_PESQUISAR

    for sel in SELETORES_PESQUISAR:
        try:
            locs = page.locator(sel)
            for i in range(min(locs.count(), 6)):
                loc = locs.nth(i)
                if not loc.is_visible(timeout=250):
                    continue
                loc.click(timeout=2500)
                print(f"[Consulta] [OK] Clicou Pesquisar ({sel[:40]})")
                page.wait_for_timeout(300)
                return True
        except Exception:
            continue

    # último recurso: Enter duplo no teclado (chip criado + pesquisa)
    try:
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        page.keyboard.press("Enter")
        print("[Consulta] [!] Pesquisar via Enter duplo (fallback final)")
        page.wait_for_timeout(350)
        return True
    except Exception:
        return False


def _pesquisar_cpf_na_aba_filtros(
    page: Page,
    termo: str,
    *,
    so_digitar_se_filtro_ok: bool = False,
) -> bool:
    """
    Fluxo EXATO do usuário (print real):
      1) Filtro = CPF  (NUNCA digitar CPF com filtro em Nome)
      2) Limpa chips antigos (ALEX V, CPFs de outras buscas...)
      3) Digita o CPF
      4) Clica PESQUISAR
      5) Espera a linha com este CPF na grid

    Filtro CPF: no máximo 2 tentativas automáticas aqui.
    Se falhar, retorna False - o caller faz a 3ª (manual + reconhecer).
    """
    dig = "".join(c for c in (termo or "") if c.isdigit()) or (termo or "").strip()

    # 1) Abrir filtros (não Auditoria)
    _fechar_auditoria_abrir_filtros(page)
    page.wait_for_timeout(250)

    # 2) Limpa chips ANTES (Última pesquisa deixa "ALEX V" + CPF antigo)
    _limpar_chips_e_campo_filtro(page)
    page.wait_for_timeout(200)

    # 3) Força Filtro = CPF (máx 2x automáticas)
    ok_sel = False
    if so_digitar_se_filtro_ok and _filtro_atual_eh_cpf(page):
        ok_sel = True
        print("[Consulta] [OK] Filtro já em CPF (você configurou)")
    else:
        for tentativa_filtro in range(1, 3):
            print(f"[Consulta] Filtro -> CPF (auto {tentativa_filtro}/2)")
            ok_sel = _selecionar_filtro_cpf(page)
            page.wait_for_timeout(250)
            if ok_sel or _filtro_atual_eh_cpf(page):
                ok_sel = True
                break
            print(f"[Consulta] Filtro ainda não é CPF (auto {tentativa_filtro}/2)")
            _fechar_auditoria_abrir_filtros(page)
            page.wait_for_timeout(200)

    if not ok_sel and not _filtro_atual_eh_cpf(page):
        print(
            "[Consulta] ✗ Filtro NÃO mudou para CPF em 2 tentativas - "
            "passa para você na 3ª"
        )
        return False

    # 4) Limpa chips de novo (trocar Nome->CPF às vezes mantém chips)
    _limpar_chips_e_campo_filtro(page)
    page.wait_for_timeout(150)

    # reafirma CPF logo antes de digitar
    if not _filtro_atual_eh_cpf(page):
        ok_re = _selecionar_filtro_cpf(page)
        page.wait_for_timeout(200)
        if not ok_re and not _filtro_atual_eh_cpf(page):
            print("[Consulta] ✗ Filtro voltou para Nome - não digita CPF")
            return False

    print(f"[Consulta] [OK] Filtro confirmado em CPF - digitando {dig}")

    # 5) Digitar CPF + Enter (cria chip × 0534...) + pesquisa
    #    Sem Enter o GW zera o campo e a lista fica vazia (print real).
    digitou = _digitar_cpf_com_chip(page, dig)
    if not digitou:
        print("[Consulta] [!] Não digitou CPF")
        return False

    # 6) Enter após o chip - o GW usa Enter para pesquisar (mais confiável que clicar botão)
    page.wait_for_timeout(300)
    try:
        page.keyboard.press("Enter")
        print("[Consulta] [OK] Enter após chip - pesquisando...")
    except Exception:
        pass
    page.wait_for_timeout(400)

    # 7) Esperar a LINHA com este CPF
    for i in range(10):
        page.wait_for_timeout(280)
        if _tem_resultado_cpf(page, dig):
            print(f"[Consulta] [OK] Resultado na lista para CPF {dig}")
            return True
        if i == 2:
            # reforço: chip pode não ter sido criado - redigita + Enter
            print("[Consulta] Sem linha ainda - recria chip + Enter...")
            _digitar_cpf_com_chip(page, dig)
            page.wait_for_timeout(200)
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass
        if i == 5:
            print("[Consulta] Grid ainda sem CPF - Enter de novo...")
            if not _filtro_atual_eh_cpf(page):
                _selecionar_filtro_cpf(page)
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass
    if not _lista_vazia(page) and (_tem_resultado_cpf(page, dig) or _tem_nome_na_lista(page)):
        print("[Consulta] [!] CPF parcial/truncado na lista - tenta Editar mesmo assim")
        return True
    print(f"[Consulta] [!] CPF {dig} não apareceu na lista após Pesquisar")
    if _lista_vazia(page):
        return True
    print("[Consulta] [!] Lista tem linhas mas NÃO do CPF buscado - não abre Editar errado")
    return False


def _tem_chip_cpf(page: Page, dig: str) -> bool:
    """True se existe o chip × 05340307425 na sidebar de filtros."""
    dig = "".join(c for c in (dig or "") if c.isdigit())
    if len(dig) < 8:
        return False
    try:
        return bool(
            page.evaluate(
                """(dig) => {
                    const dig8 = dig.slice(0, 8);
                    const nodes = Array.from(document.querySelectorAll(
                        '.tag, .token, .label, span, div, a, li'
                    ));
                    for (const el of nodes) {
                        if (el.offsetParent === null) continue;
                        const r = el.getBoundingClientRect();
                        if (r.left > 520 || r.width < 20) continue;
                        const t = (el.innerText || el.textContent || '').replace(/\\D/g, '');
                        if (t.includes(dig) || t.includes(dig8)) return true;
                    }
                    return false;
                }""",
                dig,
            )
        )
    except Exception:
        return False


def _digitar_cpf_com_chip(page: Page, dig: str) -> bool:
    """
    Fluxo real do GW (print):
      1) digita os 11 dígitos no campo da sidebar de filtros
      2) ENTER -> vira chip (× 05340307425)
      3) (depois) clicar Pesquisar / seta
    Se só digitar sem Enter, o campo zera e some da pesquisa.

    IMPORTANTE: este método só deve ser chamado quando a página for
    a consulta de motoristas. Verifica isso antes de tocar em qualquer input.
    """
    dig = "".join(c for c in (dig or "") if c.isdigit())
    if len(dig) < 11:
        return False

    # Guarda: só digita se realmente estamos na consulta
    url_agora = (page.url or "").lower()
    if "cadmotorista" in url_agora and "consulta" not in url_agora and "acao=editar" in url_agora:
        print(f"[Consulta] [!] Ainda no form editar - não digita CPF aqui ({url_agora[:60]})")
        return False

    # Já tem chip do CPF? não redigita (evita limpar)
    if _tem_chip_cpf(page, dig):
        print(f"[Consulta] [OK] Chip CPF já existe ({dig})")
        return True

    digitou = False
    try:
        inputs = page.locator(
            'input[type="text"]:visible, input:not([type]):visible, input[type="search"]:visible'
        )
        n_in = min(inputs.count(), 12)
        for i in range(n_in):
            loc = inputs.nth(i)
            try:
                name = (loc.get_attribute("name") or "").lower()
                if "data" in name or "date" in name or "orden" in name:
                    continue
                # Evita campos do formulário principal (cpf, nome, rg, cnh...)
                if any(k in name for k in ("cpf", "nome", "rg", "cnh", "cep", "nasc", "bairro",
                                           "endereco", "cidade", "categoria", "vencimento")):
                    continue
                box = loc.bounding_box()
                if not box or box["width"] < 80:
                    continue
                # Sidebar de filtros: fica no canto esquerdo (x < 480) e no topo (y < 600)
                if box["y"] > 600 or box["x"] > 480:
                    continue
                if not _filtro_atual_eh_cpf(page):
                    _selecionar_filtro_cpf(page)
                    page.wait_for_timeout(100)
                loc.click(timeout=800)
                page.keyboard.press("Control+a")
                page.keyboard.press("Backspace")
                page.wait_for_timeout(40)
                # digita dígito a dígito (tokenfield do GW aceita melhor que fill)
                loc.type(dig, delay=18)
                page.wait_for_timeout(80)
                # 1º ENTER cria o chip - OBRIGATÓRIO
                page.keyboard.press("Enter")
                page.wait_for_timeout(250)
                # 2º ENTER reforça pesquisa caso o chip não tenha sido criado
                if not _tem_chip_cpf(page, dig):
                    try:
                        val = "".join(
                            c for c in (loc.input_value(timeout=300) or "") if c.isdigit()
                        )
                        if len(val) < 11:
                            loc.click(timeout=400)
                            page.keyboard.press("Control+a")
                            loc.type(dig, delay=15)
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(200)
                        # 3º Enter garante chip mesmo em campos lentos
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(150)
                    except Exception:
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(200)
                if _tem_chip_cpf(page, dig):
                    print(f"[Consulta] [OK] CPF digitado + Enter -> chip {dig}")
                else:
                    # ainda sem chip: deixa o valor no campo e Enter de novo
                    print(f"[Consulta] [OK] CPF digitado = {dig} (Enter enviado; chip?)")
                digitou = True
                break
            except Exception:
                continue
    except Exception as e:
        print(f"[Consulta] digitar: {e}")

    if not digitou:
        digitou = page.evaluate(
            """(termo) => {
                const inputs = Array.from(document.querySelectorAll('input'));
                for (const el of inputs) {
                    if (el.offsetParent === null) continue;
                    const t = (el.type||'').toLowerCase();
                    if (t === 'date' || t === 'hidden' || t === 'checkbox' || t === 'radio'
                        || t === 'submit' || t === 'button') continue;
                    const n = (el.name||'').toLowerCase();
                    if (n.includes('data') || n.includes('date') || n.includes('orden')) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width < 80 || r.left > 520) continue;
                    el.focus();
                    el.value = '';
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.value = termo;
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                    if (window.jQuery) {
                        try { window.jQuery(el).val(termo).trigger('input').trigger('change'); }
                        catch(e) {}
                    }
                    // simula Enter para criar token/chip
                    try {
                        el.dispatchEvent(new KeyboardEvent('keydown', {
                            key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                        }));
                        el.dispatchEvent(new KeyboardEvent('keyup', {
                            key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                        }));
                    } catch(e) {}
                    return true;
                }
                return false;
            }""",
            dig,
        )
        if digitou:
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass
            page.wait_for_timeout(200)
            print(f"[Consulta] [OK] CPF (JS) + Enter = {dig}")

    return bool(digitou)


def _limpar_inputs_filtro_nao_data(page: Page) -> None:
    """Compat - não faz nada (limpeza de chips desativada)."""
    return


def _lista_vazia(page: Page) -> bool:
    try:
        body = (page.inner_text("body") or "").lower()
        if "quantidade de resultados: 0" in body:
            return True
        if re_search_pagina_zero(body):
            return True
        if any(
            x in body
            for x in ("nenhum registro", "nenhum resultado", "não há registros")
        ):
            return True
        # só conta linhas com texto (evita tr vazia do template)
        n = page.evaluate(
            """() => {
                const rows = Array.from(document.querySelectorAll('table tbody tr'));
                return rows.filter(tr => {
                    const t = (tr.innerText||'').trim();
                    return t.length > 8 && !t.toLowerCase().includes('nenhum');
                }).length;
            }"""
        )
        return int(n or 0) == 0
    except Exception:
        return False


def re_search_pagina_zero(body: str) -> bool:
    import re
    return bool(re.search(r"p[aá]gina\s*1\s*de\s*0\b", body or "", re.I))


def _tem_resultado_cpf(page: Page, dig: str) -> bool:
    """True se a grid principal mostra o CPF (com ou sem pontuação / truncado)."""
    dig = "".join(c for c in dig if c.isdigit())
    if len(dig) < 5:
        return False
    try:
        return bool(
            page.evaluate(
                """(dig) => {
                    const dig9 = dig.slice(0, 9);
                    const dig8 = dig.slice(0, 8);
                    const dig6 = dig.slice(0, 6);
                    const rows = Array.from(document.querySelectorAll('table tbody tr, table tr'));
                    for (const tr of rows) {
                        const r = tr.getBoundingClientRect();
                        if (r.width < 200 || r.left < 200) continue; // ignora sidebar
                        const tx = (tr.innerText || '').replace(/\\D/g, '');
                        if (!tx) continue;
                        if (tx.includes(dig) || tx.includes(dig9) || tx.includes(dig8)
                            || (dig6.length >= 6 && tx.includes(dig6))) return true;
                    }
                    return false;
                }""",
                dig,
            )
        )
    except Exception:
        return False


def _abrir_editar_motorista(
    page: Page, cpf: str, *, forcar_botao_editar: bool = False
) -> bool:
    """
    Print real: na linha do resultado há ícone lápis (editar) ou nome clicável.
    """
    dig = "".join(c for c in cpf if c.isdigit())
    dig_curto = dig  # usa CPF inteiro (11 dígitos) - evita linha errada
    dig7 = dig[:7] if len(dig) >= 7 else dig

    def _form_aberto() -> bool:
        url = (page.url or "").lower()
        if "cadmotorista" in url or "editar" in url or "acao=editar" in url:
            return True
        try:
            if page.locator('input[name="cpf"], #cpf, input[name="nome"]').count() > 0:
                return True
            # iframe
            for fr in page.frames:
                u = (fr.url or "").lower()
                if "cadmotorista" in u or "editar" in u:
                    return True
        except Exception:
            pass
        return False

    def _apos_click() -> bool:
        page.wait_for_timeout(350)
        try:
            tratar_dialog_motorista_ja_cadastrado(page, timeout_ms=800)
        except Exception:
            pass
        for _ in range(6):
            if _form_aberto():
                return True
            page.wait_for_timeout(250)
        return _form_aberto()

    # 0) JS: linha do CPF na grid - clica o LÁPIS (2º ícone) com prioridade
    try:
        clicou = page.evaluate(
            """(digFull) => {
                const dig9 = digFull.slice(0, 9);
                const dig8 = digFull.slice(0, 8);
                const dig6 = digFull.slice(0, 6);
                const rows = Array.from(document.querySelectorAll('table tbody tr, table tr'))
                    .filter(tr => {
                        const r = tr.getBoundingClientRect();
                        return r.width >= 250 && r.left >= 200;
                    });
                function score(tr) {
                    const tx = (tr.innerText || '').replace(/\\D/g, '');
                    if (tx.includes(digFull)) return 100;
                    if (tx.includes(dig9)) return 90;
                    if (tx.includes(dig8)) return 80;
                    if (tx.includes(dig6)) return 60;
                    return 0;
                }
                // ordena: melhor match de CPF primeiro
                const ranked = rows.map(tr => ({tr, s: score(tr)}))
                    .filter(x => x.s > 0)
                    .sort((a,b) => b.s - a.s);
                // se ninguém bate CPF mas há 1–2 linhas, usa a 1ª com nome
                let alvos = ranked.map(x => x.tr);
                if (!alvos.length && rows.length > 0 && rows.length <= 3) {
                    alvos = rows.filter(tr => {
                        const t = (tr.innerText||'').trim();
                        return t.length > 10 && !/nenhum/i.test(t);
                    });
                }
                for (const tr of alvos) {
                    // 1) Lápis / Editar (title/src/class)
                    const els = Array.from(tr.querySelectorAll('a, button, img, i, span'));
                    for (const el of els) {
                        const meta = (
                            (el.getAttribute('title')||'') + ' ' +
                            (el.getAttribute('href')||'') + ' ' +
                            (el.getAttribute('src')||'') + ' ' +
                            (el.getAttribute('onclick')||'') + ' ' +
                            (el.className||'') + ' ' +
                            (el.getAttribute('data-original-title')||'')
                        ).toLowerCase();
                        if (meta.includes('edit') || meta.includes('editar') ||
                            meta.includes('lapis') || meta.includes('lápis') ||
                            meta.includes('pencil') || meta.includes('alterar') ||
                            meta.includes('glyphicon-pencil') || meta.includes('fa-pencil') ||
                            meta.includes('fa-edit') || meta.includes('cadmotorista') ||
                            meta.includes('acao=editar') || meta.includes('acao=alterar')) {
                            (el.closest('a') || el).click();
                            return 'pencil';
                        }
                    }
                    // 2) 2º ícone pequeno da linha = lápis no GW (print real)
                    const iconLinks = Array.from(tr.querySelectorAll('td a, td img, td button'))
                        .filter(el => {
                            const rr = el.getBoundingClientRect();
                            return rr.width > 0 && rr.height > 0 && rr.width < 48;
                        });
                    if (iconLinks.length >= 2) {
                        (iconLinks[1].closest('a') || iconLinks[1]).click();
                        return '2nd-icon';
                    }
                    if (iconLinks.length === 1) {
                        (iconLinks[0].closest('a') || iconLinks[0]).click();
                        return '1st-icon';
                    }
                    // 3) nome azul
                    const nameLinks = Array.from(tr.querySelectorAll('a')).filter(a => {
                        const n = (a.innerText || '').trim();
                        const rr = a.getBoundingClientRect();
                        return n.length >= 4 && !/^\\d+$/.test(n) &&
                               !n.includes('×') && rr.width > 40;
                    });
                    if (nameLinks.length) {
                        nameLinks[0].click();
                        return 'name';
                    }
                    tr.dispatchEvent(new MouseEvent('dblclick', {bubbles:true}));
                    return 'dblclick';
                }
                return '';
            }""",
            dig,
        )
        if clicou:
            if _apos_click():
                print(f"[Consulta] [OK] Editar via {clicou}")
                return True
            page.wait_for_timeout(350)
            if _apos_click():
                print(f"[Consulta] [OK] Editar via {clicou} (atrasado)")
                return True
            print(f"[Consulta] Clicou ({clicou}) mas form não abriu - tenta seletores")
    except Exception as e:
        print(f"[Consulta] JS editar: {e}")

    # 1) Lápis / Editar (print: title="Editar" no ícone lápis)
    candidatos = []
    for d in (dig, dig7, dig[:9] if len(dig) >= 9 else dig):
        candidatos.extend(
            [
                f'tr:has-text("{d}") [title="Editar"]',
                f'tr:has-text("{d}") [title*="Editar" i]',
                f'tr:has-text("{d}") [data-original-title*="Editar" i]',
                f'tr:has-text("{d}") a[title*="Editar" i]',
                f'tr:has-text("{d}") img[title*="Editar" i]',
                f'tr:has-text("{d}") [title*="Edit" i]',
                f'tr:has-text("{d}") a[href*="editar" i]',
                f'tr:has-text("{d}") a[href*="cadmotorista" i]',
                f'tr:has-text("{d}") img[src*="edit" i]',
                f'tr:has-text("{d}") img[src*="lapis" i]',
                f'tr:has-text("{d}") img[src*="pencil" i]',
                f'tr:has-text("{d}") .fa-pencil',
                f'tr:has-text("{d}") .glyphicon-pencil',
                f'tr:has-text("{d}") td a >> nth=1',
            ]
        )
    if forcar_botao_editar:
        candidatos = ['button:has-text("Editar")', 'a:has-text("Editar")', *candidatos]

    for seletor in candidatos:
        try:
            loc = page.locator(seletor).first
            if loc.count() == 0 or not loc.is_visible(timeout=350):
                continue
            loc.click(timeout=3000)
            if _apos_click():
                print(f"[Consulta] [OK] Editar via seletor")
                return True
        except Exception:
            continue

    # 2) Clique no NOME (link azul na linha do CPF)
    for d in (dig, dig7):
        for seletor in (
            f'table tbody tr:has-text("{d}") a',
            f'tr:has-text("{d}") a',
        ):
            try:
                locs = page.locator(seletor)
                for i in range(min(locs.count(), 8)):
                    loc = locs.nth(i)
                    if not loc.is_visible(timeout=200):
                        continue
                    txt = (loc.inner_text(timeout=300) or "").strip()
                    if not txt or txt.upper() in ("EDITAR", "EXCLUIR") or txt.isdigit():
                        continue
                    if len(txt) < 3 or "×" in txt:
                        continue
                    loc.click(timeout=2500)
                    if _apos_click():
                        print("[Consulta] [OK] Editar via nome")
                        return True
            except Exception:
                continue

    # 3) Duplo clique na linha
    try:
        row = page.locator(f'tr:has-text("{dig}")').first
        if row.count() == 0:
            row = page.locator(f'tr:has-text("{dig7}")').first
        if row.count():
            row.dblclick(timeout=2000)
            if _apos_click():
                print("[Consulta] [OK] Editar via duplo clique")
                return True
    except Exception:
        pass
    return False
