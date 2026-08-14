"""
Cadastro de Veículo - formulário cadveiculo (names reais do dump).

Modelo de preenchimento completo (print de referência CAVALO/TRUCK):

  Dados principais:
    categoria=Veículo Terrestre
    pl=placa | numeroFrota
    ren=renavam | mod=modelo | anomodelo | ano
    chs=chassi | marca + #localiza_marca (...)
    tipoProp + nome_prop + #localiza_proprietario | tip=CAVALO|CARRETA|TRUCK
    alienado (opcional)
    cidade_proprietario + uf + #localiza_cidade | cor
    tipofrota=Carreteiro|Agregada|Frota Própria

  Informações Operacionais:
    capacidadeCarga | taraVeiculo   (CAVALO/CARRETA=27000, TRUCK=12000)
    qtdPallets=0 | qtdCestos=0 | cubagemVeiculo=0
    rastreador (opcional)
    baú 0/0/0 se vazio

Na aba operacional do motorista:
  #localiza_veiculo / #localiza_veiculo2 / #localiza_veiculo3 (Bi-Trem) / #localiza_veiculo4 (3º Reboque)
"""
from __future__ import annotations

import re

from playwright.sync_api import Page

from gw_automation.lookup import buscar_com_tres_pontinhos
from gw_automation.regras_veiculo import aplicar_cap_tara, normalizar_tipo_frota
from ocr.extrair_dados import DadosVeiculo, DadosProprietario

BTN_VEICULO = "#localiza_veiculo"
BTN_CARRETA = "#localiza_veiculo2"
CAMPO_VEI = "#vei_placa"
CAMPO_CAR = "#car_placa"


def garantir_veiculo(
    page: Page,
    dados: DadosVeiculo | None,
    *,
    label_campo: str = "Veículo",
    seletor_campo: str = CAMPO_VEI,
    seletor_botao: str = BTN_VEICULO,
    proprietario: DadosProprietario | None = None,
) -> bool:
    if not dados or not dados.placa:
        print(f"[Veículo] Sem placa ({label_campo}) - pulando.")
        return False

    print(
        f"[Veículo] Lookup {label_campo}: placa={dados.placa} "
        f"botao={seletor_botao} tipo={dados.tipo or '?'}"
    )

    def _novo(form: Page) -> None:
        print("[Veículo] Novo Cadastro - preenchimento COMPLETO (modelo print)...")
        preencher_form_veiculo_completo(form, dados, proprietario=proprietario)

    # Pesquisa placa -> se não achar (0 de 0), abre Novo Cadastro e vincula
    ok = buscar_com_tres_pontinhos(
        page,
        termo=dados.placa,
        label_campo=label_campo,
        seletor_campo=seletor_campo,
        seletor_botao=seletor_botao,
        filtro="Placa",
        preencher_novo=_novo,
    )

    # Sempre confere #vei_placa / #car_placa na aba do MOTORISTA
    page.wait_for_timeout(700)
    try:
        from gw_automation.lookup import _garantir_pagina_motorista_operacional

        page = _garantir_pagina_motorista_operacional(page)
    except Exception:
        pass

    val = _ler_placa_campo(page, seletor_campo)
    placa_ok = limpar_placa_cmp(dados.placa)
    if placa_ok and placa_ok in val.replace("-", ""):
        print(f"[Veículo] [OK] {label_campo} no campo: {val or dados.placa}")
        return True

    # 2ª/3ª: lookup COMPLETO de novo (com Novo Cadastro se 0 de 0).
    # NÃO usar só _reabrir_e_selecionar - ele NUNCA cria cadastro novo.
    print(
        f"[Veículo] [!] {label_campo}: campo {seletor_campo}={val!r} "
        f"sem placa {dados.placa} - lookup completo de novo (até 2x, com Novo Cadastro)..."
    )
    from gw_automation.lookup import (
        _reabrir_e_selecionar,
        _garantir_pagina_motorista_operacional,
        buscar_com_tres_pontinhos as _lookup_full,
    )

    for tentativa in range(1, 3):
        print(f"[Veículo] Tentativa {tentativa}/2 lookup+cadastro {dados.placa}...")
        page = _garantir_pagina_motorista_operacional(page)
        # fecha Localizar órfã aberta com 0 de 0
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
        page.wait_for_timeout(400)
        ok = _lookup_full(
            page,
            termo=dados.placa,
            label_campo=label_campo,
            seletor_campo=seletor_campo,
            seletor_botao=seletor_botao,
            filtro="Placa",
            preencher_novo=_novo,
        )
        page.wait_for_timeout(600)
        val = _ler_placa_campo(page, seletor_campo)
        if placa_ok and placa_ok in val.replace("-", ""):
            print(f"[Veículo] [OK] {label_campo} vinculado no motorista: {val}")
            return True

    # Último: só selecionar (caso alguém cadastrou manualmente no meio)
    print(f"[Veículo] Última tentativa: só selecionar {dados.placa} se já existir...")
    page = _garantir_pagina_motorista_operacional(page)
    _reabrir_e_selecionar(
        page,
        termo=dados.placa,
        label_campo=label_campo,
        seletor_campo=seletor_campo,
        seletor_botao=seletor_botao,
        filtro="Placa",
    )
    val = _ler_placa_campo(page, seletor_campo)
    if placa_ok and placa_ok in val.replace("-", ""):
        print(f"[Veículo] [OK] {label_campo} vinculado: {val}")
        return True

    print(
        f"[Veículo] [!] {label_campo} NÃO entrou em {seletor_campo} "
        f"(placa {dados.placa}). Confira se Novo Cadastro salvou e se a placa "
        f"bate na lista Localizar."
    )
    return False


