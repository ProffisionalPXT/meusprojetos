# main.py
from __future__ import annotations

import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

"""
Bot de Cadastro de Motorista - GW Webtrans

Fluxo (não perde progresso):
  1) OCR + confirmação
  2) SEMPRE abre Novo Motorista (NÃO pesquisa na consulta no início)
  3) Ao digitar CPF: se GW disser "já cadastrado, visualizar?" -> OK e edita
  4) Preenche SÓ o que falta (pessoais/docs)
  5) SALVA
  6) Continua no mesmo form (só reabre se o form fechar)
  7) Operacional: preenche Veículo/Carreta/Bi-Trem/3º Reboque se vazios
  8) SALVA

DRY_RUN=1: não clica Salvar.
"""

import os
import sys
import time
import traceback

from pathlib import Path
from dotenv import load_dotenv
project_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=project_dir / ".env", override=True)

from gw_automation.existentes import (
    pesquisar_motorista_por_cpf,
    reabrir_motorista_por_cpf,
    veiculo_ja_vinculado,
)
from gw_automation.login import browser_mode, fazer_login_gw
from gw_automation.motorista import preencher_dados_pessoais, preencher_documentacao
from gw_automation.navegacao import ir_para_novo_motorista
from gw_automation.operacional import abrir_aba_operacional, vincular_veiculos
from gw_automation.salvar import dry_run_ativo, salvar_motorista
from gw_automation.urls import NOVO_MOTORISTA
from ocr.confirmar import confirmar_dados_caso
from ocr.extrair_dados import extrair_dados_do_caso, motor_ocr
from utils.manual import pausar_para_manual
from utils.paths import garantir_pastas, INPUT_DIR
from utils.receber_fotos import arquivar_caso, listar_casos, resumo_casos


