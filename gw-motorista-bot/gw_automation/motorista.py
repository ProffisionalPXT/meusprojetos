"""
Fases 3 e 4 - Preencher Motorista.

Names reais do formulário GW (dump cadmotorista):
  cpf, nome, cep, endereco, bairro, complemento, numeroLogradouro
  cidade, uf + btn (lookup cidade)
  datanasc, cidNaturalidade, ufNaturalidade + btn_origem (lookup naturalidade)
  nacionalidade, sexo, nomepai, nomemae
  rg, orgao_rg, uf_rg, cnh, vencimentocnh, categcnh, primeiraHabilitacaoEm
"""
from __future__ import annotations

from playwright.sync_api import Page

from gw_automation.lookup import buscar_com_tres_pontinhos
from ocr.extrair_dados import DadosMotorista
from utils.texto import gw_texto


def preencher_dados_pessoais(page: Page, dados: DadosMotorista) -> None:
    """
    Ordem importante (regra do usuário):
      1. Sabe cidade/naturalidade (ex. PAULISTA-PE)
      2. Se não tem CEP -> busca CEP da cidade (ViaCEP / faixa, como "cep paulista pe")
      3. Preenche CEP primeiro
      4. Dispara busca do CEP no GW -> *Cidade preenche sozinha
      5. Só faz lookup de cidade se ainda estiver vazia
    """
    print("[Fase 3] Preenchendo Dados Pessoais (names reais)...")

    # CPF primeiro - se já existir, GW pergunta "deseja visualizá-lo?" -> OK
    _fill(page, "cpf", dados.cpf)
    try:
        page.locator('input[name="cpf"]').first.evaluate("el => el.blur()")
    except Exception:
        try:
            page.keyboard.press("Tab")
        except Exception:
            pass
    page.wait_for_timeout(600)

    from gw_automation.existentes import (
        avisar_duplicidade_apos_fill,
        tratar_dialog_motorista_ja_cadastrado,
    )

    if tratar_dialog_motorista_ja_cadastrado(page):
        print(
            "  [OK] Motorista JÁ cadastrado - cadastro aberto. "
            "Só preenche campos VAZIOS + veículos depois."
        )
        # marca no objeto (opcional) via return path no main
        dados._ja_existia = True  # type: ignore[attr-defined]
    else:
        dup = avisar_duplicidade_apos_fill(page, "CPF motorista")
        if dup in ("motorista", "cpf", "generico"):
            print("  [!] CPF já cadastrado - tentando abrir visualização...")
            tratar_dialog_motorista_ja_cadastrado(page)

    # Textos sem acento (GW lookup: PALMEIRA DOS INDIOS, não ÍNDIOS/?)
    dados.nome = gw_texto(dados.nome or "")
    dados.endereco = gw_texto(dados.endereco or "")
    dados.bairro = gw_texto(dados.bairro or "")
    dados.complemento = gw_texto(dados.complemento or "")
    dados.cidade = gw_texto(dados.cidade or "")
    dados.uf = gw_texto(dados.uf or "")[:2]
    dados.naturalidade = gw_texto(dados.naturalidade or "")
    dados.nacionalidade = gw_texto(dados.nacionalidade or "")
    dados.nome_pai = gw_texto(dados.nome_pai or "")
    dados.nome_mae = gw_texto(dados.nome_mae or "")
    dados.local_emissao_cnh = gw_texto(getattr(dados, "local_emissao_cnh", "") or "")

    # Só preenche se o campo ainda estiver vazio (não apaga o que já está salvo)
    _fill_se_vazio(page, "nome", dados.nome)

    # CEP / endereço só se faltando
    if not _campo_preenchido(page, "cep"):
        _garantir_e_preencher_cep(page, dados)
    _fill_se_vazio(page, "endereco", dados.endereco)
    _fill_se_vazio(page, "bairro", dados.bairro)
    _fill_se_vazio(page, "complemento", dados.complemento)

    if not _campo_preenchido(page, "cidade"):
        if dados.cidade:
            print("  -> Cidade vazia - lookup...")
            _lookup_ou_fill(
                page,
                termo=gw_texto(dados.cidade),
                label="Cidade",
                campo_texto="cidade",
                botao_id="btn",
                uf=dados.uf or "PE",
                campo_uf="uf",
                match_exato=True,
            )
    else:
        try:
            cid = page.input_value('input[name="cidade"]', timeout=1000)
            print(f"  [OK] Cidade já salva: {cid!r}")
        except Exception:
            pass

    _fill_se_vazio(page, "datanasc", dados.data_nascimento)

    if not _campo_preenchido(page, "cidNaturalidade"):
        nat = gw_texto(dados.naturalidade or "")
        if nat:
            # UF da naturalidade: se residência é AL e nasceu em Palmeira, usa AL
            uf_nat = (dados.uf or "").strip().upper()[:2] or "AL"
            # se naturalidade tem , UF no texto (raro após limpeza)
            print(f"  -> Naturalidade lookup: {nat!r} / {uf_nat}")
            _lookup_ou_fill(
                page,
                termo=nat,
                label="Naturalidade",
                campo_texto="cidNaturalidade",
                botao_id="btn_origem",
                uf=uf_nat,
                campo_uf="ufNaturalidade",
                match_exato=True,
            )

    _fill_se_vazio(page, "nacionalidade", dados.nacionalidade or "BRASILEIRO")

    if dados.sexo and not _campo_preenchido_select(page, "sexo"):
        _select(page, "sexo", dados.sexo, extras=["Masculino", "Feminino", "M", "F"])

    _fill_se_vazio(page, "nomepai", dados.nome_pai)
    _fill_se_vazio(page, "nomemae", dados.nome_mae)

    print("[Fase 3] Dados Pessoais - concluído (só preencheu o que faltava).")