def _ler_placa_campo(page: Page, seletor: str) -> str:
    try:
        return (page.input_value(seletor, timeout=2000) or "").strip().upper()
    except Exception:
        try:
            return (page.locator(seletor).first.input_value(timeout=1000) or "").strip().upper()
        except Exception:
            return ""


def limpar_placa_cmp(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (s or "")).upper()


def garantir_carreta(
    page: Page,
    dados: DadosVeiculo | None,
    proprietario: DadosProprietario | None = None,
    seletor_botao: str = BTN_CARRETA,
    seletor_campo: str = CAMPO_CAR,
) -> bool:
    return garantir_veiculo(
        page,
        dados,
        label_campo="Carreta",
        seletor_campo=seletor_campo,
        seletor_botao=seletor_botao,
        proprietario=proprietario,
    )


def preencher_form_veiculo_completo(
    page: Page,
    dados: DadosVeiculo,
    proprietario: DadosProprietario | None = None,
) -> None:
    """
    Preenche TODOS os campos do print de referência.

    Ordem (resiliente - lookup lento NÃO impede o resto):
      1) textos + selects (tipo, frota, cor, cap/tara)  <- SEMPRE primeiro
      2) marca (3 pontinhos)
      3) proprietário (3 pontinhos)
      4) cidade (3 pontinhos)
      5) re-aplica tipo/cap/tara se o GW limpou
    """
    # Prop embutido no CRLV tem prioridade sobre o prop “principal” do caso
    prop_doc = getattr(dados, "proprietario", None)
    if prop_doc and (prop_doc.nome or prop_doc.cpf_cnpj):
        proprietario = prop_doc

    dados.aplicar_regras_tipo()
    aplicar_cap_tara(dados)
    dados.tipo_frota = normalizar_tipo_frota(dados.tipo_frota)
    # Cidade do CRLV no veículo ↔ prop (sem cidade o GW não grava)
    if proprietario and proprietario.cidade and not (dados.cidade or "").strip():
        dados.sincronizar_cidade_proprietario(proprietario)
    if (dados.cidade or "").strip() and proprietario and not (proprietario.cidade or "").strip():
        proprietario.cidade = dados.cidade
        if dados.uf and not proprietario.uf:
            proprietario.uf = dados.uf
        print(
            f"  -> Cidade do CRLV no prop: {proprietario.cidade}/{proprietario.uf or '?'}"
        )

    mmv = limpar_marca_sem_especie(dados.texto_marca_modelo())
    if mmv:
        dados.marca_modelo_versao = mmv
        dados.marca = mmv
        dados.modelo = mmv
    dados.aplicar_marca_modelo_nos_tres_campos()
    aplicar_cap_tara(dados)  # de novo após tipo

    print(
        f"[Veículo] COMPLETO: placa={dados.placa} tipo={dados.tipo} "
        f"cap={dados.cap_carga} tara={dados.tara} cor={dados.cor} "
        f"marca={mmv or dados.marca or dados.modelo} "
        f"cidade={dados.cidade}/{dados.uf} "
        f"prop={getattr(proprietario, 'cpf_cnpj', None) or getattr(proprietario, 'nome', None) or '?'}"
    )

    # ========== 1) Campos simples (NÃO dependem de popup) ==========
    _select_name(page, "categoria", dados.categoria or "Veículo Terrestre")
    _fill_name(page, "pl", dados.placa)
    _fill_name(page, "numeroFrota", getattr(dados, "frota_numero", "") or "")
    _fill_name(page, "ren", dados.renavam)
    if mmv:
        _fill_name(page, "mod", mmv)
    _fill_name(page, "anomodelo", dados.ano_mod)
    _fill_name(page, "ano", dados.ano_fab or dados.ano_mod)
    _fill_name(page, "chs", dados.chassi)

    # Tipo ANTES dos lookups (evita ficar no default CARRETA do GW)
    if dados.tipo:
        if not _select_name(page, "tip", dados.tipo):
            # tenta value curto se o GW usar
            for v in (dados.tipo, dados.tipo[:1], dados.tipo.upper()):
                if _select_name(page, "tip", v):
                    break
            else:
                print(f"  [!] Tipo {dados.tipo!r} NÃO selecionado - confira o dropdown")

    if dados.cor:
        _select_name(page, "cor", dados.cor.upper())

    frota = normalizar_tipo_frota(dados.tipo_frota)
    ok_frota = False
    for lab in (frota, "Carreteiro", "Agregada", "Agregado", "Frota Própria"):
        if _select_name(page, "tipofrota", lab):
            ok_frota = True
            break
    if not ok_frota:
        print(f"  [!] Tipo frota {frota!r} não selecionado")

    # Cap/tara SEMPRE (fixos por tipo) - antes dos lookups
    _preencher_cap_tara(page, dados)
    _fill_name(page, "qtdPallets", "0")
    _fill_name(page, "qtdCestos", "0")
    _fill_name(page, "cubagemVeiculo", "0")
    _fill_name(page, "altura_carroceria", "0")
    _fill_name(page, "largura_carroceria", "0")
    _fill_name(page, "comprimento_carroceria", "0")

    # ========== 2) Marca (lookup - pode falhar sem travar o resto) ==========
    if mmv:
        print(
            f"  -> Marca/Modelo: '{mmv}' (pesquisar -> se não, cadastrar)"
        )
        try:
            _lookup_marca(page, mmv)
            # Garante *Marca (topo) - se vazio, tenta de novo
            if not _campo_texto_preenchido(page, 'input[name="marca"]'):
                print("  [!] *Marca (topo) ainda vazia - 2ª tentativa lookup...")
                _lookup_marca(page, mmv)
            try:
                val = page.input_value('input[name="marca"]', timeout=1500) or ""
            except Exception:
                val = ""
            if not val.strip():
                val = mmv
                print(f"  [!] *Marca topo vazia após lookup - marca inferior com {val!r}")
            else:
                print(f"  [OK] *Marca (topo) = {val!r}")
            _preencher_marca_inferior(page, val)
            # se inferior ok e topo ainda vazio, tenta 3ª com texto do inferior
            if not _campo_texto_preenchido(page, 'input[name="marca"]'):
                try:
                    inf = page.input_value('input[name="marca_rastreador"]', timeout=800) or ""
                except Exception:
                    inf = ""
                if inf.strip():
                    print(f"  -> 3ª tentativa *Marca com texto do rastreador: {inf!r}")
                    _lookup_marca(page, inf.strip())
        except Exception as e:
            print(f"  [!] Marca lookup falhou (segue prop/cidade): {e}")
    else:
        print("  [!] Sem texto de marca no doc - preencha *Marca manualmente se o GW exigir")

    # Re-aplica tipo/cap se o form resetou ao voltar do lookup
    _reaplicar_campos_criticos(page, dados)

    # ========== 3) Proprietário ==========
    ok_prop = False
    cidade_ja_preenchida = False

    if proprietario and (proprietario.nome or proprietario.cpf_cnpj):
        dig = "".join(c for c in (proprietario.cpf_cnpj or "") if c.isdigit())
        filtro = "CPF" if len(dig) == 11 else ("CNPJ" if len(dig) == 14 else "Nome")
        termo = dig or proprietario.nome
        print(
            f"  -> Proprietário: pesquisar {filtro}={termo!r} "
            f"nome={proprietario.nome!r} (se não achar -> Novo Cadastro)"
        )

        def _novo_prop(form: Page) -> None:
            # Garante cidade do CRLV no prop ANTES de preencher o form
            if not (proprietario.cidade or "").strip() and (dados.cidade or "").strip():
                proprietario.cidade = dados.cidade
                proprietario.uf = proprietario.uf or dados.uf or ""
                print(
                    f"  -> Cidade do CRLV copiada p/ prop: "
                    f"{proprietario.cidade}/{proprietario.uf or '?'}"
                )
            # Nome: se prop vazio, tenta proprietario_nome do veículo / CRLV
            if not (proprietario.nome or "").strip():
                fallback = (
                    getattr(dados, "proprietario_nome", None)
                    or getattr(proprietario, "nome", None)
                    or ""
                )
                if not fallback and proprietario.cpf_cnpj:
                    # mesmo CPF do motorista? o caller pode ter setado só o doc
                    pass
                if fallback:
                    proprietario.nome = str(fallback).strip()
                    print(f"  -> Nome do prop preenchido do CRLV: {proprietario.nome!r}")
            print(
                f"  -> Preenchendo form prop: nome={proprietario.nome!r} "
                f"doc={proprietario.cpf_cnpj!r}"
            )
            _preencher_prop_callback(form, proprietario)

        try:
            ok_prop = buscar_com_tres_pontinhos(
                page,
                termo=termo,
                label_campo="Proprietário",
                seletor_botao="#localiza_proprietario",
                seletor_campo='input[name="nome_prop"]',
                filtro=filtro,
                preencher_novo=_novo_prop,
            )
            if not ok_prop and dig and len(dig) == 14 and (proprietario.nome or "").strip():
                print(f"  -> CNPJ sem hit - tenta Nome={proprietario.nome!r}")
                ok_prop = buscar_com_tres_pontinhos(
                    page,
                    termo=proprietario.nome.strip(),
                    label_campo="Proprietário",
                    seletor_botao="#localiza_proprietario",
                    seletor_campo='input[name="nome_prop"]',
                    filtro="Nome",
                    preencher_novo=_novo_prop,
                )
        except Exception as e:
            print(f"  [!] Lookup proprietário falhou: {e}")
            ok_prop = False
        if not ok_prop:
            print("  [!] Proprietário não vinculado (não achou e/ou dry-run sem gravar)")
    else:
        print("  [!] Sem dados de proprietário para pesquisar")

    _reaplicar_campos_criticos(page, dados)

    if ok_prop:
        page.wait_for_timeout(500)
        cidade_ja_preenchida = _cidade_veiculo_preenchida(page)
        if cidade_ja_preenchida:
            try:
                nome_p = page.input_value('input[name="nome_prop"]', timeout=1000)
                cid_p = page.input_value('input[name="cidade_proprietario"]', timeout=1000)
                uf_p = page.input_value('input[name="uf_proprietario"]', timeout=1000)
            except Exception:
                nome_p = cid_p = uf_p = "?"
            print(
                f"  [OK] Prop={nome_p!r} | Cidade do prop={cid_p!r}/{uf_p!r} "
                f"- sem lookup de cidade"
            )
        else:
            print("  [!] Prop OK mas cidade vazia - lookup de cidade")

    # ========== 4) Cidade ==========
    if not cidade_ja_preenchida:
        cidade = (dados.cidade or "").strip()
        uf = (dados.uf or "").strip()
        if not cidade and proprietario:
            cidade = (proprietario.cidade or "").strip()
            uf = uf or (proprietario.uf or "").strip()
        if cidade:
            print(f"  -> Cidade (CRLV/prop): pesquisar {cidade}/{uf or '?'}")
            try:
                ok_cid = buscar_com_tres_pontinhos(
                    page,
                    termo=cidade,
                    label_campo="Cidade",
                    seletor_botao="#localiza_cidade",
                    seletor_campo='input[name="cidade_proprietario"]',
                    filtro="Cidade",
                    uf_preferida=uf or "GO",
                    match_exato=True,
                    preencher_novo=None,
                )
            except Exception as e:
                print(f"  [!] Lookup cidade falhou: {e}")
                ok_cid = False
            if not ok_cid:
                print(
                    f"  [!] Cidade {cidade}/{uf} NÃO vinculada no veículo - "
                    f"o GW pode recusar salvar"
                )
        else:
            print(
                "  [!] Cidade vazia (nem CRLV nem prop) - "
                "o GW provavelmente NÃO salva o veículo"
            )

    # ========== 5) Passo final: nada crítico vazio ==========
    _reaplicar_campos_criticos(page, dados)
    _relatar_campos_faltando(page, dados, mmv or "")


