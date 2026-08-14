"""
Padrão universal do GW: botão azul de 3 pontinhos (...) / lupa.

Fluxo real (prints):
  1. Clica nos 3 pontinhos ao lado do campo
  2. Abre popup "Localizar Veículo" / "Localizar proprietário"  (/localiza?...)
  3. Escolhe filtro (Placa / Nome / CPF...), digita termo, clica Pesquisar
  4. Se ACHOU (tem linha na grid) -> clica no resultado -> popup fecha -> volta
  5. Se NÃO ACHOU (Registros: 0 de 0) -> Novo Cadastro
     -> abre NOVA página de cadastro (cadveiculo / cadproprietario)
     -> preenche + Salvar
     -> FECHA a página de cadastro
     -> volta na popup de pesquisa (ou já vincula)
     -> pesquisa de novo e seleciona, ou fecha e retorna à página original
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from playwright.sync_api import Page, BrowserContext, TimeoutError as PlaywrightTimeoutError

from utils.flags import (
    lookup_max_tentativas_pesquisa,
    recriar_se_zero_resultados,
    salvar_detectar_falha,
)
from utils.manual import apos_manual_campo_ok, pausar_para_manual
from utils.ui_i18n import (
    SELETORES_NOVO_CADASTRO,
    SELETORES_OK,
    SELETORES_PESQUISAR,
    SELETORES_SALVAR,
    TEXTOS_FALHA_SALVAR,
    TEXTOS_FORM_ABERTO,
    TEXTOS_SUCESSO,
)


PreencherNovoCadastro = Callable[[Page], None]


def _dry_run() -> bool:
    import os
    v = (os.getenv("DRY_RUN", "1") or "1").strip().lower()
    return v not in ("0", "false", "nao", "não", "no", "off")


def buscar_com_tres_pontinhos(
    page: Page,
    *,
    termo: str = "",
    label_campo: str = "",
    seletor_campo: str = "",
    seletor_botao: str = "",
    filtro: str = "",
    uf_preferida: str = "",
    match_exato: bool = False,
    pegar_primeiro: bool = False,
    preencher_novo: Optional[PreencherNovoCadastro] = None,
) -> bool:
    """
    Abre a pesquisa (3 pontinhos), busca `termo`.

    filtro: valor do combo à esquerda (ex: "Placa", "Nome", "CPF", "CNPJ", "Cidade").
    uf_preferida: para cidade - prefere linha com UF certa (ex: PAULISTA + PE).
    match_exato: nome da cidade deve ser exatamente o termo (não "BRAGANÇA PAULISTA").
    preencher_novo: callback na page do formulário Novo Cadastro.

    Returns True se vinculou (existente ou recém-criado).
    """
    # pegar_primeiro=True: lista aberta e clica no 1º registro (útil no DRY-RUN)
    if not termo and not pegar_primeiro:
        print(f"[Lookup] Sem termo ({label_campo or seletor_campo}).")
        return False

    # Sem acentos - GW não acha "PALMEIRA DOS ÍNDIOS" / "PALMEIRA DOS ?NDIOS"
    from utils.texto import gw_texto

    # Cidade: separa "PAULISTA PE" -> termo=PAULISTA, uf=PE
    termo_busca = gw_texto(termo or "")
    uf = gw_texto(uf_preferida or "")[:2] if uf_preferida else ""
    if not uf and " " in termo_busca:
        partes = termo_busca.split()
        if len(partes[-1]) == 2 and partes[-1].isalpha():
            uf = partes[-1].upper()
            termo_busca = " ".join(partes[:-1]).strip()
    if label_campo and "cidade" in label_campo.lower():
        match_exato = True

    print(
        f"[Lookup] 3 pontinhos - {label_campo or 'campo'}: "
        f"{'PRIMEIRO DA LISTA' if pegar_primeiro and not termo_busca else repr(termo_busca)} "
        f"uf={uf or '-'} (filtro={filtro or 'auto'}) [v2-sem-pausa-filtro]"
    )

    pages_antes = list(page.context.pages)
    try:
        popup = _abrir_lookup(
            page,
            seletor_campo=seletor_campo,
            seletor_botao=seletor_botao,
            label_campo=label_campo,
        )
    except Exception as e:
        print(f"[Lookup] [!] Falha ao abrir lookup: {e}")
        r = pausar_para_manual(
            f"Não abriu a pesquisa (...) de {label_campo or seletor_campo}: {e}",
            dica="Clique nos 3 pontinhos, pesquise e selecione. Quando o item aparecer, ENTER.",
            page=page,
            seletor_campo=seletor_campo,
            tentativa=3,
            total_auto=2,
        )
        if r == "ok" and _reconhecer_lookup_apos_manual(
            page,
            seletor_campo=seletor_campo,
            termo=termo_busca,
            label_campo=label_campo,
            uf=uf,
            match_exato=match_exato,
        ):
            return True
        return False
    if popup is None:
        print("[Lookup] [!] Não abriu a tela Localizar (seguindo sem travar).")
        r = pausar_para_manual(
            f"Não abriu Localizar ({label_campo or seletor_campo}).",
            dica="Clique nos 3 pontinhos, pesquise e selecione. Quando o item aparecer, ENTER.",
            page=page,
            seletor_campo=seletor_campo,
            tentativa=3,
            total_auto=2,
        )
        if r == "ok" and _reconhecer_lookup_apos_manual(
            page,
            seletor_campo=seletor_campo,
            termo=termo_busca,
            label_campo=label_campo,
            uf=uf,
            match_exato=match_exato,
        ):
            return True
        return False

    try:
        # Filtro: tenta 1x e SEMPRE segue (nunca pausa por filtro).
        if filtro and not pegar_primeiro:
            _selecionar_filtro(popup, filtro)

        if pegar_primeiro and not termo_busca:
            # Lista de marca/prop costuma JÁ VIR CARREGADA.
            # NÃO clicar Pesquisar vazio no proprietário (some a grid).
            eh_prop = "propriet" in (label_campo or "").lower()
            popup.wait_for_timeout(200)
            if not eh_prop:
                try:
                    popup.locator(
                        'button:has-text("Pesquisar"), button:has-text("Search"), input[value*="Pesquis"], input[value*="Search"]'
                    ).first.click(timeout=800)
                    popup.wait_for_timeout(250)
                except Exception:
                    pass
            ok_1 = _selecionar_primeiro_da_lista(popup, label_campo=label_campo)
            if not ok_1 and eh_prop:
                try:
                    popup.locator(
                        'button:has-text("Pesquisar"), button:has-text("Search"), input[value*="Pesquis"], input[value*="Search"]'
                    ).first.click(timeout=800)
                    popup.wait_for_timeout(250)
                except Exception:
                    pass
                ok_1 = _selecionar_primeiro_da_lista(
                    popup, label_campo=label_campo, forcar_link_nome=True
                )

            if ok_1:
                print(f"[Lookup] [OK] Selecionou o PRIMEIRO da lista ({label_campo})")
                _aguardar_retorno(page, popup)
                page.wait_for_timeout(200)
                if seletor_campo and not _campo_origem_preenchido(page, seletor_campo):
                    print(
                        f"[Lookup] [!] 1º item clicado mas {seletor_campo} vazio - "
                        f"reabrindo e forçando link do nome"
                    )
                    try:
                        popup2 = _abrir_lookup(
                            page,
                            seletor_campo=seletor_campo,
                            seletor_botao=seletor_botao,
                            label_campo=label_campo,
                        )
                        if popup2:
                            popup2.wait_for_timeout(600)
                            if _selecionar_primeiro_da_lista(
                                popup2, label_campo=label_campo, forcar_link_nome=True
                            ):
                                _aguardar_retorno(page, popup2)
                                page.wait_for_timeout(500)
                    except Exception as e:
                        print(f"[Lookup] retry 1º item: {e}")
                    if seletor_campo and not _campo_origem_preenchido(page, seletor_campo):
                        print(f"[Lookup] [!] Campo {seletor_campo} ainda vazio")
                        r = pausar_para_manual(
                            f"Lista aberta mas {seletor_campo} ficou vazio.",
                            dica="Na popup Localizar, clique no nome/linha certo. Depois ENTER.",
                            page=page,
                            seletor_campo=seletor_campo,
                            tentativa=3,
                            total_auto=2,
                        )
                        if r == "ok" and _reconhecer_lookup_apos_manual(
                            page,
                            popup=popup,
                            seletor_campo=seletor_campo,
                            termo=termo_busca,
                            label_campo=label_campo,
                            uf=uf,
                            match_exato=match_exato,
                        ):
                            return True
                        return False
                return True
            print("[Lookup] [!] Lista vazia - não há primeiro item")
            r = pausar_para_manual(
                f"Lista vazia no lookup de {label_campo or seletor_campo}.",
                dica="Pesquise e selecione. Quando o item aparecer, ENTER.",
                page=popup,
                seletor_campo=seletor_campo,
                tentativa=3,
                total_auto=2,
            )
            if r == "ok" and _reconhecer_lookup_apos_manual(
                page,
                popup=popup,
                seletor_campo=seletor_campo,
                termo=termo_busca,
                label_campo=label_campo,
                uf=uf,
                match_exato=match_exato,
            ):
                return True
            try:
                _fechar(popup)
            except Exception:
                pass
            return False

        if termo_busca:
            _preencher_e_pesquisar(popup, termo_busca)
            popup.wait_for_timeout(250)

        if _tem_resultados(popup):
            if pegar_primeiro:
                if _selecionar_primeiro_da_lista(popup, label_campo=label_campo):
                    print(f"[Lookup] [OK] Primeiro resultado da busca ({label_campo})")
                    _aguardar_retorno(page, popup)
                    return True
            eh_prop = "propriet" in (label_campo or "").lower()
            eh_marca = "marca" in (label_campo or "").lower()
            n_reg = _contar_registros_popup(popup)
            try:
                # Prop/Marca: preferir link do NOME/descrição (1ª coluna), não só o CNPJ
                if eh_prop or eh_marca:
                    achou = _selecionar_resultado(
                        popup, termo_busca, uf_preferida=uf, match_exato=match_exato
                    )
                    # 1 de 1 (ou poucos): SEMPRE clica o existente - NÃO cria novo
                    if not achou and _tem_resultados(popup):
                        print(
                            f"[Lookup] Resultado na lista (reg={n_reg}) - "
                            f"seleciona existente (NÃO Novo Cadastro)"
                        )
                        achou = _selecionar_primeiro_da_lista(
                            popup,
                            label_campo=label_campo,
                            forcar_link_nome=True,
                        )
                    if not achou and _tem_resultados(popup):
                        # último recurso: clica a linha destacada / 1ª data row
                        achou = _clicar_unica_linha_resultado(popup)
                else:
                    achou = _selecionar_resultado(
                        popup, termo_busca, uf_preferida=uf, match_exato=match_exato
                    )
                    if not achou and n_reg == 1 and _tem_resultados(popup):
                        achou = _selecionar_primeiro_da_lista(
                            popup, label_campo=label_campo, forcar_link_nome=True
                        ) or _clicar_unica_linha_resultado(popup)
            except Exception as e:
                # seleção ok mas popup/página mudou
                if "closed" in str(e).lower():
                    print(
                        f"[Lookup] [OK] JÁ CADASTRADO - selecionado (popup fechou): "
                        f"{termo_busca} {uf}".strip()
                        + " (NÃO cria novo)"
                    )
                    try:
                        _aguardar_retorno(page, popup)
                    except Exception:
                        pass
                    page = _garantir_pagina_origem(
                        page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
                    )
                    if seletor_campo and _campo_origem_preenchido(page, seletor_campo):
                        return True
                    # mesmo com popup fechando, reabre se campo vazio
                    return _reabrir_e_selecionar(
                        page,
                        termo=termo_busca,
                        label_campo=label_campo,
                        seletor_campo=seletor_campo,
                        seletor_botao=seletor_botao,
                        filtro=filtro,
                        uf_preferida=uf,
                        match_exato=match_exato,
                    )
                raise
            if achou:
                print(
                    f"[Lookup] [OK] JÁ CADASTRADO - clicou na lista: "
                    f"{termo_busca} {uf}".strip()
                    + " (NÃO cria novo)"
                )
                try:
                    _aguardar_retorno(page, popup)
                except Exception:
                    pass
                page.wait_for_timeout(800)
                # Fica na página de ORIGEM (cadveiculo ou motorista) - NÃO troca de aba
                page = _garantir_pagina_origem(
                    page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
                )
                # CRÍTICO: confirmar que o campo recebeu o valor
                if seletor_campo and not _campo_origem_preenchido(page, seletor_campo):
                    print(
                        f"[Lookup] [!] Clicou na lista mas {seletor_campo} continua vazio - "
                        f"reabrindo e forçando seleção de '{termo_busca}'..."
                    )
                    try:
                        _fechar(popup)
                    except Exception:
                        pass
                    page = _garantir_pagina_origem(
                        page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
                    )
                    page.bring_to_front()
                    page.wait_for_timeout(400)
                    if _reabrir_e_selecionar(
                        page,
                        termo=termo_busca,
                        label_campo=label_campo,
                        seletor_campo=seletor_campo,
                        seletor_botao=seletor_botao,
                        filtro=filtro,
                        uf_preferida=uf,
                        match_exato=match_exato,
                    ):
                        return True
                    print(
                        f"[Lookup] [!] Ainda sem valor em {seletor_campo} "
                        f"após re-selecionar {termo_busca}"
                    )
                    r = pausar_para_manual(
                        f"Clicou na lista mas {seletor_campo} continua vazio ({termo_busca}).",
                        dica="Abra os 3 pontinhos, clique no resultado certo. Quando o campo encher (ou a lista mostrar o nome), ENTER.",
                        page=page,
                        seletor_campo=seletor_campo,
                        tentativa=3,
                        total_auto=2,
                    )
                    if r == "ok" and _reconhecer_lookup_apos_manual(
                        page,
                        seletor_campo=seletor_campo,
                        termo=termo_busca,
                        label_campo=label_campo,
                        uf=uf,
                        match_exato=match_exato,
                    ):
                        return True
                    return False
                if seletor_campo:
                    print(f"[Lookup] [OK] Campo {seletor_campo} preenchido com {termo_busca}")
                return True
            # AINDA tem linhas? Nunca criar novo se a grid não está vazia
            if _tem_resultados(popup):
                print(
                    f"[Lookup] Grid com resultado(s) sem match 'exato' de "
                    f"'{termo_busca}' - clica o existente (NÃO cria novo)"
                )
                if _selecionar_primeiro_da_lista(
                    popup, label_campo=label_campo, forcar_link_nome=True
                ) or _clicar_unica_linha_resultado(popup):
                    try:
                        _aguardar_retorno(page, popup)
                    except Exception:
                        pass
                    page = _garantir_pagina_origem(
                        page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
                    )
                    page.wait_for_timeout(700)
                    if not seletor_campo or _campo_origem_preenchido(page, seletor_campo):
                        print(f"[Lookup] [OK] Selecionou existente na lista: {termo_busca}")
                        return True
                    # clicou mas campo vazio - reabre na mesma página (não cria)
                    if _reabrir_e_selecionar(
                        page,
                        termo=termo_busca,
                        label_campo=label_campo,
                        seletor_campo=seletor_campo,
                        seletor_botao=seletor_botao,
                        filtro=filtro,
                        uf_preferida=uf,
                        match_exato=match_exato,
                    ):
                        return True
                print(
                    f"[Lookup] [!] Tinha resultado na lista mas não vinculou "
                    f"{seletor_campo or label_campo} - NÃO cria duplicado"
                )
                r = pausar_para_manual(
                    f"Havia resultado para '{termo_busca}' mas não vinculou.",
                    dica="Na popup Localizar, clique no item correto. Quando o nome estiver na lista/campo, ENTER.",
                    page=popup if popup and not popup.is_closed() else page,
                    seletor_campo=seletor_campo,
                    tentativa=3,
                    total_auto=2,
                )
                if r == "ok" and _reconhecer_lookup_apos_manual(
                    page,
                    popup=popup,
                    seletor_campo=seletor_campo,
                    termo=termo_busca,
                    label_campo=label_campo,
                    uf=uf,
                    match_exato=match_exato,
                ):
                    return True
                try:
                    _fechar(popup)
                except Exception:
                    pass
                return False
            if preencher_novo is None:
                r = pausar_para_manual(
                    f"Sem cadastro automático para '{termo_busca}' (só pesquisa).",
                    dica="Se achar na lista, selecione. Quando o item aparecer, ENTER.",
                    page=popup if popup and not popup.is_closed() else page,
                    seletor_campo=seletor_campo,
                    tentativa=3,
                    total_auto=2,
                )
                if r == "ok" and _reconhecer_lookup_apos_manual(
                    page,
                    popup=popup,
                    seletor_campo=seletor_campo,
                    termo=termo_busca,
                    label_campo=label_campo,
                    uf=uf,
                    match_exato=match_exato,
                ):
                    return True
                _fechar(popup)
                return False

        # Só chega aqui se a pesquisa devolveu 0 registros de verdade
        if _tem_resultados(popup):
            # cinto de segurança: nunca Novo Cadastro com grid cheia
            print(
                f"[Lookup] [!] Bloqueado Novo Cadastro: ainda há registros na lista "
                f"para '{termo_busca}'"
            )
            if _selecionar_primeiro_da_lista(
                popup, label_campo=label_campo, forcar_link_nome=True
            ) or _clicar_unica_linha_resultado(popup):
                try:
                    _aguardar_retorno(page, popup)
                except Exception:
                    pass
                return True
            try:
                _fechar(popup)
            except Exception:
                pass
            return False

        # 0 de 0 confirmado - SEMPRE tenta Novo Cadastro se tiver callback
        n_zero = _contar_registros_popup(popup)
        print(
            f"[Lookup] Não encontrado (registros={n_zero}) -> "
            f"Novo Cadastro de '{termo_busca}'..."
        )
        if preencher_novo is None:
            print("[Lookup] [!] Sem callback de cadastro - abortando (só pesquisa).")
            _fechar(popup)
            return False

        # Garante que ainda estamos na popup Localizar (0 de 0)
        try:
            if popup.is_closed():
                print("[Lookup] [!] Popup Localizar fechou antes do Novo Cadastro - reabrindo...")
                popup = _abrir_lookup(
                    page,
                    seletor_campo=seletor_campo,
                    seletor_botao=seletor_botao,
                    label_campo=label_campo,
                )
                if popup is None:
                    print("[Lookup] [!] Não reabriu Localizar para Novo Cadastro")
                    return False
                if filtro:
                    _selecionar_filtro(popup, filtro)
                _preencher_e_pesquisar(popup, termo_busca)
                popup.wait_for_timeout(700)
            popup.bring_to_front()
        except Exception as e:
            print(f"[Lookup] bring_to_front popup: {e}")
        popup.wait_for_timeout(400)

        form_page = _abrir_novo_cadastro(page.context, popup, pages_antes)
        if form_page is None:
            print("[Lookup] [!] 1ª tentativa Novo Cadastro falhou - 2ª...")
            popup.wait_for_timeout(600)
            form_page = _abrir_novo_cadastro(page.context, popup, pages_antes)
        if form_page is None:
            print(
                "[Lookup] [!] Não abriu Novo Cadastro - confira se o botão "
                "'Novo Cadastro' está visível na popup Localizar."
            )
            form_page = _abrir_novo_cadastro_js(page.context, popup)
        if form_page is None:
            # 3ª: clica com mouse no centro do botão azul (Playwright get_by_role)
            form_page = _abrir_novo_cadastro_forcado(page.context, popup, pages_antes)
        if form_page is None:
            print(
                "[Lookup] [!] Abortando: não conseguiu clicar 'Novo Cadastro' "
                f"com 0 registros para '{termo_busca}'. Botão deve estar azul "
                "à direita de Pesquisar na popup Localizar."
            )
            # Popup ainda aberta - você clica; o robô NÃO mexe até ENTER
            r = pausar_para_manual(
                f"Não abriu 'Novo Cadastro' para '{termo_busca}'.",
                dica=(
                    "Na popup Localizar: clique no botão azul 'Novo Cadastro', "
                    "preencha, Salvar, depois selecione o item na lista (ou deixe o campo preenchido). "
                    "Quando o nome/item aparecer ou o campo encher, ENTER."
                ),
                page=popup if popup and not popup.is_closed() else page,
                seletor_campo=seletor_campo,
                tentativa=3,
                total_auto=2,
            )
            if r == "ok" and _reconhecer_lookup_apos_manual(
                page,
                popup=popup,
                seletor_campo=seletor_campo,
                termo=termo_busca,
                label_campo=label_campo,
                uf=uf,
                match_exato=match_exato,
            ):
                return True
            # usuário pode ter aberto o form: tenta achar página nova
            try:
                for p in list(page.context.pages):
                    try:
                        u = (p.url or "").lower()
                        if p != page and any(
                            x in u for x in ("cadveiculo", "cadmarca", "cadproprietario")
                        ):
                            form_page = p
                            break
                    except Exception:
                        continue
            except Exception:
                pass
            if form_page is None:
                return False

        try:
            if form_page.is_closed():
                print("[Lookup] Form de Novo Cadastro já fechado (talvez você salvou).")
                if seletor_campo and apos_manual_campo_ok(page, seletor_campo):
                    return True
                # tenta só vincular pelo Localizar
                form_page = None
        except Exception:
            pass

        if form_page is None:
            # usuário pode ter só fechado - tenta reabrir pesquisa e vincular
            if seletor_campo and apos_manual_campo_ok(page, seletor_campo):
                return True
            r2 = pausar_para_manual(
                f"Sem form aberto para '{termo_busca}'.",
                dica="Vincule o valor no campo pelos 3 pontinhos. ENTER ao terminar.",
                page=page,
                seletor_campo=seletor_campo,
            )
            return bool(
                r2 == "ok"
                and seletor_campo
                and apos_manual_campo_ok(page, seletor_campo)
            )

        print(f"[Lookup] [OK] Novo Cadastro aberto: {form_page.url}")
        try:
            form_page.bring_to_front()
        except Exception:
            pass
        form_page.wait_for_timeout(500)
        preencher_novo(form_page)
        if _dry_run():
            print(
                "[Lookup] DRY-RUN - preencheu formulário de Novo Cadastro "
                "mas NÃO salva (vínculo não fica no GW)."
            )
            form_page.wait_for_timeout(500)
            _fechar_e_voltar(form_page, popup, page)
            _fechar(popup)
            print("[Lookup] DRY-RUN - use DRY_RUN=0 para gravar marca/prop/veículo novos.")
            return False

        # Salvar (até 2 tentativas de preencher+salvar se validação falhar)
        salvou = False
        for tent_save in range(1, 3):
            salvou = _salvar_com_confirmacao(form_page)
            if salvou and not _form_cadastro_ainda_aberto(form_page):
                print(f"[Lookup] [OK] Salvar OK (tentativa {tent_save})")
                break
            print(
                f"[Lookup] [!] Salvar NÃO gravou (tentativa {tent_save}/2) - "
                f"repreenche e tenta de novo..."
            )
            try:
                form_page.bring_to_front()
            except Exception:
                pass
            form_page.wait_for_timeout(400)
            try:
                preencher_novo(form_page)
            except Exception as e:
                print(f"[Lookup] repreencher: {e}")
            form_page.wait_for_timeout(500)

        if not salvou or _form_cadastro_ainda_aberto(form_page):
            print(
                "[Lookup] [!] Cadastro NÃO foi salvo (campo obrigatório / validação). "
                "NÃO pesquisa em loop sem ter gravado."
            )
            # Form ainda aberto: PARA e deixa você completar (não fecha em cima de você)
            r = pausar_para_manual(
                f"Formulário de '{termo_busca}' não salvou (campo obrigatório?).",
                dica=(
                    "Complete os campos em vermelho/faltando e clique Salvar no GW. "
                    "Quando gravar e o form fechar (ou o campo de origem encher), ENTER."
                ),
                page=form_page if form_page and not form_page.is_closed() else page,
                seletor_campo=seletor_campo,
            )
            ainda_aberto = True
            try:
                ainda_aberto = (
                    form_page is not None
                    and not form_page.is_closed()
                    and _form_cadastro_ainda_aberto(form_page)
                )
            except Exception:
                ainda_aberto = True
            if r == "ok" and (
                not ainda_aberto
                or (seletor_campo and apos_manual_campo_ok(page, seletor_campo))
            ):
                salvou = True
                print("[Lookup] [OK] Após intervenção manual - segue para vincular.")
            else:
                # fecha form incompleto; recria só se RECRIAR_SE_ZERO_RESULTADOS=1
                try:
                    _fechar_e_voltar(form_page, popup, page)
                except Exception:
                    pass
                try:
                    if form_page and not form_page.is_closed():
                        form_page.close()
                except Exception:
                    pass
                try:
                    _fechar(popup)
                except Exception:
                    pass
                page = _garantir_pagina_origem(
                    page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
                )
                if r == "skip" or not recriar_se_zero_resultados():
                    print(
                        "[Lookup] Não tenta Novo Cadastro de novo. "
                        "Preencha manual se precisar (ou ENTER na próxima pausa)."
                    )
                    return False
                return _criar_e_vincular_novamente(
                    page,
                    termo=termo_busca,
                    label_campo=label_campo,
                    seletor_campo=seletor_campo,
                    seletor_botao=seletor_botao,
                    filtro=filtro,
                    uf_preferida=uf,
                    match_exato=match_exato,
                    preencher_novo=preencher_novo,
                    tentativa=2,
                )

        try:
            if form_page and not form_page.is_closed():
                form_page.wait_for_timeout(1200)
        except Exception:
            pass

        # Fecha cadastro + popup; vínculo = reabrir Localizar e clicar na lista
        try:
            if form_page and not form_page.is_closed():
                _fechar_e_voltar(form_page, popup, page)
        except Exception:
            pass
        try:
            _fechar(popup)
        except Exception:
            pass
        try:
            if form_page and not form_page.is_closed():
                form_page.close()
        except Exception:
            pass

        # Após Novo Cadastro: volta à página de ORIGEM (cadveiculo OU motorista)
        page = _garantir_pagina_origem(
            page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
        )
        page.wait_for_timeout(1000)

        # Sempre reabre Localizar -> pesquisa o que acabou de criar -> SELECIONA
        if seletor_campo and _campo_origem_preenchido(page, seletor_campo):
            print(f"[Lookup] [OK] Campo {seletor_campo} já preenchido após salvar")
            return True

        print(
            f"[Lookup] VINCULANDO '{termo_busca}' em "
            f"({seletor_campo or label_campo}) - pesquisar de novo e selecionar..."
        )
        max_pesq = lookup_max_tentativas_pesquisa()
        for tentativa in range(1, max_pesq + 1):
            print(f"[Lookup] Vínculo tentativa {tentativa}/{max_pesq}...")
            page = _garantir_pagina_origem(
                page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
            )
            page.wait_for_timeout(400)
            ok_v = _reabrir_e_selecionar(
                page,
                termo=termo_busca,
                label_campo=label_campo,
                seletor_campo=seletor_campo,
                seletor_botao=seletor_botao,
                filtro=filtro,
                uf_preferida=uf,
                match_exato=match_exato,
            )
            page.wait_for_timeout(900)
            if seletor_campo and _campo_origem_preenchido(page, seletor_campo):
                print(
                    f"[Lookup] [OK] Criado e VINCULADO: {termo_busca} -> {seletor_campo}"
                )
                return True
            if ok_v and not seletor_campo:
                return True
            page.wait_for_timeout(600 + tentativa * 200)

        # 0 resultados após "salvar" = NÃO gravou -> pausa manual antes de recriar
        r = pausar_para_manual(
            f"Após salvar, não achou '{termo_busca}' na pesquisa para vincular.",
            dica=(
                "Abra os 3 pontinhos, pesquise a placa/nome. "
                "Quando o item aparecer na lista, ENTER - o robô seleciona e preenche."
            ),
            page=page,
            seletor_campo=seletor_campo,
            tentativa=3,
            total_auto=2,
        )
        if r == "ok" and _reconhecer_lookup_apos_manual(
            page,
            seletor_campo=seletor_campo,
            termo=termo_busca,
            label_campo=label_campo,
            uf=uf,
            match_exato=match_exato,
        ):
            return True
        if r == "skip" or not recriar_se_zero_resultados():
            print(
                f"[Lookup] [!] Pesquisa pós-salvar 0 resultados para '{termo_busca}' "
                f"- para aqui (sem loop)."
            )
            return False
        print(
            f"[Lookup] [!] Pesquisa pós-salvar com 0 resultados para '{termo_busca}' - "
            f"o Salvar anterior NÃO gravou. Abrindo Novo Cadastro de novo..."
        )
        return _criar_e_vincular_novamente(
            page,
            termo=termo_busca,
            label_campo=label_campo,
            seletor_campo=seletor_campo,
            seletor_botao=seletor_botao,
            filtro=filtro,
            uf_preferida=uf,
            match_exato=match_exato,
            preencher_novo=preencher_novo,
            tentativa=2,
        )

    except Exception as e:
        print(f"[Lookup] Erro: {e}")
        try:
            _fechar(popup)
        except Exception:
            pass
        return False


def _eh_form_veiculo_marca_prop(page: Page) -> bool:
    """True se a aba atual é cadastro de veículo / marca / proprietário."""
    try:
        u = (page.url or "").lower()
        return any(
            x in u
            for x in ("cadveiculo", "cadmarca", "cadproprietario")
        )
    except Exception:
        return False


def _lookup_eh_placa_operacional(
    seletor_campo: str = "", seletor_botao: str = ""
) -> bool:
    """Lookup de placa no motorista (Veículo/Carreta/Bi-Trem) - aí sim volta pro operacional."""
    s = f"{seletor_campo or ''} {seletor_botao or ''}".lower()
    return any(
        x in s
        for x in (
            "localiza_veiculo",
            "vei_placa",
            "car_placa",
            "bi_placa",
            "tri_placa",
            "#localiza_veiculo",
        )
    )


def _pagina_motorista(page: Page) -> Page:
    """Devolve a aba cadmotorista (editar/iniciar), não a do cadveiculo."""
    try:
        u = page.url or ""
        if "cadmotorista" in u:
            return page
    except Exception:
        pass
    try:
        for p in page.context.pages:
            try:
                u = p.url or ""
                if "cadmotorista" in u:
                    p.bring_to_front()
                    print(f"[Lookup] Foco na aba motorista: {u[:90]}")
                    return p
            except Exception:
                continue
    except Exception:
        pass
    return page


def _pagina_com_campo(page: Page, seletor_campo: str) -> Page:
    """Procura a aba que ainda tem o campo do lookup (cadveiculo com nome_prop/marca)."""
    if not seletor_campo:
        return page
    # página atual primeiro
    try:
        if not page.is_closed():
            loc = page.locator(seletor_campo).first
            if loc.count() and loc.is_visible(timeout=400):
                page.bring_to_front()
                return page
    except Exception:
        pass
    try:
        for p in page.context.pages:
            try:
                if p.is_closed():
                    continue
                loc = p.locator(seletor_campo).first
                if loc.count() and loc.is_visible(timeout=300):
                    p.bring_to_front()
                    u = (p.url or "")[:90]
                    print(f"[Lookup] Foco na aba com {seletor_campo}: {u}")
                    return p
            except Exception:
                continue
    except Exception:
        pass
    return page


def _garantir_pagina_origem(
    page: Page,
    *,
    seletor_campo: str = "",
    seletor_botao: str = "",
) -> Page:
    """
    Página correta após um lookup:

    - Se estamos em cadveiculo / cadmarca / cadproprietario -> FICA (marca/prop/cidade do veículo)
    - Se o lookup é placa operacional do motorista -> volta pro cadmotorista + aba Operacional
    - Senão -> aba que ainda tem o seletor_campo
    """
    # 1) Form de cadastro de veículo/marca/prop: NUNCA pular pro motorista
    if _eh_form_veiculo_marca_prop(page):
        try:
            page.bring_to_front()
        except Exception:
            pass
        return page

    # 2) Placa do motorista (Veículo/Carreta/Bi-Trem)
    if _lookup_eh_placa_operacional(seletor_campo, seletor_botao):
        return _garantir_pagina_motorista_operacional(page)

    # 3) Aba que contém o campo (ex.: cadveiculo ainda aberto em outra tab)
    if seletor_campo:
        p2 = _pagina_com_campo(page, seletor_campo)
        if _eh_form_veiculo_marca_prop(p2) or p2 is not page:
            return p2

    return page


def _garantir_pagina_motorista_operacional(page: Page) -> Page:
    """
    Após cadastro de veículo/prop, a aba ativa pode ser cadveiculo.
    Volta pro cadmotorista e abre Dados Operacionais (#vei_placa/#car_placa).
    Retorna a Page correta do motorista.
    """
    page = _pagina_motorista(page)
    try:
        page.bring_to_front()
    except Exception:
        pass
    try:
        from gw_automation.operacional import abrir_aba_operacional

        abrir_aba_operacional(page)
    except Exception as e:
        print(f"[Lookup] abrir operacional: {e}")
    try:
        page.wait_for_timeout(400)
    except Exception:
        pass
    return page


def _reabrir_e_selecionar(
    page: Page,
    *,
    termo: str,
    label_campo: str = "",
    seletor_campo: str = "",
    seletor_botao: str = "",
    filtro: str = "",
    uf_preferida: str = "",
    match_exato: bool = False,
) -> bool:
    """Abre de novo os 3 pontinhos, pesquisa e seleciona (após Novo Cadastro)."""
    if not termo:
        return False
    # NÃO força motorista se o form de origem é cadveiculo (marca/prop/cidade)
    page = _garantir_pagina_origem(
        page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
    )
    # fecha popups Localizar órfãs
    try:
        for p in list(page.context.pages):
            try:
                u = (p.url or "").lower()
                if p != page and "localiza" in u:
                    p.close()
            except Exception:
                continue
    except Exception:
        pass
    page.bring_to_front()
    page.wait_for_timeout(300)
    try:
        popup = _abrir_lookup(
            page,
            seletor_campo=seletor_campo,
            seletor_botao=seletor_botao,
            label_campo=label_campo,
        )
    except Exception as e:
        print(f"[Lookup] reabrir lookup: {e}")
        return False
    if popup is None:
        return False
    try:
        if filtro:
            _selecionar_filtro(popup, filtro)
        # pesquisa até 3x (só espera extra se 0 resultados)
        for tent in range(1, 4):
            _preencher_e_pesquisar(popup, termo)
            popup.wait_for_timeout(300 if tent == 1 else 500)
            if _tem_resultados(popup):
                print(f"[Lookup] reabrir: achou '{termo}' na lista (tentativa {tent})")
                break
            print(f"[Lookup] reabrir: ainda 0 resultados p/ '{termo}' (tentativa {tent}/3)")
            popup.wait_for_timeout(350)

        # Prop: clica no NOME (link), não só no CNPJ - senão nome_prop fica vazio
        eh_prop = "propriet" in (label_campo or "").lower()
        ok_sel = False
        if eh_prop:
            ok_sel = _selecionar_primeiro_da_lista(
                popup, label_campo=label_campo, forcar_link_nome=True
            ) or _selecionar_resultado(
                popup, termo, uf_preferida=uf_preferida, match_exato=match_exato
            )
        else:
            ok_sel = _selecionar_resultado(
                popup, termo, uf_preferida=uf_preferida, match_exato=match_exato
            )
        if ok_sel:
            _aguardar_retorno(page, popup)
            page = _garantir_pagina_origem(
                page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
            )
            page.bring_to_front()
            page.wait_for_timeout(900)
            if seletor_campo:
                ok = _campo_origem_preenchido(page, seletor_campo)
                if not ok:
                    print(
                        f"[Lookup] reabrir: clicou mas {seletor_campo} vazio "
                        f"(termo={termo}) url={(page.url or '')[:70]}"
                    )
                return ok
            return True
        # fallback: 1º da lista se a busca retornou linhas
        if _tem_resultados(popup) and _selecionar_primeiro_da_lista(
            popup, label_campo=label_campo, forcar_link_nome=eh_prop
        ):
            _aguardar_retorno(page, popup)
            page = _garantir_pagina_origem(
                page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
            )
            page.bring_to_front()
            page.wait_for_timeout(900)
            if seletor_campo:
                return _campo_origem_preenchido(page, seletor_campo)
            return True
        # 0 de 0: esta função SÓ seleciona - não cria. Quem cria é
        # buscar_com_tres_pontinhos(..., preencher_novo=...).
        n_reg = _contar_registros_popup(popup)
        print(
            f"[Lookup] reabrir: 0 resultados p/ '{termo}' (reg={n_reg}) - "
            f"não cria aqui; o caller deve chamar lookup com preencher_novo."
        )
        _fechar(popup)
        return False
    except Exception as e:
        print(f"[Lookup] reabrir/selecionar: {e}")
        try:
            _fechar(popup)
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Abrir popup Localizar
# ---------------------------------------------------------------------------

def _abrir_lookup(
    page: Page,
    *,
    seletor_campo: str = "",
    seletor_botao: str = "",
    label_campo: str = "",
) -> Optional[Page]:
    context = page.context
    pages_antes = set(context.pages)

    botao = _localizar_botao_tres_pontinhos(
        page,
        seletor_campo=seletor_campo,
        seletor_botao=seletor_botao,
        label_campo=label_campo,
    )
    if botao is None:
        return None

    try:
        with context.expect_page(timeout=4000) as nova:
            botao.click(timeout=3000)
        popup = nova.value
        popup.wait_for_load_state("domcontentloaded", timeout=10000)
        print(f"[Lookup] Popup: {popup.url}")
        return popup
    except PlaywrightTimeoutError:
        page.wait_for_timeout(500)
        novas = set(context.pages) - pages_antes
        if novas:
            popup = list(novas)[0]
            try:
                popup.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            return popup
        # modal na mesma page?
        try:
            if page.locator("text=Localizar").count() > 0:
                return page
        except Exception:
            pass
        # não travar: botão clicou mas não abriu popup reconhecível
        return None
    except Exception as e:
        print(f"[Lookup] click botão: {e}")
        return None


def _localizar_botao_tres_pontinhos(
    page: Page,
    *,
    seletor_campo: str = "",
    seletor_botao: str = "",
    label_campo: str = "",
):
    if seletor_botao:
        try:
            loc = page.locator(seletor_botao).first
            if loc.count() and loc.is_visible():
                print(f"[Lookup] Botão via seletor: {seletor_botao}")
                return loc
        except Exception:
            pass
        # input type=button value="..."
        try:
            loc = page.locator(f'{seletor_botao}[value="..."]').first
            if loc.count():
                return loc
        except Exception:
            pass

    if seletor_campo:
        try:
            campo = page.locator(seletor_campo).first
            if campo.count():
                for rel in (
                    'xpath=following-sibling::*[1]',
                    'xpath=following-sibling::button[1]',
                    'xpath=following-sibling::a[1]',
                    'xpath=following-sibling::img[1]',
                    'xpath=../button[1]',
                    'xpath=../a[1]',
                    'xpath=../img[1]',
                    'xpath=..//*[contains(@title,"Pesquis") or contains(@title,"Consult") or contains(@title,"Localiz")]',
                    'xpath=..//img[contains(@src,"lupa") or contains(@src,"search") or contains(@src,"find") or contains(@src,"lookup")]',
                    'xpath=..//a[contains(.,"...")]',
                    'xpath=..//button[contains(.,"...")]',
                ):
                    try:
                        loc = campo.locator(rel).first
                        if loc.count():
                            return loc
                    except Exception:
                        continue
        except Exception:
            pass

    if label_campo:
        # Preferência: botão/ícone na MESMA linha do rótulo (Veículo, Carreta, Cidade...)
        # No cadproprietario a Cidade usa input[type=button][value="..."] (print real)
        xpaths = [
            f"//*[contains(normalize-space(.),'{label_campo}')]/ancestor::tr[1]//input[@type='button' and @value='...']",
            f"//*[contains(normalize-space(.),'{label_campo}')]/ancestor::tr[1]//input[@value='...']",
            f"//td[contains(normalize-space(.),'{label_campo}')]/following::input[@type='button' and @value='...'][1]",
            f"//td[contains(normalize-space(.),'{label_campo}')]/following::img[1]",
            f"//td[contains(normalize-space(.),'{label_campo}')]/following::a[1]",
            f"//td[contains(normalize-space(.),'{label_campo}')]/following::button[1]",
            f"//*[contains(normalize-space(.),'{label_campo}')]/ancestor::tr[1]//img[contains(@src,'lupa') or contains(@src,'search') or contains(@src,'find') or contains(@onclick,'localiza') or contains(@onclick,'Localiza')]",
            f"//*[contains(normalize-space(.),'{label_campo}')]/ancestor::tr[1]//a[contains(@onclick,'localiza') or contains(@href,'localiza') or contains(.,'...')]",
            f"//*[contains(normalize-space(.),'{label_campo}')]/ancestor::tr[1]//img",
            f"//*[contains(normalize-space(.),'{label_campo}')]/ancestor::tr[1]//a[contains(@class,'bot') or contains(@class,'btn')]",
        ]
        for xp in xpaths:
            try:
                loc = page.locator(f"xpath={xp}").first
                if loc.count() and loc.is_visible():
                    print(f"[Lookup] Botão via label '{label_campo}' (xpath)")
                    return loc
            except Exception:
                continue
        for seletor in (
            f'tr:has-text("{label_campo}") input[type="button"][value="..."]',
            f'tr:has-text("{label_campo}") input[value="..."]',
            f'tr:has-text("{label_campo}") input[type="button"]',
            f'tr:has-text("{label_campo}") img',
            f'tr:has-text("{label_campo}") a',
            f'tr:has-text("{label_campo}") button',
            f'td:has-text("{label_campo}") ~ td input[type="button"][value="..."]',
            f'td:has-text("{label_campo}") ~ td img',
            f'td:has-text("{label_campo}") ~ td a',
            f'td:has-text("{label_campo}") ~ td button',
        ):
            try:
                loc = page.locator(seletor).first
                if loc.count() and loc.is_visible():
                    print(f"[Lookup] Botão via {seletor}")
                    return loc
            except Exception:
                continue

    for seletor in (
        'input[type="button"][value="..."]',
        'button:has-text("...")',
        'a:has-text("...")',
        'img[src*="lupa"]',
        'img[title*="Pesquisar"]',
        'img[alt*="Pesquisar"]',
        '[title*="Pesquisar"]',
        '[title*="Localizar"]',
        '[title*="Consultar"]',
    ):
        try:
            loc = page.locator(seletor).first
            if loc.count():
                return loc
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Dentro da popup Localizar
# ---------------------------------------------------------------------------

def _aliases_filtro(alvo: str) -> list[str]:
    aliases = {
        "CNPJ": ["CNPJ", "Cnpj", "cnpj", "CPF/CNPJ", "CPF / CNPJ", "Documento"],
        "CPF": ["CPF", "Cpf", "cpf", "CPF/CNPJ", "CPF / CNPJ", "Documento"],
        "Nome": ["Nome", "NOME", "Razão Social", "Razao Social", "Descrição", "Descricao"],
        "Placa": ["Placa", "PLACA"],
        "Cidade": ["Cidade", "CIDADE"],
        "Descrição": ["Descrição", "Descricao", "DESCRICAO", "Nome"],
    }
    tentativas = list(aliases.get(alvo, [alvo]))
    if alvo not in tentativas:
        tentativas = [alvo, *tentativas]
    return tentativas


def _filtro_popup_atual(popup: Page) -> str:
    """Texto da opção selecionada no combo de filtro da popup Localizar."""
    try:
        return (
            popup.evaluate(
                """() => {
                    for (const s of document.querySelectorAll('select')) {
                        if (!s.options || s.options.length < 2) continue;
                        const opts = Array.from(s.options).map(
                            o => (o.textContent||'').trim().toUpperCase()
                        );
                        // Placa/Nome/CPF OU Cidade/UF (localiza cidade)
                        const hit = opts.some(t =>
                            t === 'CPF' || t.startsWith('CPF') ||
                            t === 'PLACA' || t === 'NOME' || t === 'CNPJ' ||
                            t === 'CIDADE' || t.startsWith('CIDADE') ||
                            t.includes('DESCRI')
                        );
                        if (!hit) continue;
                        const o = s.options[s.selectedIndex];
                        return ((o && o.textContent) || '').trim();
                    }
                    return '';
                }"""
            )
            or ""
        )
    except Exception:
        return ""


def _filtro_visivel_texto(popup: Page) -> str:
    """
    Lê o texto do combo à esquerda (select nativo OU UI custom).
    No GW marca: já vem 'Descrição' - select pode estar display:none.
    """
    try:
        return (
            popup.evaluate(
                """() => {
                    // 1) select nativo
                    for (const s of document.querySelectorAll('select')) {
                        if (!s.options || s.options.length < 2) continue;
                        const opts = Array.from(s.options).map(
                            o => (o.textContent||'').trim().toUpperCase()
                        );
                        const hit = opts.some(t =>
                            t.includes('DESCRI') || t === 'PLACA' || t === 'NOME' ||
                            t.startsWith('CPF') || t === 'CNPJ' || t.startsWith('CIDADE')
                        );
                        if (!hit) continue;
                        const o = s.options[s.selectedIndex];
                        if (o) return (o.textContent||'').trim();
                    }
                    // 2) UI custom: texto perto do input de pesquisa (chosen/select2)
                    const inputs = Array.from(document.querySelectorAll(
                        'input[type="text"], input:not([type])'
                    )).filter(el => el.offsetParent !== null);
                    for (const inp of inputs) {
                        let el = inp.previousElementSibling;
                        for (let i = 0; i < 4 && el; i++) {
                            const t = (el.innerText||el.textContent||'').replace(/\\s+/g,' ').trim();
                            if (t.length >= 3 && t.length <= 24) return t;
                            el = el.previousElementSibling;
                        }
                        const parent = inp.parentElement;
                        if (parent) {
                            const fake = parent.querySelector(
                                '.chosen-single span, .select2-selection__rendered, select'
                            );
                            if (fake) {
                                const t = (fake.innerText||fake.textContent||'').replace(/\\s+/g,' ').trim();
                                if (t) return t;
                            }
                        }
                    }
                    // 3) fallback: 1º select da página
                    const s0 = document.querySelector('select');
                    if (s0 && s0.options && s0.selectedIndex >= 0) {
                        return (s0.options[s0.selectedIndex].textContent||'').trim();
                    }
                    return '';
                }"""
            )
            or ""
        )
    except Exception:
        return ""


def _filtro_popup_ok(popup: Page, filtro: str) -> bool:
    alvo = (filtro or "").strip().upper()
    if not alvo:
        return True
    cur = (_filtro_popup_atual(popup) or _filtro_visivel_texto(popup) or "").upper()
    cur = cur.replace("  ", " ").strip()
    if not cur:
        return False
    # Descrição ≈ DESCRICAO (sem acento)
    def _norm(s: str) -> str:
        return (
            s.replace("Ç", "C")
            .replace("Ã", "A")
            .replace("Á", "A")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ú", "U")
            .replace("Â", "A")
            .replace("Ê", "E")
            .replace("Ô", "O")
        )

    cn, an = _norm(cur), _norm(alvo)
    if an in cn or cn.startswith(an) or an[:5] in cn:
        return True
    for a in _aliases_filtro(filtro):
        au = _norm(a.upper())
        if au in cn or cn.startswith(au.split("/")[0]) or au[:5] in cn:
            return True
    return False


def _selecionar_filtro(popup: Page, filtro: str) -> bool:
    """
    Combo à esquerda: Placa | Nome | CPF | CNPJ | Descrição | Cidade...
    NUNCA bloqueia o fluxo: se o combo já está certo (ex. Descrição na marca)
    ou se não conseguir ler, retorna True e deixa a pesquisa seguir.
    """
    alvo = (filtro or "").strip()
    if not alvo:
        return True

    # Já está no valor certo? (print real: marca já vem em Descrição)
    if _filtro_popup_ok(popup, alvo):
        print(f"[Lookup] [OK] Filtro já em {_filtro_visivel_texto(popup) or _filtro_popup_atual(popup)!r}")
        return True

    tentativas = _aliases_filtro(alvo)

    # 1) JS force em TODOS os selects (não filtra por tipo - marca/cidade/etc.)
    try:
        ok_js = popup.evaluate(
            """(cands) => {
                const up = cands.map(c => (c||'').toUpperCase()
                    .normalize('NFD').replace(/[\\u0300-\\u036f]/g,''));
                for (const s of document.querySelectorAll('select')) {
                    if (!s.options || s.options.length < 2) continue;
                    const opts = Array.from(s.options);
                    const texts = opts.map(o => (o.textContent||'').trim());
                    const ups = texts.map(t => t.toUpperCase()
                        .normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').replace(/\\s+/g,' '));
                    let hit = null;
                    for (const cand of up) {
                        hit = opts.find((o,i) => {
                            const t = ups[i];
                            return t === cand || t.startsWith(cand) || t.includes(cand)
                                || cand.startsWith(t) || (cand.length>=4 && t.includes(cand.slice(0,5)));
                        });
                        if (hit) break;
                    }
                    if (!hit) continue;
                    for (const o of opts) o.selected = false;
                    hit.selected = true;
                    s.selectedIndex = hit.index;
                    s.value = hit.value;
                    for (const type of ['input','change','blur']) {
                        try { s.dispatchEvent(new Event(type, {bubbles:true})); } catch(e) {}
                    }
                    if (window.jQuery) {
                        try {
                            window.jQuery(s).val(hit.value).trigger('change')
                                .trigger('chosen:updated').trigger('select2:select');
                        } catch(e) {}
                    }
                    return (hit.textContent||'').trim();
                }
                return '';
            }""",
            tentativas,
        )
        if ok_js:
            popup.wait_for_timeout(150)
            print(f"[Lookup] Filtro: {ok_js!r} (JS, pedido={alvo})")
            return True
    except Exception as e:
        print(f"[Lookup] filtro JS: {e}")

    # 2) Playwright select_option em qualquer select
    for seletor in (
        'select:visible',
        "select",
        'select[name*="tipo"]',
        'select[name*="filtro"]',
        'select[name*="campo"]',
        'select[name*="opcao"]',
    ):
        try:
            n = popup.locator(seletor).count()
            for i in range(min(n, 12)):
                loc = popup.locator(seletor).nth(i)
                try:
                    if not loc.count():
                        continue
                except Exception:
                    continue
                opcoes = []
                try:
                    opcoes = loc.evaluate(
                        """el => Array.from(el.options).map(o => ({
                            text: (o.textContent||'').trim(),
                            value: o.value
                        }))"""
                    ) or []
                except Exception:
                    opcoes = []
                if len(opcoes) < 2:
                    continue

                for cand in tentativas:
                    try:
                        loc.select_option(label=cand, timeout=800, force=True)
                        print(f"[Lookup] Filtro: {cand} (pedido={alvo})")
                        return True
                    except Exception:
                        pass
                    try:
                        loc.select_option(value=cand, timeout=500, force=True)
                        print(f"[Lookup] Filtro value={cand}")
                        return True
                    except Exception:
                        pass
                    for op in opcoes:
                        txt = (op.get("text") or "")
                        val = (op.get("value") or "")
                        tl, cl = txt.lower(), cand.lower()
                        if cl in tl or tl in cl or cl[:5] in tl:
                            try:
                                loc.select_option(label=txt, timeout=800, force=True)
                                print(f"[Lookup] Filtro: {txt!r} (parcial {cand})")
                                return True
                            except Exception:
                                try:
                                    loc.select_option(value=val, timeout=500, force=True)
                                    print(f"[Lookup] Filtro value={val!r}")
                                    return True
                                except Exception:
                                    continue
        except Exception:
            continue

    # 3) NÃO trava: se a lista já tem linhas, o filtro default do GW já serve
    #    (marca = Descrição; lista 15 de 212 já aberta)
    try:
        if _tem_resultados(popup):
            print(
                f"[Lookup] [!] Filtro {alvo!r} não confirmado, "
                "mas a lista já tem registros - segue pesquisa/seleção"
            )
            return True
    except Exception:
        pass

    # 4) Último recurso: assume ok e pesquisa (comportamento antigo que funcionava)
    print(
        f"[Lookup] [!] Filtro {alvo!r} não lido - segue sem parar "
        f"(visível={_filtro_visivel_texto(popup)!r})"
    )
    return True


def _achar_popup_localiza(page: Page, popup: Page | None = None) -> Page | None:
    try:
        if popup is not None and not popup.is_closed():
            u = (popup.url or "").lower()
            if "localiza" in u or "localizar" in u:
                return popup
    except Exception:
        pass
    try:
        for p in list(page.context.pages):
            try:
                if p == page:
                    continue
                u = (p.url or "").lower()
                if "localiza" in u or "localizar" in u:
                    return p
            except Exception:
                continue
    except Exception:
        pass
    return None


def _campo_preenchido_em_qualquer_pagina(page: Page, seletor_campo: str) -> bool:
    """Checa o seletor na página de origem e em outras abas do contexto."""
    if not seletor_campo:
        return False
    if _campo_origem_preenchido(page, seletor_campo):
        return True
    try:
        for p in list(page.context.pages):
            try:
                if p.is_closed():
                    continue
                u = (p.url or "").lower()
                if "localiza" in u:
                    continue
                if _campo_origem_preenchido(p, seletor_campo):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _reconhecer_lookup_apos_manual(
    page: Page,
    *,
    popup: Page | None = None,
    seletor_campo: str = "",
    termo: str = "",
    label_campo: str = "",
    uf: str = "",
    match_exato: bool = False,
) -> bool:
    """
    Após a 3ª tentativa (você pesquisou/selecionou):
    reconhece campo preenchido OU nome na lista da popup e conclui o vínculo.
    """
    print("[Lookup] Reconhecendo o que já está na tela...")

    # 1) Campo já preenchido (ex.: Cidade=RECIFE) - NÃO reabre grid
    if seletor_campo and _campo_preenchido_em_qualquer_pagina(page, seletor_campo):
        print(f"[Lookup] [OK] Campo {seletor_campo} já preenchido (você fez) - segue")
        try:
            pop0 = _achar_popup_localiza(page, popup)
            if pop0:
                _fechar(pop0)
        except Exception:
            pass
        return True

    pop = _achar_popup_localiza(page, popup)
    if pop is None:
        page.wait_for_timeout(400)
        if seletor_campo and _campo_preenchido_em_qualquer_pagina(page, seletor_campo):
            print(f"[Lookup] [OK] Campo {seletor_campo} preenchido após fechar popup")
            return True
        print("[Lookup] [!] Sem popup Localizar aberta e campo ainda vazio")
        return False

    if _tem_resultados(pop):
        print("[Lookup] [OK] Lista com resultado(s) - selecionando o item (rápido)")
        eh_prop = "propriet" in (label_campo or "").lower()
        eh_cidade = "cidade" in (label_campo or "").lower() or "cidade" in (
            seletor_campo or ""
        ).lower()
        ok_sel = False
        # Cidade / 1 resultado: clica logo sem varrer todas as páginas
        n_reg = _contar_registros_popup(pop)
        if n_reg == 1 or (eh_cidade and n_reg > 0 and n_reg <= 5):
            ok_sel = _clicar_unica_linha_resultado(pop) or _selecionar_primeiro_da_lista(
                pop, label_campo=label_campo, forcar_link_nome=True
            )
        if not ok_sel and termo:
            ok_sel = _selecionar_resultado(
                pop, termo, uf_preferida=uf, match_exato=match_exato
            )
        if not ok_sel:
            ok_sel = _selecionar_primeiro_da_lista(
                pop, label_campo=label_campo, forcar_link_nome=eh_prop
            ) or _clicar_unica_linha_resultado(pop)
        if ok_sel:
            try:
                _aguardar_retorno(page, pop)
            except Exception:
                pass
            page.wait_for_timeout(500)
            if not seletor_campo or _campo_preenchido_em_qualquer_pagina(page, seletor_campo):
                print("[Lookup] [OK] Vinculado após sua pesquisa")
                return True
            print("[Lookup] Clicou no resultado mas campo ainda vazio")
        else:
            print("[Lookup] [!] Tinha lista mas não conseguiu clicar no item")
    else:
        print("[Lookup] Lista ainda sem registros (0 de 0?)")

    if seletor_campo and _campo_preenchido_em_qualquer_pagina(page, seletor_campo):
        return True
    return False


def _preencher_e_pesquisar(popup: Page, termo: str) -> None:
    """
    Digita o termo e clica Pesquisar NA HORA.
    Antes: cada seletor falhava com timeout 2,5s -> 5–15s parado após digitar.
    """
    termo = (termo or "").strip()
    preenchido = False
    for seletor in (
        'input[type="text"]:visible',
        'input[name*="valor"]',
        'input[name*="filtro"]',
        'input[name*="pesquisa"]',
        'input[name*="busca"]',
        'input[name*="placa"]',
        'input[name*="nome"]',
    ):
        try:
            loc = popup.locator(seletor).first
            if loc.count() and loc.is_visible(timeout=300):
                loc.fill(termo, timeout=1000)
                preenchido = True
                break
        except Exception:
            continue

    if not preenchido:
        print("[Lookup] [!] Campo de busca não encontrado na popup.")

    # Pesquisar imediato (JS - sem timeout 2,5s por seletor)
    try:
        ok = popup.evaluate(
            """() => {
                const cands = Array.from(document.querySelectorAll(
                    'button, input[type="button"], input[type="submit"], a.btn'
                ));
                for (const el of cands) {
                    if (el.offsetParent === null) continue;
                    const v = ((el.value||'') + ' ' + (el.innerText||'')).trim().toLowerCase();
                    if (v === 'pesquisar' || v === 'search' || v === 'buscar'
                        || v.includes('pesquisar') || v.includes('search')) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }"""
        )
        if ok:
            print(f"[Lookup] [OK] Pesquisar clicado na hora ({termo!r})")
            popup.wait_for_timeout(280)
            return
    except Exception:
        pass

    # Playwright rápido (timeout curto)
    for seletor in (
        'button:has-text("Pesquisar")',
        'input[type="button"][value="Pesquisar"]',
        'input[value*="Pesquis"]',
        'button:has-text("Search")',
    ):
        try:
            loc = popup.locator(seletor).first
            if loc.count() and loc.is_visible(timeout=200):
                loc.click(timeout=800)
                print(f"[Lookup] [OK] Pesquisar ({seletor[:30]})")
                popup.wait_for_timeout(280)
                return
        except Exception:
            continue

    try:
        popup.keyboard.press("Enter")
        print("[Lookup] [!] Pesquisar via Enter")
        popup.wait_for_timeout(280)
    except Exception:
        pass


def _contar_registros_popup(popup: Page) -> int:
    """Lê 'Registros: 1 de 1' / conta linhas úteis. -1 se desconhecido."""
    try:
        body = popup.inner_text("body") or ""
        m = re.search(r"registros?\s*:\s*(\d+)\s*de\s*(\d+)", body, re.I)
        if m:
            # "1 de 1" -> 1; "0 de 0" -> 0
            return int(m.group(1))
    except Exception:
        pass
    try:
        n = popup.evaluate(
            """() => {
                const rows = Array.from(document.querySelectorAll('table tr'));
                return rows.filter(tr => {
                    const tds = tr.querySelectorAll('td');
                    if (!tds.length) return false;
                    const t = (tr.innerText || '').trim();
                    if (t.length < 5) return false;
                    const u = t.toUpperCase();
                    if (u.startsWith('NOME') && u.includes('CIDADE')) return false;
                    if (u.startsWith('PLACA')) return false;
                    if (u.startsWith('DESCRI')) return false;
                    return true;
                }).length;
            }"""
        )
        return int(n or 0)
    except Exception:
        return -1


def _tem_resultados(popup: Page) -> bool:
    """Detecta 'Registros: 0 de 0' vs linhas na grid com placa/dados."""
    n = _contar_registros_popup(popup)
    if n == 0:
        return False
    if n > 0:
        return True
    try:
        body = popup.inner_text("body")
        low = body.lower()
        # print real: "Registros: 0 de 0" / "Páginas: 1 / 0"
        if re.search(r"registros?\s*:\s*0\b", low):
            return False
        if "0 de 0" in low or "registros: 0 de 0" in low:
            return False
        if re.search(r"p[aá]ginas?\s*:\s*1\s*/\s*0\b", low):
            return False
        if any(
            x in low
            for x in (
                "nenhum registro",
                "não encontrado",
                "nao encontrado",
                "sem resultados",
            )
        ):
            return False
    except Exception:
        pass

    # há linhas de dados na tabela? (não header vazio)
    try:
        n = popup.evaluate(
            """() => {
                const rows = Array.from(document.querySelectorAll('table tbody tr'));
                return rows.filter(tr => {
                    const t = (tr.innerText || '').trim();
                    // linha útil tem placa ou vários campos
                    return t.length > 5 && !/^placa/i.test(t);
                }).length;
            }"""
        )
        return int(n or 0) >= 1
    except Exception:
        pass
    return False


def _clicar_unica_linha_resultado(popup: Page) -> bool:
    """
    Clica a única (ou 1ª) linha de dados da grid - caso 'Registros: 1 de 1'.
    Preferência: link com nome (letras), não só dígitos do CNPJ.
    """
    try:
        # link azul com nome da empresa
        n = popup.locator("table a, table tr td a").count()
        for i in range(min(n, 20)):
            a = popup.locator("table a, table tr td a").nth(i)
            try:
                txt = (a.inner_text(timeout=300) or "").strip()
            except Exception:
                continue
            if len(txt) < 3:
                continue
            up = txt.upper()
            if any(x in up for x in ("PESQUISAR", "NOVO", "FECHAR", "ANTERIOR", "PRÓXIMA", "PROXIMA")):
                continue
            if re.search(r"[A-Za-zÁ-ú]{3,}", txt):
                try:
                    a.click(timeout=2500, force=True)
                    print(f"[Lookup] [OK] Clicou linha única (nome): {txt[:60]}")
                    return True
                except Exception:
                    continue
        # qualquer linha de dados
        rows = popup.locator("table tr")
        rn = rows.count()
        for i in range(min(rn, 15)):
            row = rows.nth(i)
            try:
                txt = (row.inner_text(timeout=300) or "").strip()
            except Exception:
                continue
            if len(txt) < 8:
                continue
            up = txt.upper()
            if up.startswith("NOME") and "CIDADE" in up:
                continue
            if "REGISTROS" in up or "PÁGINA" in up or "PAGINA" in up:
                continue
            try:
                link = row.locator("a").first
                if link.count():
                    link.click(timeout=2500, force=True)
                else:
                    row.click(timeout=2500, force=True)
                print(f"[Lookup] [OK] Clicou linha única (tr): {txt[:60].replace(chr(10), ' ')}")
                return True
            except Exception:
                continue
    except Exception as e:
        print(f"[Lookup] clicar_unica_linha: {e}")
    return False


def _selecionar_resultado(
    popup: Page,
    termo: str,
    *,
    uf_preferida: str = "",
    match_exato: bool = False,
    max_paginas: int = 5,
) -> bool:
    """
    Escolhe a linha correta na grid.

    Para cidade (match_exato=True + uf):
      - NÃO pega "BRAGANÇA PAULISTA" quando o termo é "PAULISTA"
      - Prefere linha com 1ª coluna == PAULISTA e UF == PE
      - Se não achar na página 1, clica Próxima (página 2, 3...)

    Para placa: casa ONB7E61 / ONB-7E61 na linha e clica o link azul.
    """
    trecho = termo.strip()
    uf = (uf_preferida or "").strip().upper()
    if not trecho:
        return False

    eh_placa = _parece_placa_termo(trecho)

    for pagina in range(1, max_paginas + 1):
        print(f"[Lookup] Analisando página {pagina} da grid...")

        # Placa: tenta clicar no texto/link da placa diretamente (mais confiável no GW)
        if eh_placa and _clicar_placa_na_grid(popup, trecho):
            print(f"[Lookup] [OK] Clicou placa na grid (pág {pagina}): {trecho}")
            try:
                if not popup.is_closed():
                    popup.wait_for_timeout(500)
            except Exception:
                pass
            return True

        escolhida = _melhor_linha(popup, trecho, uf=uf, match_exato=match_exato)
        if escolhida is not None:
            try:
                if not _clicar_linha_resultado(escolhida, trecho):
                    raise RuntimeError("clique linha falhou")
                print(f"[Lookup] [OK] Clicou na linha (pág {pagina}): {trecho} {uf}".strip())
                try:
                    if not popup.is_closed():
                        popup.wait_for_timeout(500)
                except Exception:
                    pass
                return True
            except Exception as e:
                msg = str(e).lower()
                if "closed" in msg or "target page" in msg:
                    print(f"[Lookup] [OK] Clicou (janela fechou) pág {pagina}: {trecho} {uf}".strip())
                    return True
                print(f"[Lookup] clique linha: {e}")

        # próxima página
        if not _ir_proxima_pagina(popup):
            break
        popup.wait_for_timeout(700)

    # Última chance: 1 linha de resultado após pesquisa de placa
    if eh_placa:
        try:
            if _selecionar_primeiro_da_lista(popup, label_campo="Veículo", forcar_link_nome=True):
                print(f"[Lookup] [OK] 1º da lista (fallback placa {trecho})")
                return True
        except Exception:
            pass

    print(f"[Lookup] [!] Nenhuma linha exata para '{trecho}' UF={uf or '-'}")
    return False


def _parece_placa_termo(termo: str) -> bool:
    t = re.sub(r"[^A-Za-z0-9]", "", (termo or "")).upper()
    if len(t) == 7 and t[:3].isalpha() and any(c.isdigit() for c in t[3:]):
        return True
    return False


def _clicar_placa_na_grid(popup: Page, placa: str) -> bool:
    """Clica no link/texto da placa na grid Localizar Veículo."""
    import re as _re

    limpa = _re.sub(r"[^A-Za-z0-9]", "", (placa or "")).upper()
    if len(limpa) < 7:
        return False
    # variantes de exibição
    variantes = [
        limpa,
        f"{limpa[:3]}-{limpa[3:]}",
        f"{limpa[:3]}{limpa[3:]}",
        placa.strip().upper(),
    ]
    for v in variantes:
        try:
            loc = popup.get_by_text(v, exact=False).first
            if loc.count() and loc.is_visible(timeout=400):
                # prefere o <a> pai
                try:
                    a = loc.locator("xpath=ancestor-or-self::a[1]")
                    if a.count():
                        a.first.click(timeout=2500, force=True)
                    else:
                        loc.click(timeout=2500, force=True)
                except Exception:
                    loc.click(timeout=2500, force=True)
                return True
        except Exception:
            continue
    # varre links da tabela
    try:
        n = popup.locator("table a, a").count()
        for i in range(min(n, 40)):
            el = popup.locator("table a, a").nth(i)
            try:
                txt = _re.sub(
                    r"[^A-Za-z0-9]",
                    "",
                    (el.inner_text(timeout=200) or ""),
                ).upper()
            except Exception:
                continue
            if limpa in txt or txt == limpa:
                try:
                    el.click(timeout=2500, force=True)
                    return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


def _clicar_linha_resultado(escolhida, trecho: str) -> bool:
    """
    Clica link azul da linha; se não houver, td/onclick.

    Proprietário: preferir o 1º <a> com NOME (texto sem ser só dígitos),
    não o CNPJ - no GW clicar só no CNPJ às vezes não preenche nome_prop.

    Importante: no GW o vínculo costuma ser via href/onclick do <a>.
    force=True às vezes NÃO dispara o handler -> popup fecha sem gravar.
    Preferir click normal; JS click no <a> como fallback.
    """
    trecho_u = (trecho or "").upper().replace("-", "").replace(".", "").replace("/", "")
    so_digitos_termo = trecho_u.isdigit() and len(trecho_u) >= 11

    def _click_el(el) -> bool:
        """Click real (sem force) -> JS click se falhar."""
        try:
            el.scroll_into_view_if_needed(timeout=800)
        except Exception:
            pass
        try:
            el.click(timeout=2500)
            return True
        except Exception:
            pass
        try:
            el.click(timeout=2000, force=True)
            return True
        except Exception:
            pass
        try:
            el.evaluate(
                """el => {
                    el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, view:window}));
                    el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, view:window}));
                    el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                    if (typeof el.click === 'function') el.click();
                }"""
            )
            return True
        except Exception:
            return False

    # 1) Links da linha: se buscou CNPJ, clica no link com letras (nome)
    try:
        links = escolhida.locator("a")
        n_a = links.count()
        if n_a:
            melhor = None
            for i in range(min(n_a, 6)):
                a = links.nth(i)
                try:
                    txt = (a.inner_text(timeout=200) or "").strip()
                except Exception:
                    continue
                if not txt or len(txt) < 2:
                    continue
                # ignora botões de paginação/ações
                up = txt.upper()
                if any(x in up for x in ("PESQUISAR", "NOVO", "FECHAR", "ANTERIOR", "PRÓXIMA", "PROXIMA")):
                    continue
                # nome (tem letras) tem prioridade quando o termo é CNPJ
                if so_digitos_termo and re.search(r"[A-Za-zÁ-ú]{3,}", txt):
                    melhor = a
                    break
                if trecho_u and trecho_u in re.sub(r"[^A-Z0-9]", "", txt.upper()):
                    melhor = a
                    break
                if melhor is None:
                    melhor = a
            if melhor is not None:
                if _click_el(melhor):
                    return True
    except Exception:
        pass

    try:
        # td com o termo
        tds = escolhida.locator("td")
        n = tds.count()
        for i in range(min(n, 8)):
            td = tds.nth(i)
            try:
                txt = (td.inner_text(timeout=200) or "").upper()
                if trecho.upper().replace("-", "") in txt.replace("-", ""):
                    if td.locator("a").count():
                        if _click_el(td.locator("a").first):
                            return True
                    else:
                        if _click_el(td):
                            return True
            except Exception:
                continue
        # se termo é CNPJ e não achou td: clica 1ª td com nome
        if so_digitos_termo:
            for i in range(min(n, 4)):
                td = tds.nth(i)
                try:
                    txt = (td.inner_text(timeout=200) or "").strip()
                    if re.search(r"[A-Za-zÁ-ú]{3,}", txt):
                        if td.locator("a").count():
                            if _click_el(td.locator("a").first):
                                return True
                        else:
                            if _click_el(td):
                                return True
                except Exception:
                    continue
    except Exception:
        pass
    try:
        if _click_el(escolhida):
            return True
    except Exception:
        pass
    try:
        escolhida.evaluate(
            """el => {
                const links = el.querySelectorAll('a');
                for (const a of links) {
                    const t = (a.innerText || '').trim();
                    if (/[A-Za-zÁ-ú]{3,}/.test(t) && t.length > 2) {
                        a.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                        if (typeof a.click === 'function') a.click();
                        return;
                    }
                }
                if (el.onclick) { el.onclick(); return; }
                if (links[0]) { links[0].click(); return; }
                const td = el.querySelector('td');
                if (td) td.click();
                else el.click();
            }"""
        )
        return True
    except Exception:
        return False


def _campo_origem_preenchido(page: Page, seletor: str) -> bool:
    """Verifica se o campo na página principal recebeu valor (nome_prop, marca...)."""
    try:
        if page.is_closed():
            return False
        for _ in range(8):
            try:
                loc = page.locator(seletor).first
                if loc.count():
                    val = (loc.input_value(timeout=600) or "").strip()
                    if len(val) > 1:
                        return True
            except Exception:
                pass
            try:
                page.wait_for_timeout(250)
            except Exception:
                break
        return False
    except Exception:
        return False


def _selecionar_primeiro_da_lista(
    popup: Page,
    *,
    label_campo: str = "",
    forcar_link_nome: bool = False,
) -> bool:
    """
    Clica no primeiro registro da grid.
    Marca: 24.280 CRM 6X2 | Prop: 2G AUTO HOLDING LTDA (1ª linha azul).
    """
    proibidos = {
        "LOCALIZAR", "DESCRIÇÃO", "DESCRICAO", "NOME", "CIDADE", "PESQUISAR",
        "NOVO CADASTRO", "FECHAR", "PLACA", "CPF", "CNPJ", "UF", "TELEFONE",
        "CPF/CNPJ", "ANTERIOR", "PRÓXIMA", "PROXIMA", "REGISTROS",
    }
    eh_prop = "propriet" in (label_campo or "").lower()

    # Espera a grid (ex.: "Registros: 15 de 560")
    try:
        popup.wait_for_selector("text=Registros", timeout=4000)
    except Exception:
        try:
            popup.wait_for_selector("table a, table tr", timeout=3000)
        except Exception:
            pass
    try:
        popup.wait_for_timeout(400)
    except Exception:
        pass

    def _eh_util(txt: str) -> bool:
        if not txt or len(txt.strip()) < 2:
            return False
        up = " ".join(txt.upper().split())
        if up in proibidos:
            return False
        if up.startswith("LOCALIZAR"):
            return False
        if "NOME" in up and "CIDADE" in up:
            return False
        if up.startswith("REGISTROS") or up.startswith("PÁGINA") or up.startswith("PAGINA"):
            return False
        if eh_prop and len([c for c in txt if c.isalpha()]) < 3:
            return False
        return True

    def _click_sem_forcar(el) -> bool:
        """Click real primeiro - force=True no GW às vezes não dispara o vínculo."""
        try:
            el.scroll_into_view_if_needed(timeout=600)
        except Exception:
            pass
        try:
            el.click(timeout=2500)
            return True
        except Exception:
            pass
        try:
            el.click(timeout=2000, force=True)
            return True
        except Exception:
            pass
        try:
            el.evaluate(
                """el => {
                    el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                    if (typeof el.click === 'function') el.click();
                }"""
            )
            return True
        except Exception:
            return False

    # Estratégia A: todos os <a> da página (mais confiável no GW)
    try:
        n = popup.locator("a").count()
        print(f"[Lookup] links na popup: {n}")
        for i in range(min(n, 50)):
            el = popup.locator("a").nth(i)
            try:
                txt = (el.inner_text(timeout=300) or "").strip()
            except Exception:
                continue
            if not _eh_util(txt):
                continue
            try:
                if not _click_sem_forcar(el):
                    continue
                print(f"[Lookup] 1º item clicado (a): {txt[:80].replace(chr(10), ' ')}")
                try:
                    if not popup.is_closed():
                        popup.wait_for_timeout(900)
                except Exception:
                    pass
                return True
            except Exception as e:
                print(f"[Lookup] falha click a[{i}]: {e}")
                continue
    except Exception as e:
        print(f"[Lookup] varredura <a>: {e}")

    # Estratégia B: linhas da tabela (muitos GW não usam <a>, só tr/td + onclick)
    try:
        rows = popup.locator("table tr")
        rn = rows.count()
        print(f"[Lookup] tr na popup: {rn}")
        for i in range(min(rn, 30)):
            row = rows.nth(i)
            try:
                txt = (row.inner_text(timeout=300) or "").strip()
            except Exception:
                continue
            if not _eh_util(txt):
                continue
            # 1ª célula (nome do prop / descrição da marca)
            try:
                td0 = row.locator("td").first
                ok_click = False
                if td0.count():
                    if td0.locator("a").count():
                        ok_click = _click_sem_forcar(td0.locator("a").first)
                    if not ok_click:
                        ok_click = _click_sem_forcar(td0)
                    if not ok_click:
                        row.evaluate(
                            """el => {
                                const a = el.querySelector('a');
                                if (a) {
                                    a.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                                    a.click();
                                    return;
                                }
                                if (el.onclick) { el.onclick(); return; }
                                const td = el.querySelector('td');
                                if (td) td.click();
                                else el.click();
                            }"""
                        )
                        ok_click = True
                else:
                    ok_click = _click_sem_forcar(row)
                if not ok_click:
                    continue
                print(f"[Lookup] 1º item clicado (tr/td): {txt[:80].replace(chr(10), ' ')}")
                try:
                    if not popup.is_closed():
                        popup.wait_for_timeout(900)
                except Exception:
                    pass
                return True
            except Exception as e:
                print(f"[Lookup] falha tr[{i}]: {e}")
                continue
    except Exception as e:
        print(f"[Lookup] varredura tr: {e}")

    # Estratégia C: texto azul típico do 1º prop da lista (fallback)
    if eh_prop:
        for nome in ("2G AUTO HOLDING", "AUTO HOLDING"):
            try:
                loc = popup.get_by_text(nome, exact=False).first
                if loc.count() and _click_sem_forcar(loc):
                    print(f"[Lookup] 1º item clicado (texto): {nome}")
                    try:
                        popup.wait_for_timeout(800)
                    except Exception:
                        pass
                    return True
            except Exception:
                continue

    return False


def _melhor_linha(popup: Page, termo: str, *, uf: str = "", match_exato: bool = False):
    """Retorna o locator da melhor TR ou None."""
    termo_u = termo.strip().upper()
    # CNPJ/CPF: grid mostra 28.731.462/0001-06 - compara só dígitos
    termo_dig = re.sub(r"\D", "", termo_u)
    eh_doc = len(termo_dig) in (11, 14) and termo_dig.isdigit()

    def _linha_tem_doc(linha: str) -> bool:
        if not eh_doc or not termo_dig:
            return False
        ld = re.sub(r"\D", "", linha or "")
        if not ld:
            return False
        if termo_dig == ld or termo_dig in ld or ld in termo_dig:
            return True
        # últimos 8–12 dígitos batem (mascara/pontuação estranha)
        if len(termo_dig) >= 11 and len(ld) >= 11:
            if termo_dig[-12:] == ld[-12:] or termo_dig[:8] == ld[:8]:
                return True
        return False

    try:
        rows = popup.locator("table tbody tr")
        n = rows.count()
    except Exception:
        n = 0

    if n == 0:
        # algumas grids não usam tbody
        try:
            rows = popup.locator("table tr")
            n = rows.count()
        except Exception:
            return None

    candidatas_exatas = []
    candidatas_uf = []
    candidatas_parcial = []

    for i in range(n):
        try:
            row = rows.nth(i)
            txt = (row.inner_text(timeout=800) or "").strip()
            if not txt or len(txt) < 2:
                continue
            # pula cabeçalho
            up_txt = txt.upper()
            if up_txt.startswith("CIDADE") and "UF" in up_txt and i == 0:
                continue
            if up_txt.startswith("NOME") and "CIDADE" in up_txt:
                continue

            cells = row.locator("td")
            c0 = ""
            c_uf = ""
            try:
                if cells.count() >= 1:
                    c0 = (cells.nth(0).inner_text(timeout=500) or "").strip().upper()
                if cells.count() >= 2:
                    c_uf = (cells.nth(1).inner_text(timeout=500) or "").strip().upper()
            except Exception:
                c0 = txt.split()[0].upper() if txt else ""

            linha_u = txt.upper()

            # match exato na 1ª coluna (cidade)
            nome_ok = c0 == termo_u or c0.strip() == termo_u
            # evita "BRAGANÇA PAULISTA" quando termo é "PAULISTA"
            if match_exato:
                if not nome_ok:
                    # também aceita link com texto exato
                    try:
                        a_txt = (row.locator("a").first.inner_text(timeout=300) or "").strip().upper()
                        nome_ok = a_txt == termo_u
                    except Exception:
                        pass
                if not nome_ok:
                    continue
            else:
                # texto OU CPF/CNPJ (dígitos; grid com pontuação)
                bate = (
                    termo_u in linha_u
                    or termo_u in c0
                    or _linha_tem_doc(linha_u)
                )
                if not bate:
                    continue

            if uf and c_uf == uf:
                candidatas_exatas.append(row)
            elif uf and uf in linha_u:
                candidatas_uf.append(row)
            elif not match_exato or nome_ok:
                candidatas_parcial.append(row)
        except Exception:
            continue

    if candidatas_exatas:
        return candidatas_exatas[0]
    if candidatas_uf:
        return candidatas_uf[0]
    # match_exato sem UF: ainda ok se nome exato
    if match_exato and candidatas_parcial:
        return candidatas_parcial[0]
    if not match_exato and candidatas_parcial:
        return candidatas_parcial[0]
    return None


def _ir_proxima_pagina(popup: Page) -> bool:
    """Clica em Próxima / > na paginação da popup Localizar."""
    for seletor in (
        'a:has-text("Próxima")',
        'button:has-text("Próxima")',
        'input[value*="Próxima"]',
        'a:has-text("Proxima")',
        'a:has-text(">")',
        'img[alt*="Próxima"]',
        'img[title*="Próxima"]',
        'a[title*="Próxima"]',
        # setas comuns
        'a:has-text("»")',
        'a:has-text("›")',
    ):
        try:
            loc = popup.locator(seletor).first
            if loc.count() and loc.is_visible():
                # evita clicar se desabilitado
                cls = (loc.get_attribute("class") or "").lower()
                if "disabled" in cls or "inativ" in cls:
                    continue
                loc.click(timeout=2000)
                print("[Lookup] -> Próxima página")
                return True
        except Exception:
            continue
    return False


def _pagina_form_apos_novo(
    context: BrowserContext,
    popup: Page,
    pages_antes: set,
) -> Optional[Page]:
    """Detecta form de cadastro após clicar Novo Cadastro (nova aba OU mesma janela)."""
    popup.wait_for_timeout(800)
    # 1) nova aba
    novas = [
        p for p in context.pages if p not in pages_antes and not p.is_closed()
    ]
    if novas:
        form = novas[-1]
        try:
            form.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        print(f"[Lookup] [OK] Cadastro em nova aba: {form.url}")
        return form
    # 2) popup navegou para cadastro
    try:
        url = (popup.url or "").lower()
    except Exception:
        url = ""
    if any(
        x in url
        for x in (
            "cadveiculo",
            "cadproprietario",
            "cadmarca",
            "acao=iniciar",
            "acao=novo",
            "acao=incluir",
        )
    ):
        print(f"[Lookup] [OK] Cadastro na mesma janela: {popup.url}")
        return popup
    # 3) form de veículo/prop apareceu no DOM da popup (sem mudar URL logo)
    try:
        if popup.locator(
            '#pl, input[name="pl"], #nome, input[name="nome"], '
            'input[name="cpf"], #cpf, text=Salvar'
        ).count():
            # ainda em localiza mas com form? raro
            if "localiza" not in (popup.url or "").lower():
                return popup
    except Exception:
        pass
    return None


def _abrir_novo_cadastro(
    context: BrowserContext,
    popup: Page,
    pages_antes: list,
) -> Optional[Page]:
    """
    Clica 'Novo Cadastro' na popup Localizar (print: botão azul à direita)
    e devolve a página do formulário (cadveiculo / cadproprietario).
    """
    pages_set = set(context.pages)
    try:
        for p in pages_antes or []:
            pages_set.add(p)
    except Exception:
        pass

    # dump: quantos botões "Novo" existem
    try:
        n_novo = popup.evaluate(
            """() => {
                const els = Array.from(document.querySelectorAll(
                    'button, a, input[type="button"], input[type="submit"]'
                ));
                return els.filter(el => {
                    if (el.offsetParent === null) return false;
                    const t = ((el.value||'') + ' ' + (el.innerText||'')).toLowerCase();
                    return t.includes('novo') || t.includes('new');
                }).map(el => ((el.value||'') + '|' + (el.innerText||'')).trim().slice(0,40));
            }"""
        )
        print(f"[Lookup] botões Novo* na popup: {n_novo}")
    except Exception:
        pass

    seletores = list(SELETORES_NOVO_CADASTRO) + [
        'input[value="Novo Cadastro"]',
        'input[type="button"][value*="Novo"]',
        'button:has-text("Novo")',
        'a:has-text("Novo")',
        '[value="Novo Cadastro"]',
        'text=/Novo\\s*Cadastro/i',
    ]

    for seletor in seletores:
        try:
            loc = popup.locator(seletor).first
            if not loc.count() or not loc.is_visible(timeout=400):
                continue
            print(f"[Lookup] Clicando Novo Cadastro ({seletor[:55]})...")
            try:
                loc.scroll_into_view_if_needed(timeout=1500)
            except Exception:
                pass
            try:
                with context.expect_page(timeout=12000) as nova:
                    loc.click(timeout=5000, force=True)
                form = nova.value
                form.wait_for_load_state("domcontentloaded", timeout=20000)
                print(f"[Lookup] [OK] Nova aba de cadastro: {form.url}")
                return form
            except PlaywrightTimeoutError:
                form = _pagina_form_apos_novo(context, popup, pages_set)
                if form:
                    return form
                print("[Lookup] Click Novo Cadastro sem nova página - tenta próximo seletor")
                continue
            except Exception as e:
                # click pode abrir sem expect_page
                print(f"[Lookup] click: {e}")
                form = _pagina_form_apos_novo(context, popup, pages_set)
                if form:
                    return form
                continue
        except Exception as e:
            print(f"[Lookup] seletor Novo Cadastro falhou: {e}")
            continue
    return None


def _abrir_novo_cadastro_forcado(
    context: BrowserContext,
    popup: Page,
    pages_antes: list,
) -> Optional[Page]:
    """
    Clique forçado no botão azul Novo Cadastro (0 de 0).
    Usa get_by_role / bounding box / JS nativo.
    """
    pages_set = set(context.pages)
    try:
        for p in pages_antes or []:
            pages_set.add(p)
    except Exception:
        pass

    # 1) get_by_role
    for name in ("Novo Cadastro", "Novo", "New Registration", "New Record"):
        try:
            btn = popup.get_by_role("button", name=re.compile(name, re.I))
            if btn.count() and btn.first.is_visible(timeout=300):
                print(f"[Lookup] Novo Cadastro get_by_role({name!r})...")
                try:
                    with context.expect_page(timeout=10000) as nova:
                        btn.first.click(timeout=4000, force=True)
                    form = nova.value
                    form.wait_for_load_state("domcontentloaded", timeout=15000)
                    return form
                except Exception:
                    form = _pagina_form_apos_novo(context, popup, pages_set)
                    if form:
                        return form
        except Exception:
            continue

    # 2) clique por coordenadas (botão à direita de Pesquisar)
    try:
        box = popup.evaluate(
            """() => {
                const els = Array.from(document.querySelectorAll(
                    'button, a, input[type="button"], input[type="submit"]'
                ));
                for (const el of els) {
                    if (el.offsetParent === null) continue;
                    const t = ((el.value||'') + ' ' + (el.innerText||'')).trim().toLowerCase();
                    if (!t.includes('novo cadastro') && t !== 'novo' && !t.includes('new regist'))
                        continue;
                    const r = el.getBoundingClientRect();
                    if (r.width < 20 || r.height < 10) continue;
                    return {x: r.left + r.width/2, y: r.top + r.height/2, t};
                }
                return null;
            }"""
        )
        if box:
            print(f"[Lookup] Novo Cadastro click coords {box}...")
            try:
                with context.expect_page(timeout=10000) as nova:
                    popup.mouse.click(box["x"], box["y"])
                form = nova.value
                form.wait_for_load_state("domcontentloaded", timeout=15000)
                return form
            except Exception:
                form = _pagina_form_apos_novo(context, popup, pages_set)
                if form:
                    return form
    except Exception as e:
        print(f"[Lookup] coords Novo Cadastro: {e}")

    return _abrir_novo_cadastro_js(context, popup)


def _abrir_novo_cadastro_js(
    context: BrowserContext,
    popup: Page,
) -> Optional[Page]:
    """Último recurso: clica Novo Cadastro via JS no DOM da popup."""
    pages_antes = set(context.pages)
    try:
        clicou = popup.evaluate(
            """() => {
                const els = Array.from(document.querySelectorAll(
                    'button, a, input[type="button"], input[type="submit"]'
                ));
                for (const el of els) {
                    if (el.offsetParent === null) continue;
                    const t = ((el.value || '') + ' ' + (el.innerText || '')).toLowerCase();
                    if (
                        t.includes('novo cadastro') || t.trim() === 'novo'
                        || t.includes('new registration') || t.includes('new record')
                        || (t.includes('new') && t.includes('regist'))
                    ) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }"""
        )
        if not clicou:
            return None
        print("[Lookup] Novo Cadastro via JS...")
        popup.wait_for_timeout(1500)
        for _ in range(15):
            novas = [p for p in context.pages if p not in pages_antes and not p.is_closed()]
            if novas:
                form = novas[-1]
                try:
                    form.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                return form
            url = (popup.url or "").lower()
            if "cadveiculo" in url or "cadproprietario" in url:
                return popup
            popup.wait_for_timeout(400)
    except Exception as e:
        print(f"[Lookup] JS Novo Cadastro: {e}")
    return None


def _salvar(page: Page) -> None:
    _salvar_com_confirmacao(page)


def _form_cadastro_ainda_aberto(page: Page) -> bool:
    """
    True se ainda estamos no form de Novo Cadastro (não salvou de verdade).
    Ex.: cadproprietario?acao=iniciar com Salvar ainda na tela.
    """
    try:
        if page.is_closed():
            return False
    except Exception:
        return False
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    # ainda em tela de inclusão
    if any(
        x in url
        for x in (
            "acao=iniciar",
            "acao=incluir",
            "acao=novo",
        )
    ):
        return True
    # Salvar ainda visível + título de cadastro (PT ou EN)
    try:
        body = (page.inner_text("body") or "").lower()
        tem_salvar = False
        for seletor in SELETORES_SALVAR:
            try:
                loc = page.locator(seletor).first
                if loc.count() and loc.is_visible(timeout=300):
                    tem_salvar = True
                    break
            except Exception:
                continue
        if tem_salvar and any(x in body for x in TEXTOS_FORM_ABERTO):
            return True
    except Exception:
        pass
    return False


def _texto_indica_falha_salvar(body: str) -> bool:
    low = (body or "").lower()
    if any(x in low for x in TEXTOS_SUCESSO):
        return False
    return any(x in low for x in TEXTOS_FALHA_SALVAR)


def _salvar_com_confirmacao(page: Page) -> bool:
    """
    Clica Salvar e verifica se GRAVOU de verdade.
    Retorna False se validação falhou / form ainda aberto / mensagem de erro.

    SALVAR_DETECTAR_FALHA=0 -> modo antigo: clica Salvar e assume OK (para reverter).
    """
    clicou = False
    for seletor in SELETORES_SALVAR:
        try:
            loc = page.locator(seletor).first
            if not loc.count() or not loc.is_visible(timeout=500):
                continue
            loc.click(timeout=4000)
            clicou = True
            print("[Lookup] Salvar clicado.")
            break
        except Exception:
            continue
    if not clicou:
        print("[Lookup] [!] Botão Salvar/Save não encontrado.")
        return False

    # dialogs OK / alerta (PT/EN)
    try:
        page.wait_for_timeout(700)
        for sel in SELETORES_OK:
            try:
                b = page.locator(sel).first
                if b.count() and b.is_visible(timeout=400):
                    b.click(timeout=1500)
                    print("[Lookup] OK no diálogo pós-Salvar")
                    page.wait_for_timeout(400)
            except Exception:
                continue
    except Exception:
        pass

    try:
        page.wait_for_load_state("domcontentloaded", timeout=2000)
        page.wait_for_timeout(500)
    except Exception:
        page.wait_for_timeout(1500)

    # Reverter: só clica e assume sucesso (comportamento antigo)
    if not salvar_detectar_falha():
        print("[Lookup] SALVAR_DETECTAR_FALHA=0 - assume salvou (sem checar form/erro)")
        return True

    # 2º clique Salvar se ainda visível (GW às vezes exige)
    try:
        if _form_cadastro_ainda_aberto(page):
            for seletor in SELETORES_SALVAR:
                loc = page.locator(seletor).first
                if loc.count() and loc.is_visible(timeout=400):
                    loc.click(timeout=2000)
                    print("[Lookup] 2º clique Salvar")
                    page.wait_for_timeout(1000)
                    break
    except Exception:
        pass

    try:
        body = page.inner_text("body") or ""
    except Exception:
        body = ""
    low = body.lower()

    if _texto_indica_falha_salvar(body):
        print("[Lookup] [!] Mensagem de validação/erro após Salvar - NÃO gravou")
        return False

    if any(x in low for x in TEXTOS_SUCESSO):
        print("[Lookup] [OK] Mensagem de sucesso após Salvar")
        return True

    # form de inclusão ainda aberto = NÃO salvou
    if _form_cadastro_ainda_aberto(page):
        print(
            "[Lookup] [!] Form de cadastro ainda aberto após Salvar "
            "(falta campo obrigatório?) - NÃO gravou"
        )
        return False

    # saiu do form (URL mudou / fechou) -> sucesso fraco
    try:
        if page.is_closed():
            return True
        url = (page.url or "").lower()
        if "acao=editar" in url or "acao=consultar" in url or "localiza" in url:
            print("[Lookup] [OK] Saiu do form de inclusão após Salvar")
            return True
    except Exception:
        pass

    # sem indício claro: se não está mais no form, ok; senão falha
    if not _form_cadastro_ainda_aberto(page):
        return True
    print("[Lookup] [!] Sem confirmação de gravação")
    return False


def _criar_e_vincular_novamente(
    page: Page,
    *,
    termo: str,
    label_campo: str = "",
    seletor_campo: str = "",
    seletor_botao: str = "",
    filtro: str = "",
    uf_preferida: str = "",
    match_exato: bool = False,
    preencher_novo: Optional[PreencherNovoCadastro] = None,
    tentativa: int = 2,
) -> bool:
    """
    Após Salvar falhar (0 resultados na pesquisa), abre Localizar -> Novo Cadastro
    de novo, preenche, salva e vincula. Só 1 re-tentativa (tentativa>=3 aborta).
    Desliga com RECRIAR_SE_ZERO_RESULTADOS=0.
    """
    if not recriar_se_zero_resultados():
        print(
            f"[Lookup] RECRIAR_SE_ZERO_RESULTADOS=0 - não recria '{termo}'."
        )
        return False
    if tentativa > 2 or not preencher_novo or not termo:
        print(
            f"[Lookup] [!] Desistindo de recriar '{termo}' - "
            f"preencha/salve manualmente se precisar."
        )
        return False

    print(f"[Lookup] Recriando cadastro de '{termo}' (tentativa {tentativa})...")
    page = _garantir_pagina_origem(
        page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
    )
    pages_antes = list(page.context.pages)
    try:
        popup = _abrir_lookup(
            page,
            seletor_campo=seletor_campo,
            seletor_botao=seletor_botao,
            label_campo=label_campo,
        )
    except Exception as e:
        print(f"[Lookup] recriar: não abriu lookup: {e}")
        return False
    if popup is None:
        return False

    try:
        if filtro:
            _selecionar_filtro(popup, filtro)
        _preencher_e_pesquisar(popup, termo)
        popup.wait_for_timeout(900)

        # se agora existe, só seleciona
        if _tem_resultados(popup):
            print(f"[Lookup] Agora achou '{termo}' na lista - seleciona (não cria)")
            if _selecionar_resultado(
                popup, termo, uf_preferida=uf_preferida, match_exato=match_exato
            ) or _selecionar_primeiro_da_lista(
                popup, label_campo=label_campo, forcar_link_nome=True
            ):
                try:
                    _aguardar_retorno(page, popup)
                except Exception:
                    pass
                page = _garantir_pagina_origem(
                    page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
                )
                if not seletor_campo or _campo_origem_preenchido(page, seletor_campo):
                    return True

        # 0 de 0 -> Novo Cadastro de novo
        form_page = _abrir_novo_cadastro(page.context, popup, pages_antes)
        if form_page is None:
            form_page = _abrir_novo_cadastro_js(page.context, popup)
        if form_page is None:
            print("[Lookup] [!] Recriar: não abriu Novo Cadastro")
            try:
                _fechar(popup)
            except Exception:
                pass
            return False

        form_page.bring_to_front()
        form_page.wait_for_timeout(400)
        preencher_novo(form_page)
        salvou = _salvar_com_confirmacao(form_page)
        if not salvou or _form_cadastro_ainda_aberto(form_page):
            # 2º fill+save no mesmo form
            print("[Lookup] Recriar: 2º fill+save no form...")
            try:
                preencher_novo(form_page)
            except Exception:
                pass
            salvou = _salvar_com_confirmacao(form_page)

        if not salvou or _form_cadastro_ainda_aberto(form_page):
            print(
                f"[Lookup] [!] Recriar '{termo}' ainda falhou no Salvar "
                f"(confira cidade/campos obrigatórios no form)."
            )
            # deixa form aberto um pouco para debug, depois fecha
            form_page.wait_for_timeout(800)
            try:
                _fechar_e_voltar(form_page, popup, page)
            except Exception:
                pass
            return False

        try:
            _fechar_e_voltar(form_page, popup, page)
        except Exception:
            pass
        try:
            _fechar(popup)
        except Exception:
            pass
        try:
            if not form_page.is_closed():
                form_page.close()
        except Exception:
            pass

        page = _garantir_pagina_origem(
            page, seletor_campo=seletor_campo, seletor_botao=seletor_botao
        )
        page.wait_for_timeout(800)
        if seletor_campo and _campo_origem_preenchido(page, seletor_campo):
            return True
        ok = _reabrir_e_selecionar(
            page,
            termo=termo,
            label_campo=label_campo,
            seletor_campo=seletor_campo,
            seletor_botao=seletor_botao,
            filtro=filtro,
            uf_preferida=uf_preferida,
            match_exato=match_exato,
        )
        if seletor_campo and _campo_origem_preenchido(page, seletor_campo):
            print(f"[Lookup] [OK] Recriado e vinculado: {termo}")
            return True
        return bool(ok)
    except Exception as e:
        print(f"[Lookup] recriar erro: {e}")
        try:
            _fechar(popup)
        except Exception:
            pass
        return False


def _fechar_e_voltar(form_page: Page, popup: Page, origem: Page) -> None:
    """
    Depois de cadastrar: fecha a página nova e volta para a anterior.

    Ordem:
      1. tenta botão Fechar / Voltar para Consulta
      2. se for aba extra, page.close()
      3. foca de volta na popup ou na origem
    """
    print("[Lookup] Voltando para a página anterior...")

    # tenta "Voltar para Consulta" / Fechar no form
    for seletor in (
        'button:has-text("Voltar para Consulta")',
        'a:has-text("Voltar para Consulta")',
        'button:has-text("Fechar")',
        'a:has-text("Fechar")',
        'text=Voltar para Consulta',
        'text=Fechar',
    ):
        try:
            if form_page.is_closed():
                break
            loc = form_page.locator(seletor).first
            if loc.count():
                loc.click(timeout=2000)
                form_page.wait_for_timeout(500)
                break
        except Exception:
            continue

    # se ainda aberta e não é a mesma que popup/origem -> fecha aba
    try:
        if (
            not form_page.is_closed()
            and form_page != popup
            and form_page != origem
            and len(form_page.context.pages) > 1
        ):
            form_page.close()
            print("[Lookup] Página de cadastro fechada.")
    except Exception as e:
        print(f"[Lookup] Ao fechar form: {e}")

    # foca popup ou origem
    try:
        if not popup.is_closed():
            popup.bring_to_front()
        else:
            origem.bring_to_front()
    except Exception:
        pass


def _fechar(popup: Page) -> None:
    for seletor in (
        'button:has-text("Fechar")',
        'a:has-text("Fechar")',
        'input[value*="Fechar"]',
        'text=Fechar',
    ):
        try:
            popup.locator(seletor).first.click(timeout=1500)
            return
        except Exception:
            continue
    try:
        if len(popup.context.pages) > 1:
            popup.close()
    except Exception:
        pass


def _aguardar_retorno(origem: Page, popup: Page) -> None:
    """
    Após clicar no resultado da grid Localizar:
      - O GW fecha a popup SOZINHO e grava o valor no campo.
      - NÃO clicar Fechar cedo: Fechar cancela a seleção e o campo fica vazio
        (bug real: prop já cadastrado -> clica nome -> Fechar -> fecha sem marcar).
    """
    # 1) Espera a popup fechar sozinha (seleção OK) - máx ~2s
    try:
        if popup and popup != origem:
            for _ in range(10):
                try:
                    if popup.is_closed():
                        break
                except Exception:
                    break
                try:
                    origem.wait_for_timeout(180)
                except Exception:
                    break
    except Exception:
        pass

    # 2) Se ainda aberta - Enter / espera curta
    try:
        if popup and popup != origem and not popup.is_closed():
            try:
                popup.keyboard.press("Enter")
                origem.wait_for_timeout(250)
            except Exception:
                pass
            for _ in range(4):
                try:
                    if popup.is_closed():
                        break
                except Exception:
                    break
                try:
                    origem.wait_for_timeout(200)
                except Exception:
                    break
    except Exception:
        pass

    # 3) Só fecha manualmente se AINDA aberta após espera longa
    #    (seleção pode ter falhado - melhor fechar do que travar)
    try:
        if popup and popup != origem and not popup.is_closed():
            print("[Lookup] Popup ainda aberta após seleção - fecha sem cancelar cedo")
            for seletor in (
                'button:has-text("Fechar")',
                'a:has-text("Fechar")',
                'input[value*="Fechar"]',
            ):
                try:
                    loc = popup.locator(seletor).first
                    if loc.count() and loc.is_visible(timeout=400):
                        loc.click(timeout=1200)
                        break
                except Exception:
                    continue
            try:
                if not popup.is_closed() and len(popup.context.pages) > 1:
                    popup.close()
            except Exception:
                pass
    except Exception:
        pass

    try:
        if origem and not origem.is_closed():
            origem.bring_to_front()
            origem.wait_for_timeout(500)
    except Exception:
        pass
