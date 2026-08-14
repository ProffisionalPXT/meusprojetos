"""
Cadastro de Proprietário via popup "Localizar proprietário".

Fluxo:
  3 pontinhos no campo Proprietário (no form do veículo)
  -> Localizar proprietário
  -> filtro Nome ou CPF/CNPJ + Pesquisar
  -> se existe: clica na linha
  -> se não: Novo Cadastro
      -> preenche: Nome, CPF/CNPJ, RG ou I.E., Cidade (lookup), RNTRC
      -> Salvar
      -> volta ao veículo

Cidade é obrigatória no GW (campo cinza + ...). Sem ela o Salvar do prop falha.
Não preenche: endereço completo, telefone, checkbox TAC, representante legal, etc.
"""
from __future__ import annotations

from playwright.sync_api import Page

from gw_automation.lookup import buscar_com_tres_pontinhos
from ocr.extrair_dados import DadosProprietario


RG_PADRAO = "0000000"
IE_PADRAO = "0000000"


def garantir_proprietario(
    page: Page,
    dados: DadosProprietario | None,
    *,
    label_campo: str = "Proprietário",
    seletor_campo: str = "",
) -> bool:
    if not dados or not (dados.cpf_cnpj or dados.nome):
        print("[Proprietário] Sem dados - pulando.")
        return False

    dados.aplicar_regras_gw()
    termo = dados.cpf_cnpj or dados.nome

    # Filtro da popup: preferir CPF/CNPJ se tiver documento
    filtro = "Nome"
    digitos = "".join(c for c in (dados.cpf_cnpj or "") if c.isdigit())
    if len(digitos) == 11:
        filtro = "CPF"
        termo = digitos
    elif len(digitos) == 14:
        filtro = "CNPJ"
        termo = digitos
    elif dados.tipo_doc in ("CPF", "CNPJ"):
        filtro = dados.tipo_doc

    print(f"[Proprietário] Verificar se existe: '{termo}' (filtro={filtro})")

    def _novo(form: Page) -> None:
        print("[Proprietário] Novo Cadastro aberto - preenchendo formulário...")
        _preencher_form_proprietario(form, dados)

    ok = buscar_com_tres_pontinhos(
        page,
        termo=termo,
        label_campo=label_campo,
        seletor_campo=seletor_campo,
        filtro=filtro,
        preencher_novo=_novo,
    )
    # CNPJ não achou -> tenta pelo NOME (às vezes a base só indexa razão social)
    if not ok and digitos and len(digitos) == 14 and (dados.nome or "").strip():
        print(f"[Proprietário] CNPJ sem resultado - tentando Nome={dados.nome!r}")
        ok = buscar_com_tres_pontinhos(
            page,
            termo=dados.nome.strip(),
            label_campo=label_campo,
            seletor_campo=seletor_campo,
            filtro="Nome",
            preencher_novo=_novo,
        )
    return ok