def _campo_texto_preenchido(page: Page, seletor: str) -> bool:
    try:
        val = (page.input_value(seletor, timeout=800) or "").strip()
        return len(val) > 1
    except Exception:
        return False


def _preencher_cap_tara(page: Page, dados: DadosVeiculo) -> None:
    aplicar_cap_tara(dados)
    cap = (dados.cap_carga or "").strip() or "27000"
    tara = (dados.tara or "").strip() or "27000"
    if (dados.tipo or "").upper() == "TRUCK":
        cap = cap if cap not in ("0", "0.0") else "12000"
        tara = tara if tara not in ("0", "0.0") else "12000"
    _fill_name(page, "capacidadeCarga", cap)
    _fill_name(page, "taraVeiculo", tara)


def _reaplicar_campos_criticos(page: Page, dados: DadosVeiculo) -> None:
    """Depois de popups, o GW às vezes reseta tipo/cap/tara - reaplica."""
    try:
        if dados.tipo:
            atual = ""
            try:
                atual = (
                    page.locator('select[name="tip"]').first.evaluate(
                        "e => e.options[e.selectedIndex]?.text || e.value || ''"
                    )
                    or ""
                )
            except Exception:
                pass
            if (dados.tipo or "").upper() not in (atual or "").upper():
                _select_name(page, "tip", dados.tipo)
        # cap/tara zerados -> preenche de novo
        for name, attr, default in (
            ("capacidadeCarga", "cap_carga", "27000"),
            ("taraVeiculo", "tara", "27000"),
        ):
            try:
                val = (page.input_value(f'input[name="{name}"]', timeout=800) or "").strip()
            except Exception:
                val = ""
            dig = re.sub(r"[^\d]", "", val)
            if not dig or dig in ("0", "00"):
                alvo = (getattr(dados, attr, None) or default).strip()
                _fill_name(page, name, alvo)
        frota = normalizar_tipo_frota(dados.tipo_frota)
        try:
            ft = (
                page.locator('select[name="tipofrota"]').first.evaluate(
                    "e => e.options[e.selectedIndex]?.text || ''"
                )
                or ""
            )
            if frota.lower() not in (ft or "").lower() and "agreg" not in frota.lower():
                # se deveria ser Carreteiro e ficou Agregada sem motivo, corrige
                if "carret" in frota.lower() and "agreg" in (ft or "").lower():
                    _select_name(page, "tipofrota", frota)
        except Exception:
            pass
    except Exception as e:
        print(f"  [!] reaplicar críticos: {e}")


