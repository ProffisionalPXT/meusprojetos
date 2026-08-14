"""
Confirmação humana dos dados extraídos ANTES de preencher o GW.

Uso no terminal:
  ENTER        -> confirma e segue
  n / nao      -> cancela o caso
  e <num>      -> edita campo pelo número
  e campo=val  -> edita por nome (ex: e cpf=12345678901)
  m            -> mostra resumo de novo
  q            -> cancela tudo

Env:
  CONFIRMAR_DADOS=1  (padrão) - pede confirmação
  CONFIRMAR_DADOS=0  - pula (só automação)
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ocr.extrair_dados import (
    DadosCaso,
    DadosMotorista,
    DadosProprietario,
    DadosVeiculo,
)


def confirmar_ativo() -> bool:
    v = (os.getenv("CONFIRMAR_DADOS", "1") or "1").strip().lower()
    return v not in ("0", "false", "nao", "não", "no", "off")


def confirmar_dados_caso(dados: DadosCaso) -> Optional[DadosCaso]:
    """
    Mostra resumo editável. Retorna dados (possivelmente editados) ou None se cancelar.
    """
    if not confirmar_ativo():
        print("[Confirmar] CONFIRMAR_DADOS=0 - seguindo sem revisão humana.")
        return dados

    if not sys.stdin.isatty():
        print(
            "[Confirmar] [!] Sem terminal interativo - salvando JSON em "
            "output/para_confirmar/ e seguindo com os dados atuais."
        )
        _salvar_snapshot(dados, pasta="para_confirmar")
        return dados

    itens = _lista_campos(dados)
    while True:
        _imprimir_tabela(dados.caso_nome, itens)
        _imprimir_avisos_ocr(dados)
        _imprimir_plano_gw(dados)
        print(
            "\n  ┌─────────────────────────────────────────────────┐\n"
            "  │  Os dados estão corretos?                       │\n"
            "  │                                                 │\n"
            "  │  ENTER  ->  sim, pode preencher o GW             │\n"
            "  │  n      ->  cancelar este motorista              │\n"
            "  │  5      ->  corrigir o campo número 5            │\n"
            "  │  e cpf=123...  ->  corrigir por nome do campo    │\n"
            "  │  (se houver [!] OCR, confira placa/renavam/chassi)│\n"
            "  └─────────────────────────────────────────────────┘"
        )
        try:
            cmd = input("\n  Sua resposta: ").strip()
        except EOFError:
            print("[Confirmar] Cancelado.")
            return None

        if cmd == "" or cmd.lower() in ("s", "sim", "ok", "c", "confirmar", "y", "yes"):
            _salvar_snapshot(dados, pasta="confirmados")
            _reaplicar_regras(dados)
            print("\n  [OK] Confirmado. Iniciando preenchimento no GW...\n")
            return dados

        low = cmd.lower()
        if low in ("n", "nao", "não", "cancelar", "q", "quit"):
            print("  Caso cancelado.")
            return None

        if low in ("m", "mostrar", "l", "listar"):
            continue

        if low.startswith("e ") or low.startswith("edit "):
            resto = cmd.split(None, 1)[1] if " " in cmd else ""
            if not _aplicar_edicao(dados, itens, resto):
                print("  [!] Ex.: e 3   ou   e cpf=12345678901")
            itens = _lista_campos(dados)
            continue

        # número sozinho = corrigir esse campo
        if cmd.isdigit():
            n = int(cmd)
            if 1 <= n <= len(itens):
                secao, chave, atual = itens[n - 1]
                print(f"  Campo {n}: {secao}.{chave}")
                print(f"  Valor atual: {atual or '(vazio)'}")
                try:
                    novo = input("  Novo valor (ENTER mantém): ").strip()
                except EOFError:
                    continue
                if novo:
                    _set_campo(dados, secao, chave, novo)
                    print(f"  [OK] Atualizado: {novo!r}")
                itens = _lista_campos(dados)
            else:
                print(f"  [!] Use um número entre 1 e {len(itens)}")
            continue

        print("  [!] Digite ENTER (ok), n (cancelar) ou o número do campo para corrigir.")


def _lista_campos(dados: DadosCaso) -> List[Tuple[str, str, str]]:
    """
    Só campos que o bot preenche de fato (testados).
    Fora da lista: apelido, telefone, e-mail, escolaridade, etc.
    """
    itens: List[Tuple[str, str, str]] = []

    m = dados.motorista
    # Dados pessoais + documentação + tipo operacional (testados)
    for k in (
        "cpf",
        "nome",
        "cep",
        "endereco",
        "bairro",
        "complemento",
        "cidade",
        "uf",
        "data_nascimento",
        "naturalidade",
        "nacionalidade",
        "sexo",
        "nome_pai",
        "nome_mae",
        "rg",
        "orgao_emissor",
        "cnh",
        "categoria_cnh",
        "validade_cnh",
        "data_emissao_cnh",
        "local_emissao_cnh",
        "data_primeira_habilitacao",
        "tipo_motorista",
    ):
        itens.append(("motorista", k, str(getattr(m, k, "") or "")))

    campos_veiculo = (
        "placa",
        "renavam",
        "chassi",
        "marca_modelo_versao",
        "ano_fab",
        "ano_mod",
        "cor",
        "tipo",
        "tipo_frota",
        "cap_carga",
        "tara",
        "cidade",
        "uf",
    )
    campos_reboque = (
        "placa",
        "renavam",
        "chassi",
        "marca_modelo_versao",
        "ano_fab",
        "ano_mod",
        "cor",
        "tipo",
        "cap_carga",
        "tara",
    )

    if dados.veiculo:
        for k in campos_veiculo:
            itens.append(("veiculo", k, str(getattr(dados.veiculo, k, "") or "")))

    if dados.carreta:
        for k in campos_reboque:
            itens.append(("carreta", k, str(getattr(dados.carreta, k, "") or "")))

    if dados.bitrem:
        for k in campos_reboque:
            itens.append(("bitrem", k, str(getattr(dados.bitrem, k, "") or "")))

    if dados.tri_reboque:
        for k in campos_reboque:
            itens.append(
                ("tri_reboque", k, str(getattr(dados.tri_reboque, k, "") or ""))
            )

    if dados.proprietario:
        p = dados.proprietario
        for k in ("nome", "cpf_cnpj", "tipo_doc", "cidade", "uf", "rntrc"):
            itens.append(("proprietario", k, str(getattr(p, k, "") or "")))

    # Props extras quando diferem do principal / cavalo
    pv = getattr(dados.veiculo, "proprietario", None) if dados.veiculo else None
    d_principal = "".join(
        c for c in ((pv.cpf_cnpj if pv else "") or "") if c.isdigit()
    )
    for secao, v in (
        ("prop_carreta", dados.carreta),
        ("prop_bitrem", dados.bitrem),
        ("prop_tri_reboque", dados.tri_reboque),
    ):
        if not v:
            continue
        pc = getattr(v, "proprietario", None)
        if not pc:
            continue
        d2 = "".join(c for c in (pc.cpf_cnpj or "") if c.isdigit())
        if d_principal and d2 and d_principal != d2:
            for k in ("nome", "cpf_cnpj", "cidade", "uf", "rntrc"):
                itens.append((secao, k, str(getattr(pc, k, "") or "")))

    if dados.rntrc_tac:
        itens.append(("caso", "rntrc_tac", str(dados.rntrc_tac or "")))
    return itens


def _imprimir_tabela(caso_nome: str, itens: List[Tuple[str, str, str]]) -> None:
    print(f"\n{'='*60}")
    print(f" CONFIRME TODOS OS DADOS ANTES DO GW - caso: {caso_nome}")
    print(f"{'='*60}")
    secao_atual = ""
    for i, (secao, chave, val) in enumerate(itens, 1):
        if secao != secao_atual:
            secao_atual = secao
            print(f"\n  [{secao.upper()}]")
        marca = " " if val else "·"
        vshow = val if val else "(vazio)"
        if len(vshow) > 50:
            vshow = vshow[:47] + "..."
        # destaca placa/renavam/chassi (mais sensíveis a OCR de foto ruim)
        crit = chave in ("placa", "renavam", "chassi")
        flag = " [!]OCR" if crit and val else ""
        print(f"  {i:3d}. {marca} {chave:<28} {vshow}{flag}")
    vazios = sum(1 for *_, v in itens if not v)
    print(f"\n  Campos vazios: {vazios}/{len(itens)}  (· = vazio - corrija se for obrigatório)")
    print("  ([!]OCR = confira no documento - foto ruim troca B/H, 0/O, Z/2)")


def _imprimir_avisos_ocr(dados: DadosCaso) -> None:
    """Mostra o que o OCR marcou como duvidoso / possivelmente incorreto."""
    avisos = list(getattr(dados, "avisos_ocr", None) or [])
    # reforço: se placa/renavam/chassi preenchidos, lembrar de checar
    criticos_preenchidos = []
    for secao, v in dados.veiculos_composicao():
        if not v:
            continue
        for k in ("placa", "renavam", "chassi"):
            if getattr(v, k, None):
                criticos_preenchidos.append(f"{secao}.{k}={getattr(v, k)}")

    if not avisos and not criticos_preenchidos:
        return

    print(f"\n{'─'*60}")
    print(" [!]  CAMPOS QUE PODEM ESTAR INCORRETOS (OCR)")
    print(f"{'─'*60}")
    if avisos:
        print("  Avisos automáticos da leitura:")
        for a in avisos[:25]:
            print(f"    · {a}")
        if len(avisos) > 25:
            print(f"    · ... +{len(avisos) - 25} aviso(s)")
    else:
        print("  Nenhum alerta forte, mas sempre confira no documento:")
    if criticos_preenchidos:
        print("  Valores críticos extraídos (compare com a foto/PDF):")
        for c in criticos_preenchidos:
            print(f"    -> {c}")
    print("  Se algum estiver errado: digite o NÚMERO do campo e corrija.")
    print(f"{'─'*60}")


def _imprimir_plano_gw(dados: DadosCaso) -> None:
    """Mostra o que o robô fará nos 3 pontinhos (sempre pesquisa primeiro)."""
    print(f"\n{'─'*60}")
    print(" PLANO NO GW (sempre PESQUISA antes de cadastrar novo)")
    print(f"{'─'*60}")
    m = dados.motorista
    print(
        f"  1. Motorista CPF {m.cpf or '?'} - pessoais+docs -> SALVA "
        f"(se já existe, Editar; se não, Novo)"
    )
    print(
        f"  1b. Após salvar: continua no mesmo form -> veículos "
        f"(não pesquisa CPF de novo)"
    )
    if dados.veiculo and dados.veiculo.placa:
        print(
            f"  2. Veículo placa {dados.veiculo.placa} - ... Localizar: "
            f"se achar VINCULA; se não, Novo Cadastro do veículo"
        )
        mmv = dados.veiculo.texto_marca_modelo()
        if mmv:
            print(f"     · Marca '{mmv}' - pesquisa; se não, cadastra marca")
    else:
        print("  2. Veículo - sem placa")
    n_plano = 3
    if dados.carreta and dados.carreta.placa:
        print(
            f"  {n_plano}. Carreta placa {dados.carreta.placa} - mesma regra (pesquisa -> ou cria)"
        )
        n_plano += 1
    if dados.bitrem and dados.bitrem.placa:
        print(
            f"  {n_plano}. Bi-Trem placa {dados.bitrem.placa} - "
            f"#localiza_veiculo3 (pesquisa -> ou cria)"
        )
        n_plano += 1
    if dados.tri_reboque and dados.tri_reboque.placa:
        print(
            f"  {n_plano}. 3º Reboque placa {dados.tri_reboque.placa} - "
            f"#localiza_veiculo4 (pesquisa -> ou cria)"
        )
        n_plano += 1
    if dados.veiculo and getattr(dados.veiculo, "proprietario", None):
        p = dados.veiculo.proprietario
        dig = "".join(c for c in (p.cpf_cnpj or "") if c.isdigit())
        tipo = "CNPJ" if len(dig) == 14 else ("CPF" if len(dig) == 11 else "Nome")
        print(
            f"  {n_plano}. Prop do CAVALO {tipo} {p.cpf_cnpj or p.nome or '?'} - "
            f"pesquisa; se não, Novo Cadastro"
        )
        n_plano += 1
    elif dados.proprietario:
        p = dados.proprietario
        dig = "".join(c for c in (p.cpf_cnpj or "") if c.isdigit())
        tipo = "CNPJ" if len(dig) == 14 else ("CPF" if len(dig) == 11 else "Nome")
        print(
            f"  {n_plano}. Proprietário {tipo} {p.cpf_cnpj or p.nome or '?'} - "
            f"pesquisa; se não, Novo Cadastro"
        )
        n_plano += 1
    for rotulo, v in (
        ("CARRETA", dados.carreta),
        ("Bi-Trem", dados.bitrem),
        ("3º Reboque", dados.tri_reboque),
    ):
        if not v or not getattr(v, "proprietario", None):
            continue
        p = v.proprietario
        dig = "".join(c for c in (p.cpf_cnpj or "") if c.isdigit())
        tipo = "CNPJ" if len(dig) == 14 else ("CPF" if len(dig) == 11 else "Nome")
        print(
            f"  {n_plano}. Prop da {rotulo} {tipo} {p.cpf_cnpj or p.nome or '?'} - "
            f"(pode ser o mesmo ou outro)"
        )
        n_plano += 1
    if dados.rntrc_tac:
        print(f"  {n_plano}. RNTRC/TAC {dados.rntrc_tac} nos proprietários (se faltar)")
    print(
        "\n  Se o GW disser 'já cadastrado' (CPF/placa), o robô avisa e NÃO força duplicar."
    )
    print(f"{'─'*60}")


def _aplicar_edicao(dados: DadosCaso, itens: List[Tuple[str, str, str]], resto: str) -> bool:
    resto = (resto or "").strip()
    if not resto:
        return False

    # e 3  -> pede valor
    if resto.isdigit():
        n = int(resto)
        if not (1 <= n <= len(itens)):
            return False
        secao, chave, _ = itens[n - 1]
        try:
            novo = input(f"  Novo valor para {secao}.{chave}: ").strip()
        except EOFError:
            return False
        _set_campo(dados, secao, chave, novo)
        print(f"  [OK] {secao}.{chave} = {novo!r}")
        return True

    # e 3=valor  ou  e cpf=valor  ou  e motorista.cpf=valor
    if "=" in resto:
        esq, val = resto.split("=", 1)
        esq, val = esq.strip(), val.strip()
        if esq.isdigit():
            n = int(esq)
            if not (1 <= n <= len(itens)):
                return False
            secao, chave, _ = itens[n - 1]
            _set_campo(dados, secao, chave, val)
            print(f"  [OK] {secao}.{chave} = {val!r}")
            return True
        if "." in esq:
            secao, chave = esq.split(".", 1)
            _set_campo(dados, secao.strip(), chave.strip(), val)
            print(f"  [OK] {secao.strip()}.{chave.strip()} = {val!r}")
            return True
        # procura chave em qualquer seção (primeira)
        for secao, chave, _ in itens:
            if chave.lower() == esq.lower():
                _set_campo(dados, secao, chave, val)
                print(f"  [OK] {secao}.{chave} = {val!r}")
                return True
        print(f"  [!] Campo '{esq}' não encontrado")
        return False

    return False


def _set_campo(dados: DadosCaso, secao: str, chave: str, valor: str) -> None:
    secao = secao.lower().strip()
    chave = chave.strip()
    if secao == "caso" and chave == "rntrc_tac":
        dados.rntrc_tac = valor
        if dados.proprietario and valor:
            dados.proprietario.rntrc = valor
        return
    obj = None
    if secao == "motorista":
        obj = dados.motorista
    elif secao == "veiculo":
        if dados.veiculo is None:
            dados.veiculo = DadosVeiculo()
        obj = dados.veiculo
    elif secao == "carreta":
        if dados.carreta is None:
            dados.carreta = DadosVeiculo()
        obj = dados.carreta
    elif secao == "bitrem":
        if dados.bitrem is None:
            dados.bitrem = DadosVeiculo(tipo="CARRETA")
        obj = dados.bitrem
    elif secao == "tri_reboque":
        if dados.tri_reboque is None:
            dados.tri_reboque = DadosVeiculo(tipo="CARRETA")
        obj = dados.tri_reboque
    elif secao == "proprietario":
        if dados.proprietario is None:
            dados.proprietario = DadosProprietario()
        obj = dados.proprietario
    elif secao == "prop_carreta":
        if dados.carreta is None:
            dados.carreta = DadosVeiculo()
        if dados.carreta.proprietario is None:
            dados.carreta.proprietario = DadosProprietario()
        obj = dados.carreta.proprietario
    elif secao == "prop_bitrem":
        if dados.bitrem is None:
            dados.bitrem = DadosVeiculo(tipo="CARRETA")
        if dados.bitrem.proprietario is None:
            dados.bitrem.proprietario = DadosProprietario()
        obj = dados.bitrem.proprietario
    elif secao == "prop_tri_reboque":
        if dados.tri_reboque is None:
            dados.tri_reboque = DadosVeiculo(tipo="CARRETA")
        if dados.tri_reboque.proprietario is None:
            dados.tri_reboque.proprietario = DadosProprietario()
        obj = dados.tri_reboque.proprietario
    if obj is None:
        print(f"  [!] Seção desconhecida: {secao}")
        return
    if not hasattr(obj, chave):
        print(f"  [!] Campo desconhecido: {secao}.{chave}")
        return
    setattr(obj, chave, valor)

    # 1) Se o campo alterado for do veículo (cidade ou uf), sincroniza para o proprietário dele
    if secao in ("veiculo", "carreta", "bitrem", "tri_reboque"):
        if chave in ("cidade", "uf") and getattr(obj, "proprietario", None):
            setattr(obj.proprietario, chave, valor)
            print(f"  -> Sincronizado {secao}.{chave} -> {secao}.proprietario.{chave}")
            # Redefine o objeto ativo como o proprietário dele para disparar a propagação
            obj = obj.proprietario

    # 2) Propagação entre proprietários idênticos e seus respectivos veículos
    def _mesmo_doc(p1, p2) -> bool:
        if p1 is None or p2 is None:
            return False
        d1 = "".join(c for c in (p1.cpf_cnpj or "") if c.isdigit())
        d2 = "".join(c for c in (p2.cpf_cnpj or "") if c.isdigit())
        if d1 and d2:
            return d1 == d2
        n1 = (p1.nome or "").strip().upper()
        n2 = (p2.nome or "").strip().upper()
        return bool(n1 and n2 and n1 == n2)

    if isinstance(obj, DadosProprietario):
        # Propaga para todos os outros proprietários com mesmo doc/nome
        todos_props = []
        if dados.proprietario:
            todos_props.append(("proprietario principal", dados.proprietario))
        for v in dados.iter_veiculos():
            vp = getattr(v, "proprietario", None)
            if vp:
                todos_props.append((f"{v.tipo or 'veiculo'}.proprietario", vp))

        for label_prop, p in todos_props:
            if p is obj:
                continue
            if _mesmo_doc(obj, p) or (not p.cpf_cnpj and not obj.cpf_cnpj):
                if hasattr(p, chave):
                    setattr(p, chave, valor)
                    print(f"  -> Propagado {chave}={valor!r} -> {label_prop}")

        # Se alterou cidade ou uf de um proprietário, propaga também para todos os veículos dele
        if chave in ("cidade", "uf"):
            for v in dados.iter_veiculos():
                vp = getattr(v, "proprietario", None)
                if vp and (_mesmo_doc(obj, vp) or (not vp.cpf_cnpj and not obj.cpf_cnpj)):
                    setattr(v, chave, valor)
                    print(f"  -> Propagado {chave}={valor!r} -> {v.tipo or 'veiculo'}.{chave}")

    # Sincroniza proprietario_nome direto de cada veículo com o nome do seu respectivo proprietário
    for v in dados.iter_veiculos():
        if v.proprietario and v.proprietario.nome:
            v.proprietario_nome = v.proprietario.nome




def _reaplicar_regras(dados: DadosCaso) -> None:
    from ocr.extrair_dados import _sincronizar_cidades_crlv

    if dados.proprietario:
        if dados.rntrc_tac and not dados.proprietario.rntrc:
            dados.proprietario.rntrc = dados.rntrc_tac
        dados.proprietario.aplicar_regras_gw()
    for v in dados.iter_veiculos():
        v.aplicar_regras_tipo()
    # Garante cidade do CRLV no prop e no veículo (evita save sem cidade)
    _sincronizar_cidades_crlv(dados)
    if dados.veiculo and dados.veiculo.placa:
        dados.motorista.placa_veiculo = dados.veiculo.placa
    if dados.carreta and dados.carreta.placa:
        dados.motorista.placa_carreta = dados.carreta.placa


def _salvar_snapshot(dados: DadosCaso, pasta: str = "confirmados") -> Path:
    from utils.paths import OUTPUT_DIR

    dest = OUTPUT_DIR / pasta
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{dados.caso_nome}.json"
    payload: Dict[str, Any] = {
        "caso_nome": dados.caso_nome,
        "rntrc_tac": dados.rntrc_tac,
        "motorista": dados.motorista.to_dict(),
        "veiculo": dados.veiculo.__dict__ if dados.veiculo else None,
        "carreta": dados.carreta.__dict__ if dados.carreta else None,
        "bitrem": dados.bitrem.__dict__ if dados.bitrem else None,
        "tri_reboque": dados.tri_reboque.__dict__ if dados.tri_reboque else None,
        "proprietario": dados.proprietario.__dict__ if dados.proprietario else None,
        "arquivos": dados.arquivos,
        "avisos_ocr": list(getattr(dados, "avisos_ocr", None) or []),
    }
    # fotos lists etc are fine
    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items() if not k.startswith("_")}
        if isinstance(o, list):
            return [_clean(x) for x in o]
        return o

    path.write_text(
        json.dumps(_clean(payload), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[Confirmar] JSON: {path}")
    return path