def _garantir_e_preencher_cep(page: Page, dados: DadosMotorista) -> None:
    """
    Se não tem CEP legível no doc, mas sabe naturalidade/cidade
    (ex.: nasceu em Paulista-PE), busca CEP (ViaCEP ≈ Google 'cep paulista pe')
    e preenche o campo CEP. Depois aciona a lupa/blur para o GW
    preencher a cidade embaixo.
    """
    from utils.cep_por_cidade import buscar_cep_por_cidade

    cep = "".join(c for c in (dados.cep or "") if c.isdigit())
    if len(cep) != 8:
        # Sem CEP no doc -> busca pela NATURALIDADE (nascimento), não pela cidade do prop
        nat = (dados.naturalidade or "").strip()
        print(
            f"  -> CEP ausente/ incompleto. Buscando pela naturalidade "
            f"({nat or dados.cidade}/{dados.uf or 'PE'})..."
        )
        cep_novo, end = buscar_cep_por_cidade(
            cidade="",  # força prioridade na naturalidade
            uf=dados.uf,
            naturalidade=nat or dados.cidade,
        )
        if cep_novo:
            cep = cep_novo
            dados.cep = cep_novo
            if end:
                dados.endereco = dados.endereco or end.endereco
                dados.bairro = dados.bairro or end.bairro
                # residência = cidade de nascimento
                dados.cidade = end.cidade
                dados.uf = end.uf
        else:
            print("  [!] Não achou CEP para a região de nascimento")
            return

    if not cep:
        return

    print(f"  -> Preenchendo CEP primeiro: {cep}")
    _fill(page, "cep", cep)

    # Dispara preenchimento automático da cidade no GW
    _disparar_busca_cep(page)
    page.wait_for_timeout(900)


def _disparar_busca_cep(page: Page) -> None:
    """Tab/blur ou botão ao lado do CEP para o sistema carregar a cidade."""
    try:
        loc = page.locator('input[name="cep"], #cep').first
        if loc.count():
            loc.press("Tab")
            page.wait_for_timeout(400)
    except Exception:
        pass
    # botões comuns de lupa CEP
    for seletor in (
        'input[name="cep"] ~ input[type="button"]',
        'input[name="cep"] ~ img',
        'tr:has-text("CEP") input[type="button"]',
        'tr:has-text("CEP") img',
        'img[title*="CEP"]',
        'img[src*="lupa"]',
    ):
        try:
            b = page.locator(seletor).first
            if b.count() and b.is_visible():
                b.click(timeout=1500)
                print("  [OK] Disparou busca de CEP (lupa/botão)")
                page.wait_for_timeout(800)
                return
        except Exception:
            continue
    # Enter no campo
    try:
        page.locator('input[name="cep"]').first.press("Enter")
        page.wait_for_timeout(600)
    except Exception:
        pass


def _campo_preenchido(page: Page, name: str) -> bool:
    try:
        val = page.input_value(f'input[name="{name}"]', timeout=1000)
        return bool((val or "").strip())
    except Exception:
        return False