def _relatar_campos_faltando(page: Page, dados: DadosVeiculo, mmv: str) -> None:
    """Log final do que ainda está vazio no form de veículo."""
    faltas = []
    checks = [
        ("pl", "placa"),
        ("marca", "marca"),
        ("nome_prop", "proprietário"),
        ("cidade_proprietario", "cidade"),
        ("capacidadeCarga", "cap. carga"),
        ("taraVeiculo", "tara"),
    ]
    for name, rotulo in checks:
        try:
            val = (page.input_value(f'input[name="{name}"]', timeout=600) or "").strip()
        except Exception:
            val = ""
        dig = re.sub(r"[^\dA-Za-z]", "", val)
        if not dig or dig in ("0", "00", "0.0"):
            faltas.append(rotulo)
    try:
        tip = page.locator('select[name="tip"]').first.evaluate(
            "e => e.options[e.selectedIndex]?.text || ''"
        )
        if dados.tipo and (dados.tipo or "").upper() not in (tip or "").upper():
            faltas.append(f"tipo(≠{dados.tipo})")
    except Exception:
        pass
    if faltas:
        print(f"  [!] Form veículo AINDA incompleto: {', '.join(faltas)}")
        if mmv and "marca" in faltas:
            print(f"     -> marque manualmente: {mmv}")
        if dados.cidade and "cidade" in faltas:
            print(f"     -> cidade: {dados.cidade}/{dados.uf or '?'}")
    else:
        print("  [OK] Form veículo: campos críticos preenchidos")