def _preencher_form_proprietario(page: Page, dados: DadosProprietario) -> None:
    """
    Tela cadproprietario?acao=iniciar.

    Preenche:
      1. *Nome  (obrigatório - antes falhava e ficava em branco)
      2. CPF ou CNPJ
      3. R.G. (CPF) ou I.E. (CNPJ) - padrão 0000000 se vazio
      4. *Cidade (lookup ... do CRLV)
      5. RNTRC (se houver no TAC)
    """
    dados.aplicar_regras_gw()
    page.wait_for_timeout(200)

    _voltar_aba_dados_principais(page)

    digitos = "".join(c for c in (dados.cpf_cnpj or "") if c.isdigit())
    if not dados.tipo_doc:
        if len(digitos) == 11:
            dados.tipo_doc = "CPF"
        elif len(digitos) == 14:
            dados.tipo_doc = "CNPJ"

    nome = (dados.nome or "").strip().lstrip("'\"").rstrip("'\"").strip()
    # Segurança: corta lixo OCR que possa ter chegado no nome
    # Ex.: "TRANSP LTDA CADASTRADO DESDE 12/2020" -> "TRANSP LTDA"
    import re as _re
    nome = _re.split(r"\bCADASTRADO\s*DESDE\b", nome, maxsplit=1, flags=_re.I)[0].strip()
    nome = _re.split(r"\bCNPJ\b|\bCPF\s*/?CNPJ\b", nome, maxsplit=1, flags=_re.I)[0].strip(" -|\"'")
    # se nome ficou muito curto após corte, tenta reconstruir do dados
    if len(nome.replace(" ", "")) < 5:
        nome = ""
    # fallback: se o prop é a mesma pessoa do motorista (CPF igual), usa nome do motorista
    if not nome and digitos and hasattr(dados, "_nome_fallback"):
        nome = (getattr(dados, "_nome_fallback") or "").strip()

    print(
        f"[Proprietário] Campos: nome={nome!r} "
        f"{dados.tipo_doc}={digitos} IE/RG "
        f"cidade={dados.cidade or '?'}/{dados.uf or '?'} "
        f"RNTRC={dados.rntrc or '(vazio)'}"
    )

    # 1) *Nome PRIMEIRO (antes do CPF - o combo às vezes re-renderiza e apaga)
    if not nome:
        print("  [!] Nome do prop vazio nos dados - form vai bloquear Salvar")
    else:
        ok_nome = _preencher_nome_proprietario(page, nome)
        if not ok_nome:
            print(f"  [!] NÃO preencheu *Nome={nome!r} - tentando de novo...")
            page.wait_for_timeout(150)
            _preencher_nome_proprietario(page, nome)

    # 2) Combo CPF / CNPJ + documento
    if dados.tipo_doc:
        _selecionar_tipo_doc(page, dados.tipo_doc)

    if dados.tipo_doc == "CNPJ" or len(digitos) == 14:
        _fill(
            page,
            digitos or dados.cpf_cnpj,
            'input[name="cpf"]',
            '#cpf',
            'input[name*="cnpj" i]',
            '#cnpj',
            'input[name*="documento" i]',
            'input[name*="nrDocumento" i]',
        )
    else:
        _fill(
            page,
            digitos or dados.cpf_cnpj,
            'input[name="cpf"]',
            '#cpf',
            'input[name*="cpf" i]',
            'input[name*="documento" i]',
            'input[name*="nrDocumento" i]',
        )

    # 3) Re-aplica NOME se o combo CPF apagou o campo
    if nome and not _nome_prop_preenchido(page, nome):
        print("  -> Nome sumiu após CPF - preenche de novo")
        _preencher_nome_proprietario(page, nome)

    # 4) R.G. / I.E.
    if dados.tipo_doc == "CPF" or len(digitos) == 11:
        rg = (dados.rg or "").strip() or RG_PADRAO
        if set(rg) <= {"0"}:
            rg = RG_PADRAO
        _fill(
            page,
            rg,
            "#rg",
            'input[name="rg"]',
            'input[name*="rg"]',
            'tr:has-text("R.G") input[type="text"]',
            'tr:has-text("R.G.") input[type="text"]',
        )
        print(f"  [OK] CPF -> R.G. = {rg}")
    elif dados.tipo_doc == "CNPJ" or len(digitos) == 14:
        ie = (dados.inscricao_estadual or "").strip() or IE_PADRAO
        if set(ie) <= {"0"} or len(ie) < 5:
            ie = IE_PADRAO
        _fill(
            page,
            ie,
            'input[name*="inscricao" i]',
            'input[name*="ie" i]',
            'input[name*="estadual" i]',
            "#ie",
            'tr:has-text("I.E") input[type="text"]',
            'tr:has-text("I.E.") input[type="text"]',
        )
        print(f"  [OK] CNPJ -> I.E. = {ie}")

    # 5) Cidade (1 tentativa rápida; se falhar, segue e tenta de novo no final)
    try:
        _preencher_cidade_proprietario(page, dados)
    except Exception as e:
        print(f"  [!] Cidade no form do prop falhou: {e}")

    # 6) RNTRC
    _preencher_rntrc_somente(page, dados)

    _voltar_aba_dados_principais(page)
    # Nome final (crítico)
    if nome and not _nome_prop_preenchido(page, nome):
        print("  -> Nome ainda vazio no final - força preenchimento")
        _preencher_nome_proprietario(page, nome)
    if not _cidade_ja_preenchida(page, dados.cidade or ""):
        try:
            _preencher_cidade_proprietario(page, dados)
        except Exception as e:
            print(f"  [!] re-checagem cidade: {e}")
    page.wait_for_timeout(100)