def processar_caso(page, caso) -> bool:
    print(f"\n{'='*50}")
    print(f"Processando caso: {caso.nome}")
    print(f"{'='*50}")

    dados = extrair_dados_do_caso(caso)
    if dados.rntrc_tac:
        print(f"[TAC] RNTRC: {dados.rntrc_tac}")

    dados = confirmar_dados_caso(dados)
    if dados is None:
        print(f"[Caso] '{caso.nome}' pulado (não confirmado).")
        return False

    cpf = "".join(c for c in (dados.motorista.cpf or "") if c.isdigit())
    ja_existia = False

    # ---------- Sempre Novo Motorista (não passa pela Consulta no início) ----------
    # Se o CPF já existir, o GW avisa ao digitar -> OK -> abre o cadastro existente.
    # Assim evita filtro Nome/CPF quebrado e lista vazia na consulta.
    print("\n=== Abrir cadastro: Novo Motorista (sem pesquisar na consulta) ===")
    ir_para_novo_motorista(page, usar_url_direta=True)
    if "cadmotorista" not in (page.url or ""):
        try:
            page.goto(NOVO_MOTORISTA, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(800)
        except Exception:
            ir_para_novo_motorista(page, usar_url_direta=True)

    # ---------- Pessoais + docs (só o que falta) ----------
    print("\n=== Pessoais + Documentação (só campos vazios) ===")
    preencher_dados_pessoais(page, dados.motorista)
    # se ao digitar CPF abriu "já cadastrado -> visualizar", já estamos no edit
    if getattr(dados.motorista, "_ja_existia", False) or "acao=editar" in (page.url or ""):
        ja_existia = True
        print("[GW] Form em modo edição (motorista já salvo) - só completa o que falta.")

    preencher_documentacao(page, dados.motorista)

    # Se já existia e pessoais/docs ok, salva rápido (sem networkidle)
    print("\n=== Salvar pessoais/docs (se houver algo novo) ===")
    ok_a = salvar_motorista(page)
    if ok_a:
        print("[GW] [OK] Salvou (ou dry-run).")
    else:
        print("[GW] [!] Salvar fase A com alerta - segue para veículos se o form abrir.")

    # ---------- Operacional: se JÁ está no form editar, NÃO volta à consulta ----------
    # (antes: salvava -> consulta CPF -> não clicava Editar -> travava; demorava muito)
    print("\n=== Abrir form para Operacional ===")
    url_agora = (page.url or "").lower()
    ja_no_form = (
        "cadmotorista" in url_agora
        and ("acao=editar" in url_agora or "id=" in url_agora or ja_existia)
    )
    # Form ainda aberto com campos de motorista?
    if not ja_no_form:
        try:
            if page.locator('input[name="cpf"], #cpf, input[name="nome"]').count() > 0:
                if "consulta" not in url_agora:
                    ja_no_form = True
        except Exception:
            pass

    if ja_no_form:
        print(
            "[GW] [OK] Já no cadastro do motorista (editar) - "
            "pula Consulta/Editar e vai direto a Operacional"
        )
    elif cpf:
        print(f"[GW] Pesquisa CPF {cpf} na consulta e clica Editar (lápis)...")
        ok_re = reabrir_motorista_por_cpf(page, cpf)
        if not ok_re:
            print("[GW] [!] 1ª reabertura falhou - 2ª tentativa...")
            page.wait_for_timeout(600)
            ok_re = reabrir_motorista_por_cpf(page, cpf)
        if not ok_re:
            print(
                "[GW] [!] Não abriu Editar após consultar CPF. "
                "Operacional precisa do form do motorista aberto."
            )
            pausar_para_manual(
                f"Não abriu o cadastro do motorista (CPF {cpf}).",
                dica=(
                    "Na Consulta: clique no LÁPIS (Editar) da linha do motorista. "
                    "Quando o form abrir, ENTER."
                ),
                page=page,
            )
        else:
            print("[GW] [OK] Motorista reaberto via Consulta -> Editar")
    else:
        print("[GW] Sem CPF - tenta operacional no form atual.")

    abrir_aba_operacional(page)

    # Só vincula o que estiver vazio (ou com placa diferente da esperada)
    def _placa_no_campo(sel: str, esperada: str) -> bool:
        if not veiculo_ja_vinculado(page, sel):
            return False
        if not esperada:
            return True
        try:
            val = (page.input_value(sel, timeout=1000) or "").upper()
            exp = "".join(c for c in esperada.upper() if c.isalnum())
            return exp in val.replace("-", "")
        except Exception:
            return False

    pl_v = (dados.veiculo.placa if dados.veiculo else "") or ""
    pl_c = (dados.carreta.placa if dados.carreta else "") or ""
    pl_b = (dados.bitrem.placa if dados.bitrem else "") or ""
    pl_t = (dados.tri_reboque.placa if dados.tri_reboque else "") or ""
    precisa_vei = bool(pl_v) and not _placa_no_campo("#vei_placa", pl_v)
    precisa_car = bool(pl_c) and not _placa_no_campo("#car_placa", pl_c)
    precisa_bi = bool(pl_b) and not _placa_no_campo("#bi_placa", pl_b)
    precisa_tri = bool(pl_t) and not _placa_no_campo("#tri_placa", pl_t)

    if not precisa_vei and pl_v:
        print(f"[GW] · Veículo já vinculado ({pl_v}) - mantém")
    if not precisa_car and pl_c:
        print(f"[GW] · Carreta já vinculada ({pl_c}) - mantém")
    if not precisa_bi and pl_b:
        print(f"[GW] · Bi-Trem já vinculado ({pl_b}) - mantém")
    if not precisa_tri and pl_t:
        print(f"[GW] · 3º Reboque já vinculado ({pl_t}) - mantém")

    if precisa_vei or precisa_car or precisa_bi or precisa_tri:
        vincular_veiculos(
            page,
            veiculo=dados.veiculo if precisa_vei else None,
            carreta=dados.carreta if precisa_car else None,
            bitrem=dados.bitrem if precisa_bi else None,
            tri_reboque=dados.tri_reboque if precisa_tri else None,
            proprietario=dados.proprietario,
            tipo_motorista=dados.motorista.tipo_motorista or "Carreteiro",
        )
        # re-checa após vínculo
        abrir_aba_operacional(page)
        faltando = []
        if pl_v and not _placa_no_campo("#vei_placa", pl_v):
            print(f"[GW] [!] Veículo {pl_v} AINDA vazio em #vei_placa após vínculo")
            faltando.append(f"Veículo {pl_v} (#vei_placa)")
        if pl_c and not _placa_no_campo("#car_placa", pl_c):
            print(f"[GW] [!] Carreta {pl_c} AINDA vazia em #car_placa após vínculo")
            faltando.append(f"Carreta {pl_c} (#car_placa)")
        if pl_b and not _placa_no_campo("#bi_placa", pl_b):
            print(f"[GW] [!] Bi-Trem {pl_b} AINDA vazio em #bi_placa após vínculo")
            faltando.append(f"Bi-Trem {pl_b} (#bi_placa)")
        if pl_t and not _placa_no_campo("#tri_placa", pl_t):
            print(f"[GW] [!] 3º Reboque {pl_t} AINDA vazio em #tri_placa após vínculo")
            faltando.append(f"3º Reboque {pl_t} (#tri_placa)")
        if faltando:
            pausar_para_manual(
                "Operacional incompleto - o robô não conseguiu vincular tudo.",
                dica=(
                    "Na aba Dados Operacionais, use os 3 pontinhos e vincule: "
                    + "; ".join(faltando)
                    + ". Depois ENTER (e o robô tenta Salvar)."
                ),
                page=page,
            )
    else:
        print("[GW] Nada a vincular em operacional (já completo ou sem placa).")

    print("\n=== Salvar final ===")
    ok_b = salvar_motorista(page)
    if not ok_b and not dry_run_ativo():
        r = pausar_para_manual(
            "Salvar final não confirmou sucesso.",
            dica=(
                "Confira campos obrigatórios, clique Salvar no GW se faltar. "
                "ENTER quando estiver ok (ou s se quiser deixar incompleto)."
            ),
            page=page,
        )
        if r == "ok":
            # 2ª chance: se você salvou na mão, considera ok
            ok_b = True
            print("[GW] [OK] Seguindo após intervenção no Salvar final.")

    ok = ok_b or ok_a or ja_existia
    if ok:
        print(f"[Caso] '{caso.nome}' ok.")
        if not dry_run_ativo():
            arquivar_caso(caso, motivo="ok")
        else:
            print("[Arquivar] DRY-RUN - pasta em input/.")
        return True

    print(f"[Caso] '{caso.nome}' incompleto - pasta permanece em input/.")
    pausar_para_manual(
        f"Caso '{caso.nome}' ficou incompleto.",
        dica="Ajuste no GW se quiser; pasta permanece em input\\ para rodar de novo. ENTER para seguir.",
        page=page,
    )
    return False


def main() -> None:
    print()
    print("=" * 50)
    print("  ROBÔ GW - Cadastro de Motorista")
    print("=" * 50)
    print("  Já cadastrado? -> OK visualizar -> só preenche o que falta")
    print("  (ex.: cavalo + carreta + bi-trem na aba Operacional)")
    print("  Tentativas: 1ª e 2ª automáticas · 3ª você faz")
    print("  (ENTER = robô reconhece lista/campo e continua · s = pular)")
    print("  Ctrl+C encerra")
    print("=" * 50)
    print()
    garantir_pastas()

    dry = dry_run_ativo()
    print(f"  Modo: {'TESTE (não grava)' if dry else 'GRAVAÇÃO REAL'}")
    print(f"  Browser: {browser_mode()}  |  OCR: {motor_ocr()}")
    try:
        from utils.flags import imprimir_flags

        imprimir_flags()
    except Exception:
        pass
    print()

    casos = listar_casos()
    print(resumo_casos(casos))
    print(f"\n  Pasta: {INPUT_DIR}\n")

    if not casos:
        print("  Nenhuma pasta em input\\")
        if sys.stdin.isatty():
            input("  ENTER para sair...")
        return

    email = os.getenv("GW_EMAIL")
    senha = os.getenv("GW_SENHA")
    org = os.getenv("ORGANIZACAO", "PURM")
    if not email or not senha:
        print("Erro: credenciais .env")
        return

    page = browser = playwright = None
    try:
        page, context, browser, playwright = fazer_login_gw(email, senha, org)
        print("\n✅ Login OK")

        for caso in casos:
            try:
                processar_caso(page, caso)
            except Exception as e:
                print(f"Erro '{caso.nome}': {e}")
                traceback.print_exc()
                pausar_para_manual(
                    f"Erro no caso '{caso.nome}': {e}",
                    dica="Corrija no browser se der; ENTER para o próximo caso (ou fim).",
                    page=page,
                )

        print("\n=== Fim ===")
        if browser_mode() == "headless" or not sys.stdin.isatty():
            time.sleep(3)
        else:
            if sys.stdin.isatty():
                input("ENTER para fechar...")
    except Exception as e:
        print(f"Erro: {e}")
        traceback.print_exc()
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEncerrado (Ctrl+C).")
        sys.exit(0)