def _preencher_prop_callback(form: Page, prop: DadosProprietario) -> None:
    from gw_automation.proprietario import _preencher_form_proprietario

    _preencher_form_proprietario(form, prop)


def limpar_marca_sem_especie(texto: str) -> str:
    """Tira espécie (TRACAO...) e troca / por espaço -> M.BENZ AXOR 2536 LS."""
    try:
        from ocr.parsers_locais import _limpar_marca_sem_especie

        return _limpar_marca_sem_especie(texto or "")
    except Exception:
        t = (texto or "").replace("/", " ")
        t = re.sub(r"\s+", " ", t.strip())
        t = re.split(
            r"\b(?:TRACAO|TRAÇÃO|TRATOR|SEMI|REBOQUE|CARGA|PASSAGEIRO|CAMINHAO)\b",
            t,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" -")
        return t


def limitar_descricao_marca(texto: str, max_len: int | None = None) -> str:
    """
    1) Remove espécie misturada (TRACAO etc.)
    2) Respeita limite de *Descrição do GW (padrão 25).
    """
    t = limpar_marca_sem_especie(texto)
    t = re.sub(r"\s+", " ", (t or "").strip())
    if not t:
        return ""
    limite = max_len if max_len and max_len > 0 else int(
        __import__("os").getenv("MARCA_DESC_MAX", "25") or "25"
    )
    if len(t) <= limite:
        return t
    cortado = t[:limite].rstrip()
    print(f"  [Marca] Descrição limitada a {limite} chars: {t!r} -> {cortado!r}")
    return cortado


