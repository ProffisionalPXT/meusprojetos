"""
Aba Dados Operacionais do cadastro de motorista.

Mapeamento real (dump form):
  select#tipo          -> Funcionário | Agregado | Carreteiro
  #vei_placa           -> placa do veículo (readonly)
  #localiza_veiculo    -> botão "..." lookup veículo  (idlista=7)
  #car_placa           -> placa carreta
  #localiza_veiculo2   -> botão "..." lookup carreta
  #bi_placa / #localiza_veiculo3 -> Bi-Trem
  #tri_placa / #localiza_veiculo4 -> 3º Reboque

Composição por quantidade de CRLV:
  1 -> só Veículo (TRUCK)
  2 -> Veículo + Carreta
  3 -> Veículo + Carreta + Bi-Trem
  4 -> Veículo + Carreta + Bi-Trem + 3º Reboque
"""
from __future__ import annotations

from playwright.sync_api import Page

from gw_automation.veiculo import garantir_carreta, garantir_veiculo
from ocr.extrair_dados import DadosProprietario, DadosVeiculo


# Botões reais do GW (value="...")
BTN_VEICULO = "#localiza_veiculo"
BTN_CARRETA = "#localiza_veiculo2"
BTN_BITREM = "#localiza_veiculo3"
BTN_TRITREM = "#localiza_veiculo4"
CAMPO_PLACA_VEI = "#vei_placa"
CAMPO_PLACA_CAR = "#car_placa"
CAMPO_PLACA_BI = "#bi_placa"
CAMPO_PLACA_TRI = "#tri_placa"


def abrir_aba_operacional(page: Page) -> None:
    for seletor in (
        "text=Dados Operacionais",
        'a:has-text("Dados Operacionais")',
        'td:has-text("Dados Operacionais")',
    ):
        try:
            page.locator(seletor).first.click(timeout=4000)
            page.wait_for_timeout(800)
            print("[Operacional] Aba Dados Operacionais aberta")
            return
        except Exception:
            continue
    print("[Operacional] [!] Não encontrou aba Dados Operacionais")


def selecionar_tipo_motorista(page: Page, tipo: str = "Carreteiro") -> None:
    """
    select name=tipo / id=tipo
    Opções: Funcionário | Agregado | Carreteiro
    """
    tipo = (tipo or "Carreteiro").strip()
    # normaliza frota -> tipo operacional
    t = tipo.lower()
    if "agreg" in t:
        label = "Agregado"
    elif "func" in t:
        label = "Funcionário"
    else:
        label = "Carreteiro"

    for seletor in ('select[name="tipo"]', "#tipo"):
        try:
            page.select_option(seletor, label=label, timeout=2500)
            print(f"[Operacional] Tipo motorista = {label}")
            return
        except Exception:
            try:
                # valores curtos às vezes: c=Carreteiro, a=Agregado
                mapa = {"Carreteiro": "c", "Agregado": "a", "Funcionário": "f"}
                page.select_option(seletor, value=mapa.get(label, "c"), timeout=1500)
                print(f"[Operacional] Tipo motorista value = {mapa.get(label)}")
                return
            except Exception:
                continue
    print(f"[Operacional] [!] Tipo '{label}' não selecionado")


def _vincular_slot(
    page: Page,
    dados: DadosVeiculo | None,
    *,
    label: str,
    seletor_campo: str,
    seletor_botao: str,
    proprietario: DadosProprietario | None,
    via_carreta: bool = False,
) -> None:
    if not (dados and dados.placa):
        return
    prop = getattr(dados, "proprietario", None) or proprietario
    print(
        f"[Operacional] {label} -> placa={dados.placa} "
        f"prop={getattr(prop, 'cpf_cnpj', None) or getattr(prop, 'nome', None) or '?'}"
    )
    abrir_aba_operacional(page)
    if via_carreta:
        ok = garantir_carreta(
            page,
            dados,
            proprietario=prop,
            seletor_botao=seletor_botao,
            seletor_campo=seletor_campo,
        )
    else:
        ok = garantir_veiculo(
            page,
            dados,
            label_campo=label,
            seletor_campo=seletor_campo,
            seletor_botao=seletor_botao,
            proprietario=prop,
        )
    if not ok:
        print(
            f"[Operacional] [!] {label} não ficou em {seletor_campo} - "
            "cadastro pode ter ido, mas falta VINCULAR no motorista"
        )
    else:
        abrir_aba_operacional(page)


def vincular_veiculos(
    page: Page,
    *,
    veiculo: DadosVeiculo | None,
    carreta: DadosVeiculo | None = None,
    bitrem: DadosVeiculo | None = None,
    tri_reboque: DadosVeiculo | None = None,
    proprietario: DadosProprietario | None = None,
    tipo_motorista: str = "Carreteiro",
) -> None:
    """
    Na aba operacional:
      1. Tipo (Carreteiro/Agregado)
      2. #localiza_veiculo  -> Veículo (cavalo/truck)
      3. #localiza_veiculo2 -> Carreta
      4. #localiza_veiculo3 -> Bi-Trem (3º CRLV)
      5. #localiza_veiculo4 -> 3º Reboque (4º CRLV)
    """
    abrir_aba_operacional(page)
    selecionar_tipo_motorista(page, tipo_motorista)
    page.wait_for_timeout(400)

    tem_algo = any(
        v and v.placa for v in (veiculo, carreta, bitrem, tri_reboque)
    )
    if not tem_algo:
        print("[Operacional] Sem placas para vincular")
        return

    if veiculo and veiculo.placa:
        _vincular_slot(
            page,
            veiculo,
            label="Veículo",
            seletor_campo=CAMPO_PLACA_VEI,
            seletor_botao=BTN_VEICULO,
            proprietario=proprietario,
            via_carreta=False,
        )
    else:
        print("[Operacional] Sem placa de veículo - pulando")

    if carreta and carreta.placa:
        _vincular_slot(
            page,
            carreta,
            label="Carreta",
            seletor_campo=CAMPO_PLACA_CAR,
            seletor_botao=BTN_CARRETA,
            proprietario=proprietario,
            via_carreta=True,
        )

    if bitrem and bitrem.placa:
        _vincular_slot(
            page,
            bitrem,
            label="Bi-Trem",
            seletor_campo=CAMPO_PLACA_BI,
            seletor_botao=BTN_BITREM,
            proprietario=proprietario,
            via_carreta=False,
        )

    if tri_reboque and tri_reboque.placa:
        _vincular_slot(
            page,
            tri_reboque,
            label="3º Reboque",
            seletor_campo=CAMPO_PLACA_TRI,
            seletor_botao=BTN_TRITREM,
            proprietario=proprietario,
            via_carreta=False,
        )