def _nome_prop_preenchido(page: Page, esperada: str = "") -> bool:
    """True se *Nome do prop tem texto (opcionalmente com o esperado)."""
    for sel in (
        'input[name="nome"]',
        "#nome",
        'tr:has-text("Nome") input[type="text"]',
        'input[name*="razao" i]',
    ):
        try:
            val = (page.input_value(sel, timeout=400) or "").strip()
            if len(val) < 3:
                continue
            if not esperada:
                return True
            # casa início do nome (GW pode cortar)
            e = esperada.strip().upper()[:12]
            if e and e in val.upper():
                return True
            if len(val) >= 5:
                return True
        except Exception:
            continue
    return False


def _preencher_nome_proprietario(page: Page, nome: str) -> bool:
    """
    Preenche *Nome no cadproprietario de várias formas.
    Print real: input grande à esquerda, rótulo *Nome.
    """
    nome = (nome or "").strip()
    if not nome:
        return False

    # 1) Seletores diretos (sem bloquear por 'representante legal' falso positivo)
    for sel in (
        'input[name="nom"]',
        '#nom',
        'input[id="nom"]',
        'input[name="nome"]',
        '#nome',
        'input[id="nome"]',
        'input[name="razaoSocial"]',
        'input[name*="razao" i]',
        'input[name*="rzs" i]',
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            # ignora se estiver na aba/área de representante
            try:
                near = loc.evaluate(
                    """el => {
                        let n = el;
                        for (let i = 0; i < 6 && n; i++) {
                            const id = ((n.id||'')+(n.className||'')).toLowerCase();
                            if (id.includes('representante')) return true;
                            n = n.parentElement;
                        }
                        return false;
                    }"""
                )
                if near:
                    continue
            except Exception:
                pass
            loc.click(timeout=600)
            loc.fill("", timeout=800)
            loc.fill(nome, timeout=2000, force=True)
            page.wait_for_timeout(80)
            got = (loc.input_value(timeout=400) or "").strip()
            if len(got) >= 3:
                print(f"  [OK] prop nome ({sel}) = {got}")
                return True
        except Exception:
            continue

    # 2) Pelo rótulo *Nome / Nome
    if _fill_por_rotulo(page, nome, ("*Nome", "Nome", "Razão Social", "Razao Social")):
        if _nome_prop_preenchido(page, nome):
            return True

    # 3) JS: 1º input texto grande na tabela Dados principais (não CPF/RG)
    try:
        ok = page.evaluate(
            """(nome) => {
                const bad = /cpf|cnpj|rg|ie|cep|telefone|celular|email|pis|cnh|depend/i;
                const inputs = Array.from(document.querySelectorAll(
                    'input[type="text"], input:not([type])'
                ));
                for (const el of inputs) {
                    if (el.offsetParent === null) continue;
                    if (el.readOnly || el.disabled) continue;
                    const nm = (el.name||'') + ' ' + (el.id||'');
                    if (bad.test(nm)) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width < 120 || r.height < 10) continue;
                    // tipicamente o *Nome é o input largo do topo
                    if (r.y > 350) continue;
                    el.focus();
                    el.value = '';
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.value = nome;
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                    if (window.jQuery) {
                        try { window.jQuery(el).val(nome).trigger('input').trigger('change'); }
                        catch(e) {}
                    }
                    if ((el.value||'').trim().length >= 3) return el.name || el.id || 'ok';
                }
                return '';
            }""",
            nome,
        )
        if ok:
            print(f"  [OK] prop nome (JS {ok}) = {nome}")
            return True
    except Exception as e:
        print(f"  [!] nome JS: {e}")

    # 4) force Playwright no 1º input visível da linha Nome
    try:
        loc = page.locator(
            'tr:has-text("Nome") input[type="text"]:visible, '
            'td:has-text("Nome") ~ td input[type="text"]:visible'
        ).first
        if loc.count():
            loc.fill(nome, timeout=2000, force=True)
            print(f"  [OK] prop nome (tr Nome) = {nome}")
            return True
    except Exception as e:
        print(f"  [!] nome tr: {e}")

    return _nome_prop_preenchido(page, nome)


def _preencher_cidade_proprietario(page: Page, dados: DadosProprietario) -> None:
    """
    Campo Cidade no cadproprietario é readonly cinza + botão ... (lookup).
    SEM cidade o GW não salva o proprietário.
    """
    cidade = (dados.cidade or "").strip()
    uf = (dados.uf or "").strip().upper() or "PE"
    if not cidade:
        print(
            "  [!] Proprietário SEM cidade nos dados (CRLV?) - "
            "o GW deve recusar Salvar"
        )
        return

    # Já preenchida?
    if _cidade_ja_preenchida(page, cidade):
        print(f"  [OK] Cidade já preenchida: {cidade}/{uf}")
        return

    print(f"  -> Cidade do proprietário (CRLV): clicar ... e buscar {cidade}/{uf}")

    # 1 tentativa rápida pelo label (evita loop em 10 seletores)
    ok = False
    try:
        ok = buscar_com_tres_pontinhos(
            page,
            termo=cidade,
            label_campo="Cidade",
            seletor_campo='input[name="cidade"]',
            seletor_botao='tr:has-text("Cidade") input[type="button"][value="..."]',
            filtro="Cidade",
            uf_preferida=uf,
            match_exato=True,
            preencher_novo=None,
        )
    except Exception as e:
        print(f"  · lookup cidade rápido: {e}")

    if not ok:
        try:
            ok = buscar_com_tres_pontinhos(
                page,
                termo=cidade,
                label_campo="Cidade",
                seletor_campo='input[name="cidade"]',
                filtro="Cidade",
                uf_preferida=uf,
                match_exato=True,
                preencher_novo=None,
            )
        except Exception as e:
            print(f"  · fallback cidade: {e}")

    if not ok:
        ok = _lookup_cidade_manual(page, cidade, uf)

    if ok or _cidade_ja_preenchida(page, cidade):
        print(f"  [OK] Cidade vinculada: {cidade}/{uf}")
    else:
        print(
            f"  [!] Cidade {cidade}/{uf} NÃO vinculada - "
            f"Salvar do prop provavelmente falha"
        )


def _lookup_cidade_manual(page: Page, cidade: str, uf: str) -> bool:
    """Clica no ... da linha Cidade e pesquisa na popup Localizar."""
    from gw_automation.lookup import (
        _selecionar_filtro,
        _preencher_e_pesquisar,
        _selecionar_resultado,
    )

    context = page.context
    pages_antes = set(context.pages)
    botao = None
    for sel in (
        'tr:has-text("Cidade") input[type="button"][value="..."]',
        'tr:has-text("Cidade") input[value="..."]',
        'tr:has-text("Cidade") input[type="button"]',
        'input[name="cidade"] ~ input[type="button"]',
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=500):
                botao = loc
                break
        except Exception:
            continue
    if botao is None:
        print("  [!] Não achou botão ... da Cidade no form prop")
        return False

    popup = None
    try:
        with context.expect_page(timeout=6000) as nova:
            botao.click(timeout=3000)
        popup = nova.value
        popup.wait_for_load_state("domcontentloaded", timeout=12000)
    except Exception:
        page.wait_for_timeout(800)
        novas = [p for p in context.pages if p not in pages_antes and not p.is_closed()]
        if novas:
            popup = novas[-1]
        else:
            if page.locator("text=Localizar").count():
                popup = page
    if popup is None:
        print("  [!] Popup Localizar Cidade não abriu")
        return False

    print(f"  -> Popup cidade: {getattr(popup, 'url', '?')}")
    try:
        _selecionar_filtro(popup, "Cidade")
    except Exception:
        pass
    try:
        _preencher_e_pesquisar(popup, cidade)
        popup.wait_for_timeout(800)
        ok = _selecionar_resultado(
            popup,
            cidade,
            uf_preferida=uf,
            match_exato=True,
        )
        return bool(ok)
    except Exception as e:
        print(f"  [!] lookup cidade manual: {e}")
        return False


def _cidade_ja_preenchida(page: Page, esperada: str = "") -> bool:
    for sel in (
        'input[name="cidade"]',
        "#cidade",
        'input[id*="cidade" i]',
        'tr:has-text("Cidade") input[type="text"]',
    ):
        try:
            val = (page.input_value(sel, timeout=800) or "").strip()
            if not val:
                continue
            if not esperada:
                return True
            if esperada.upper() in val.upper() or val.upper() in esperada.upper():
                return True
            # preenchida com outra cidade ainda conta
            if len(val) >= 3:
                return True
        except Exception:
            continue
    return False


def _preencher_rntrc_somente(page: Page, dados: DadosProprietario) -> None:
    """
    Só o campo RNTRC (número do TAC). Não marca checkbox TAC nem outros campos.
    """
    rntrc = "".join(c for c in (dados.rntrc or "") if c.isdigit())
    if not rntrc:
        print("  · RNTRC vazio - pula aba Operacional")
        return

    print(f"  -> RNTRC = {rntrc}")
    abriu = _abrir_aba_prop_exata(
        page,
        "Informações Operacionais",
        "Informacoes Operacionais",
    )
    if not abriu:
        print("  · Aba Operacional não abriu - tenta RNTRC na tela atual")
    page.wait_for_timeout(400)

    ok = _fill(
        page,
        rntrc,
        'input[name*="rntrc" i]',
        'input[id*="rntrc" i]',
        "#rntrc",
        'input[name*="RNTRC"]',
        'tr:has-text("RNTRC") input[type="text"]',
        'tr:has-text("RNTRC") input:not([type="hidden"])',
        'td:has-text("RNTRC") ~ td input',
    )
    if not ok:
        ok = _fill_por_rotulo(page, rntrc, ("RNTRC", "RNTC"))

    if ok:
        print(f"  [OK] RNTRC = {rntrc}")
    else:
        print(f"  [!] Campo RNTRC não encontrado - valor era {rntrc}")

    _voltar_aba_dados_principais(page)


def _preencher_rntrc_tac(page: Page, dados: DadosProprietario) -> None:
    """Compat: só RNTRC (sem TAC/outros)."""
    _preencher_rntrc_somente(page, dados)


# Abas que o robô NUNCA deve abrir no cadastro de proprietário
_ABAS_PROIBIDAS_PROP = (
    "representante legal",
    "representante",
    "financeiras",
    "financeira",
    "ocorrências",
    "ocorrencias",
    "ocorrencia",
)


def _voltar_aba_dados_principais(page: Page) -> None:
    """Garante foco em Dados principais (topo do form)."""
    for t in (
        "Dados principais",
        "Dados Principais",
        "Principal",
    ):
        if _abrir_aba_prop_exata(page, t):
            return
    # se não há aba "Dados principais", só não clica em nada


def _abrir_aba_prop_exata(page: Page, *nomes_aba: str) -> bool:
    """
    Clica em aba do cadproprietario pelo texto EXATO/quase exato.
    Nunca usa 'text=TAC' / 'Operacional' solto (abria Representante Legal etc.).
    """
    proib = _ABAS_PROIBIDAS_PROP
    for t in nomes_aba:
        if not t:
            continue
        t_low = t.strip().lower()
        if any(p in t_low for p in proib):
            continue
        # seletores de ABA (barra de abas), não qualquer td da página
        seletores = (
            f'[role="tab"]:has-text("{t}")',
            f'ul.tabs a:has-text("{t}")',
            f'ul.nav a:has-text("{t}")',
            f'.nav-tabs a:has-text("{t}")',
            f'.tabs a:has-text("{t}")',
            f'a.tab:has-text("{t}")',
            f'td.tab:has-text("{t}")',
            f'li.tab a:has-text("{t}")',
            f'a:has-text("{t}")',
        )
        for sel in seletores:
            try:
                locs = page.locator(sel)
                n = min(locs.count(), 8)
                for i in range(n):
                    loc = locs.nth(i)
                    if not loc.is_visible(timeout=300):
                        continue
                    txt = (loc.inner_text(timeout=300) or "").strip()
                    tl = txt.lower()
                    # rejeita abas proibidas e cliques genéricos
                    if any(p in tl for p in proib):
                        continue
                    # texto da aba deve ser o nome (ou contê-lo de forma clara)
                    if t_low not in tl and tl not in t_low:
                        continue
                    # evita clicar "Informações Operacionais" quando pediu só "Operacional"
                    # se o pedido for longo (>= 10), exige overlap forte
                    if len(t_low) >= 10 and t_low not in tl:
                        continue
                    loc.click(timeout=1500)
                    print(f"  [OK] Aba prop: {txt[:40]}")
                    page.wait_for_timeout(400)
                    return True
            except Exception:
                continue
    return False


def _abrir_aba_prop(page: Page, *textos: str) -> None:
    """Compat: só abas nomeadas de forma segura."""
    _abrir_aba_prop_exata(page, *textos)


def _marcar_tac(page: Page) -> None:
    for seletor in (
        'input[type="checkbox"][name*="tac" i]',
        'input[type="checkbox"][id*="tac" i]',
        'label:has-text("TAC") input[type="checkbox"]',
        'tr:has-text("TAC") input[type="checkbox"]',
        'input[type="checkbox"][name*="autonomo" i]',
    ):
        try:
            loc = page.locator(seletor).first
            if loc.count() == 0:
                continue
            if not loc.is_checked():
                loc.check(timeout=1500, force=True)
            print("  [OK] TAC marcado")
            return
        except Exception:
            continue
    # texto clicável
    try:
        loc = page.locator('text=TAC (Transportador').first
        if loc.count() and loc.is_visible(timeout=400):
            loc.click(timeout=1000)
            print("  [OK] TAC clicado (texto)")
    except Exception:
        pass


def _fill_por_rotulo(page: Page, valor: str, rotulos: tuple) -> bool:
    """Preenche o input na mesma linha de um rótulo (ex.: RNTRC)."""
    if not valor:
        return False
    for rot in rotulos:
        for sel in (
            f'tr:has-text("{rot}") input[type="text"]',
            f'tr:has-text("{rot}") input:not([type="hidden"]):not([type="button"]):not([type="checkbox"])',
            f'td:has-text("{rot}") ~ td input',
            f'*:has-text("{rot}") >> xpath=ancestor::tr[1]//input[not(@type="hidden") and not(@type="button")]',
        ):
            try:
                loc = page.locator(sel).first
                if loc.count() == 0 or not loc.is_visible(timeout=500):
                    continue
                loc.scroll_into_view_if_needed(timeout=1000)
                loc.fill(str(valor), timeout=2000, force=True)
                print(f"  [OK] prop (rótulo {rot}) = {valor}")
                return True
            except Exception:
                continue
    # JS: acha label e preenche input vizinho
    try:
        ok = page.evaluate(
            """([valor, rotulos]) => {
                const want = rotulos.map(r => r.toUpperCase());
                const nodes = Array.from(document.querySelectorAll('td, th, label, span, b'));
                for (const n of nodes) {
                    const t = (n.textContent || '').trim().toUpperCase();
                    if (!want.some(w => t === w || t.startsWith(w))) continue;
                    let tr = n.closest('tr');
                    let input = tr ? tr.querySelector('input:not([type=hidden]):not([type=button]):not([type=checkbox])') : null;
                    if (!input) {
                        let el = n.nextElementSibling;
                        for (let i = 0; i < 4 && el; i++) {
                            input = el.querySelector ? el.querySelector('input') : null;
                            if (input) break;
                            if (el.tagName === 'INPUT') { input = el; break; }
                            el = el.nextElementSibling;
                        }
                    }
                    if (input && input.offsetParent !== null) {
                        input.focus();
                        input.value = valor;
                        input.dispatchEvent(new Event('input', {bubbles:true}));
                        input.dispatchEvent(new Event('change', {bubbles:true}));
                        return true;
                    }
                }
                return false;
            }""",
            [str(valor), list(rotulos)],
        )
        if ok:
            print(f"  [OK] prop (JS rótulo) = {valor}")
            return True
    except Exception:
        pass
    return False


def _selecionar_tipo_doc(page: Page, tipo: str) -> None:
    for seletor in (
        'select:near(input[name*="cpf"])',
        'select:near(input[name*="cnpj"])',
        'select[name*="tipoDocumento"]',
        'select[name*="tipoPessoa"]',
        'select[name*="tipo"]',
        'tr:has-text("CPF") select',
        'tr:has-text("CNPJ") select',
    ):
        try:
            page.select_option(seletor, label=tipo, timeout=1500)
            print(f"  [OK] Tipo documento: {tipo}")
            return
        except Exception:
            try:
                page.select_option(seletor, value=tipo, timeout=1500)
                return
            except Exception:
                continue
    try:
        page.locator(f'select >> option:has-text("{tipo}")').first.click(timeout=1000)
    except Exception:
        pass


def _fill(page: Page, valor: str, *seletores: str) -> bool:
    if not valor:
        return False
    for seletor in seletores:
        try:
            locs = page.locator(seletor)
            n = min(locs.count(), 6)
            for i in range(n):
                loc = locs.nth(i)
                try:
                    if not loc.is_visible(timeout=250):
                        continue
                except Exception:
                    continue
                # Só pula se o próprio id/name for de representante (não o texto do form inteiro)
                try:
                    meta = ((loc.get_attribute("name") or "") + " " + (loc.get_attribute("id") or "")).lower()
                    if "representante" in meta:
                        continue
                except Exception:
                    pass
                try:
                    loc.fill(str(valor), timeout=1500, force=True)
                    print(f"  [OK] prop {seletor} = {valor}")
                    return True
                except Exception:
                    continue
        except Exception:
            continue
    return False