def _maxlength_descricao_marca(form: Page) -> int | None:
    """Lê maxlength do input Descrição no cadmarca."""
    for seletor in (
        'input[name*="descricao" i]',
        "#descricao",
        'input[name="descricao"]',
        'tr:has-text("Descrição") input[type="text"]',
        'input[type="text"]:visible',
    ):
        try:
            loc = form.locator(seletor).first
            if not loc.count() or not loc.is_visible():
                continue
            ml = loc.get_attribute("maxlength")
            if ml and str(ml).isdigit() and int(ml) > 0:
                return int(ml)
            # fallback: size do input
            sz = loc.evaluate(
                """e => {
                    if (e.maxLength && e.maxLength > 0 && e.maxLength < 500) return e.maxLength;
                    return e.size || 0;
                }"""
            )
            if isinstance(sz, int) and 5 <= sz <= 80:
                return sz
        except Exception:
            continue
    return None


def _preencher_descricao_marca_nova(form: Page, marca: str) -> str:
    """Preenche *Descrição no Novo Cadastro de marca, respeitando limite."""
    limite = _maxlength_descricao_marca(form)
    texto = limitar_descricao_marca(marca, limite)
    for seletor in (
        'input[name*="descricao" i]',
        "#descricao",
        'input[name="descricao"]',
        'input[name*="nome"]',
        'tr:has-text("Descrição") input',
        'input[type="text"]:visible',
    ):
        try:
            loc = form.locator(seletor).first
            if loc.count() and loc.is_visible():
                loc.fill("", timeout=1000)
                loc.fill(texto, timeout=2000)
                # confere se o campo engoliu o fim
                try:
                    val = (loc.input_value(timeout=800) or "").strip()
                    if val and val != texto and len(val) < len(texto):
                        print(f"  [Marca] Campo aceitou só {len(val)} chars: {val!r}")
                        texto = val
                except Exception:
                    pass
                print(f"  [OK] marca Descrição = {texto!r} (max={limite or '?'})")
                return texto
        except Exception:
            continue
    print(f"  [!] não preencheu Descrição da marca: {texto!r}")
    return texto