def preencher_documentacao(page: Page, dados: DadosMotorista) -> None:
    print("[Fase 4] Aba Documentação...")
    for seletor in (
        'a:has-text("Documentação")',
        'td:has-text("Documentação")',
        "text=Documentação",
    ):
        try:
            page.locator(seletor).first.click(timeout=4000)
            page.wait_for_timeout(700)
            print("  [OK] Aba Documentação")
            break
        except Exception:
            continue

    _fill_se_vazio(page, "rg", dados.rg)

    orgao, uf_org = _separar_orgao(dados.orgao_emissor)
    _fill_se_vazio(page, "orgao_rg", orgao)
    _fill_se_vazio(page, "uf_rg", uf_org)

    _fill_se_vazio(page, "cnh", dados.cnh)
    _fill_se_vazio(page, "vencimentocnh", dados.validade_cnh)
    _fill_se_vazio(page, "dataemissaocnh", getattr(dados, "data_emissao_cnh", "") or "")
    _fill_se_vazio(page, "localemissaocnh", getattr(dados, "local_emissao_cnh", "") or "")
    _fill_se_vazio(page, "primeiraHabilitacaoEm", dados.data_primeira_habilitacao)

    # Categoria: SEMPRE aplica o valor do OCR (não confiar em default C/A do GW)
    if dados.categoria_cnh:
        _selecionar_categoria_cnh(page, dados.categoria_cnh)

    print("[Fase 4] Documentação - concluído (só o que faltava).")


def _selecionar_categoria_cnh(page: Page, categoria: str) -> bool:
    """
    Select #categcnh com opções A B C D E AB AC AD AE.
    Nunca cai para a 1ª letra se a categoria for combinada (AE -> não vira A ou C).
    """
    cat = (categoria or "").strip().upper().replace(" ", "").replace("/", "")
    if not cat:
        return False

    seletor = 'select[name="categcnh"], #categcnh'
    # o que o GW já tem
    atual = ""
    try:
        atual = (page.locator(seletor).first.input_value(timeout=800) or "").strip().upper()
    except Exception:
        pass
    if atual == cat or atual.replace("/", "") == cat:
        print(f"  · categcnh já = {atual}")
        return True

    # 1) lista opções reais do select e escolhe EXATA
    try:
        opts = page.locator(f"{seletor} option")
        n = opts.count()
        for i in range(n):
            opt = opts.nth(i)
            try:
                lab = (opt.inner_text(timeout=300) or "").strip().upper().replace(" ", "")
                val = (opt.get_attribute("value") or "").strip().upper().replace(" ", "")
            except Exception:
                continue
            lab_n = lab.replace("/", "")
            val_n = val.replace("/", "")
            if lab_n == cat or val_n == cat or lab == cat or val == cat:
                # prefer value se existir
                try:
                    if val:
                        page.select_option(seletor, value=opt.get_attribute("value"), timeout=2000)
                    else:
                        page.select_option(seletor, label=opt.inner_text().strip(), timeout=2000)
                    # confere
                    conf = (page.locator(seletor).first.input_value(timeout=800) or "").strip().upper()
                    conf_n = conf.replace("/", "").replace(" ", "")
                    if conf_n == cat or conf == cat:
                        print(f"  [OK] categcnh = {cat} (era {atual or 'vazio'})")
                        return True
                    print(f"  [!] categcnh ficou {conf!r} (queríamos {cat})")
                except Exception as e:
                    print(f"  [!] select categcnh opção {lab}/{val}: {e}")
    except Exception as e:
        print(f"  [!] ler opções categcnh: {e}")

    # 2) tentativas diretas (sem cair em letra única se cat tiver 2 letras)
    tentativas = [cat, f"{cat[0]}/{cat[1]}" if len(cat) == 2 else cat]
    if len(cat) == 1:
        tentativas.append(cat)
    for v in tentativas:
        if not v:
            continue
        try:
            page.select_option(seletor, label=str(v), timeout=1500)
            conf = (page.locator(seletor).first.input_value(timeout=800) or "").strip().upper()
            if conf.replace("/", "") == cat or conf == cat:
                print(f"  [OK] categcnh label={v}")
                return True
        except Exception:
            pass
        try:
            page.select_option(seletor, value=str(v), timeout=1000)
            conf = (page.locator(seletor).first.input_value(timeout=800) or "").strip().upper()
            if conf.replace("/", "") == cat or conf == cat:
                print(f"  [OK] categcnh value={v}")
                return True
        except Exception:
            pass

    # 3) ÚLTIMO recurso: só 1 letra se a combinada não existir no select
    if len(cat) >= 2:
        # preferência E se for *E (carreteiro), senão 1ª letra
        for letra in (cat[-1], cat[0]):
            try:
                page.select_option(seletor, label=letra, timeout=1000)
                print(
                    f"  [!] categcnh: '{cat}' não existia no select - "
                    f"usou '{letra}' (confira no GW)"
                )
                return False
            except Exception:
                continue

    print(f"  [!] Categoria CNH '{cat}' NÃO selecionada - ajuste manual")
    return False