def _lookup_marca(page: Page, marca: str) -> None:
    """1º *Marca - pesquisa; se não existir, Novo Cadastro (respeita limite de chars)."""
    # pesquisa com texto completo e, se longo, também versão limitada
    termo = (marca or "").strip()
    termo_lim = limitar_descricao_marca(termo)
    print(f"  -> [1/3] Marca (topo) lookup+cadastro: {termo!r}")

    def _novo(form: Page) -> None:
        _preencher_descricao_marca_nova(form, termo)

    ok = buscar_com_tres_pontinhos(
        page,
        termo=termo_lim if len(termo) > len(termo_lim) else termo,
        label_campo="Marca",
        seletor_botao="#localiza_marca",
        seletor_campo='input[name="marca"]',
        filtro="Descrição",
        preencher_novo=_novo,
    )
    # se não achou com texto cortado, tenta termo original (marca já cadastrada longa)
    if not ok and termo != termo_lim:
        ok = buscar_com_tres_pontinhos(
            page,
            termo=termo,
            label_campo="Marca",
            seletor_botao="#localiza_marca",
            seletor_campo='input[name="marca"]',
            filtro="Descrição",
            preencher_novo=_novo,
        )
    if not ok:
        print(f"  [!] Marca topo '{termo}' não vinculada")


def _lookup_marca_somente_existente(page: Page, marca: str) -> bool:
    """
    DRY-RUN: pesquisa a marca; se achar, seleciona.
    Se não achar, NÃO abre Novo Cadastro (não pode registrar no teste).
    """
    print(f"  -> [1/3] Marca (topo) só se já existir: {marca}")
    return buscar_com_tres_pontinhos(
        page,
        termo=marca,
        label_campo="Marca",
        seletor_botao="#localiza_marca",
        seletor_campo='input[name="marca"]',
        filtro="Descrição",
        preencher_novo=None,  # impede cadastro novo
    )