def _fill(page: Page, name: str, valor: str) -> bool:
    if not valor:
        return False
    for seletor in (f'input[name="{name}"]', f"#{name}", f'select[name="{name}"]'):
        try:
            loc = page.locator(seletor).first
            if loc.count() == 0:
                continue
            tag = loc.evaluate("e => e.tagName.toLowerCase()")
            if tag == "select":
                try:
                    page.select_option(seletor, label=str(valor), timeout=2000)
                except Exception:
                    page.select_option(seletor, value=str(valor), timeout=2000)
            else:
                loc.fill(str(valor), timeout=2500, force=True)
            print(f"  [OK] {name} = {valor}")
            return True
        except Exception:
            continue
    print(f"  [!] não preencheu {name}={valor}")
    return False


def _fill_se_vazio(page: Page, name: str, valor: str) -> bool:
    """Não sobrescreve o que o GW já tem salvo."""
    if not valor:
        return False
    if _campo_preenchido(page, name):
        try:
            atual = page.input_value(f'input[name="{name}"]', timeout=800)
            print(f"  · {name} já preenchido ({atual!r}) - mantém")
        except Exception:
            print(f"  · {name} já preenchido - mantém")
        return True
    return _fill(page, name, valor)


def _campo_preenchido_select(page: Page, name: str) -> bool:
    try:
        val = page.locator(f'select[name="{name}"]').first.input_value(timeout=800)
        return bool(val and val not in ("", "0", "Selecione"))
    except Exception:
        return False


def _select(page: Page, name: str, valor: str, extras: list | None = None) -> bool:
    if not valor:
        return False
    tentativas = [valor] + list(extras or [])
    seletor = f'select[name="{name}"]'
    for v in tentativas:
        if not v:
            continue
        try:
            page.select_option(seletor, label=str(v), timeout=1500)
            print(f"  [OK] select {name} = {v}")
            return True
        except Exception:
            try:
                page.select_option(seletor, value=str(v), timeout=1000)
                print(f"  [OK] select {name} value={v}")
                return True
            except Exception:
                continue
    # sexo: M/F
    if name == "sexo":
        s = valor.strip().upper()
        label = "Masculino" if s in ("M", "MASCULINO") else "Feminino"
        try:
            page.select_option(seletor, label=label, timeout=1500)
            print(f"  [OK] select sexo = {label}")
            return True
        except Exception:
            pass
    return False


def _lookup_ou_fill(
    page: Page,
    *,
    termo: str,
    label: str,
    campo_texto: str,
    botao_id: str,
    uf: str = "",
    campo_uf: str = "",
    match_exato: bool = False,
) -> None:
    """Clica no botão de lookup (#btn / #btn_origem) e pesquisa com UF exata."""
    print(f"  -> Lookup {label}: {termo} / {uf or '?'}")

    # Uma tentativa basta (vários filtros derrubavam a página)
    seletor_btn = f"#{botao_id}"
    try:
        if page.locator(seletor_btn).count() == 0:
            seletor_btn = f'input[name="{botao_id}"]'
    except Exception:
        pass

    ok = buscar_com_tres_pontinhos(
        page,
        termo=termo,
        label_campo=label,
        seletor_botao=seletor_btn,
        filtro="Cidade" if match_exato else "Descrição",
        uf_preferida=uf,
        match_exato=match_exato,
        preencher_novo=None,
    )
    if ok:
        if uf and campo_uf:
            try:
                if not page.is_closed():
                    _fill(page, campo_uf, uf)
            except Exception:
                pass
        return

    print(f"  [!] Lookup {label} não vinculou '{termo}/{uf}' - não digita no campo readonly")


def _separar_orgao(texto: str) -> tuple[str, str]:
    t = (texto or "").strip().replace("/", " ").replace("-", " ")
    parts = [p for p in t.split() if p]
    if len(parts) >= 2 and len(parts[-1]) == 2 and parts[-1].isalpha():
        return " ".join(parts[:-1]), parts[-1].upper()
    return t, ""