def _preencher_marca_inferior(page: Page, marca: str = "") -> None:
    """
    Marca ao lado do Rastreador (readonly) - pesquisa a MESMA marca.
    Cadastro novo usa o mesmo limite de caracteres da Descrição.
    """
    if not (marca or "").strip():
        print("  [!] Marca rastreador sem termo - pulando")
        return

    termo = (marca or "").strip()
    termo_lim = limitar_descricao_marca(termo)

    def _novo(form: Page) -> None:
        _preencher_descricao_marca_nova(form, termo)

    print(f"  -> [3/3] Marca rastreador: pesquisar {termo_lim!r} -> se não, cadastrar")
    ok = buscar_com_tres_pontinhos(
        page,
        termo=termo_lim,
        label_campo="Marca rastreador",
        seletor_botao="#localiza_marca2",
        seletor_campo='input[name="marca_rastreador"]',
        filtro="Descrição",
        pegar_primeiro=False,
        preencher_novo=_novo,
    )
    if ok:
        try:
            val = page.input_value('input[name="marca_rastreador"]', timeout=1500)
            print(f"  [OK] marca_rastreador = {val!r}")
        except Exception:
            print("  [OK] marca_rastreador vinculada")
        return
    print("  [!] Marca (Rastreador) não vinculada")


# compat
def garantir_marca(page: Page, marca: str) -> bool:
    _lookup_marca(page, marca)
    return True


def _cidade_veiculo_preenchida(page: Page) -> bool:
    """True se *Cidade do form de veículo já tem valor (veio do proprietário)."""
    for seletor in (
        'input[name="cidade_proprietario"]',
        "#cidade_proprietario",
        'input[name="cidade"]',
    ):
        try:
            loc = page.locator(seletor).first
            if loc.count() == 0:
                continue
            val = (loc.input_value(timeout=1000) or "").strip()
            if val:
                return True
        except Exception:
            continue
    return False


def _fill_name(page: Page, name: str, valor: str) -> bool:
    if valor is None or str(valor) == "":
        return False
    for seletor in (f'input[name="{name}"]', f"#{name}", f'select[name="{name}"]'):
        try:
            loc = page.locator(seletor).first
            if loc.count() == 0:
                continue
            tag = loc.evaluate("e => e.tagName.toLowerCase()")
            if tag == "select":
                page.select_option(seletor, label=str(valor), timeout=2000)
            else:
                loc.fill(str(valor), timeout=2000, force=True)
            print(f"  [OK] {name} = {valor}")
            return True
        except Exception:
            try:
                if page.locator(f'select[name="{name}"]').count():
                    page.select_option(f'select[name="{name}"]', value=str(valor), timeout=1000)
                    print(f"  [OK] {name} value={valor}")
                    return True
            except Exception:
                continue
    print(f"  [!] não preencheu {name}={valor}")
    return False


def _select_name(page: Page, name: str, label: str) -> bool:
    if not label:
        return False
    seletor = f'select[name="{name}"]'
    label = str(label).strip()
    tentativas = (
        label,
        label.upper(),
        label.capitalize(),
        label.title(),
    )
    for tentativa in tentativas:
        try:
            page.select_option(seletor, label=tentativa, timeout=1500)
            print(f"  [OK] select {name} = {tentativa}")
            return True
        except Exception:
            try:
                page.select_option(seletor, value=tentativa, timeout=800)
                print(f"  [OK] select {name} value={tentativa}")
                return True
            except Exception:
                continue
    # Match parcial nas options (ex.: "CAVALO " / "1-CAVALO")
    try:
        loc = page.locator(seletor).first
        opts = loc.evaluate(
            """e => Array.from(e.options).map(o => ({v: o.value, t: (o.text||'').trim()}))"""
        )
        alvo = label.upper()
        for o in opts or []:
            t = (o.get("t") or "").upper()
            v = (o.get("v") or "").upper()
            if alvo == t or alvo == v or alvo in t or t in alvo:
                try:
                    page.select_option(seletor, label=o.get("t"), timeout=1200)
                    print(f"  [OK] select {name} = {o.get('t')!r} (parcial)")
                    return True
                except Exception:
                    try:
                        page.select_option(seletor, value=o.get("v"), timeout=800)
                        print(f"  [OK] select {name} value={o.get('v')!r}")
                        return True
                    except Exception:
                        continue
    except Exception:
        pass
    print(f"  [!] select {name}={label!r} falhou")
    return False
