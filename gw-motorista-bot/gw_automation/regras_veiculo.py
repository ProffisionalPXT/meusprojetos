"""
Tipo de veículo no GW + Cap. carga / Tara (regras fixas da operação).

Dropdown *Tipo: CARRETA | CAVALO | TRUCK

Classificação por quantidade de CRLV (documentos de veículo):
  - 1 documento  -> TRUCK  (só campo Veículo)
  - 2 documentos -> CAVALO + CARRETA
  - 3 documentos -> CAVALO + CARRETA + Bi-Trem  (2ª carreta)
  - 4 documentos -> CAVALO + CARRETA + Bi-Trem + 3º Reboque
  - texto do CRLV/nome ajuda a separar cavalo x reboques

No cadastro do veículo no GW, Bi-Trem e 3º Reboque usam tipo **CARRETA**
(cap/tara 27000). A diferença é só o slot na aba Operacional do motorista.

Capacidade e Tara - SEMPRE estes valores (não inventar outros):
  CAVALO  -> cap 27000 | tara 27000
  CARRETA -> cap 27000 | tara 27000
  TRUCK   -> cap 12000 | tara 12000
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


TIPO_CAVALO = "CAVALO"
TIPO_CARRETA = "CARRETA"
TIPO_TRUCK = "TRUCK"

# Valores fixos - sempre estes
CAP_TARA = {
    TIPO_CAVALO: ("27000", "27000"),
    TIPO_CARRETA: ("27000", "27000"),
    TIPO_TRUCK: ("12000", "12000"),
}

# Tipo de frota no GW (prints): Agregada | Carreteiro
FROTA_AGREGADA = "Agregada"
FROTA_CARRETEIRO = "Carreteiro"
FROTAS_VALIDAS = (FROTA_AGREGADA, FROTA_CARRETEIRO)


def normalizar_tipo_frota(valor: str) -> str:
    """Aceita agregada/carreteiro (e variações). Default: Carreteiro."""
    if not valor:
        return FROTA_CARRETEIRO
    t = valor.strip().lower()
    if "agreg" in t:
        return FROTA_AGREGADA
    if "carret" in t:
        return FROTA_CARRETEIRO
    return FROTA_CARRETEIRO


_KEYWORDS_CARRETA = (
    "semi-reboque",
    "semirreboque",
    "semi reboque",
    "semi-reboque",
    "carreta",
    "reboque",
    "carga semi",
    "carga semi-reboque",
)
_KEYWORDS_CAVALO = (
    "caminhao trator",
    "caminhão trator",
    "caminhao-trator",
    "caminhão-trator",
    "cavalo mecanico",
    "cavalo mecânico",
    "cavalo",
    "tracao",
    "tração",
    "trator",
)


@dataclass
class CapTara:
    cap_carga: str
    tara: str


def cap_tara_para_tipo(tipo: str) -> CapTara:
    tipo = (tipo or "").strip().upper()
    cap, tara = CAP_TARA.get(tipo, ("12000", "12000"))
    return CapTara(cap_carga=cap, tara=tara)


def aplicar_cap_tara(veiculo) -> None:
    """
    Cap e tara SEMPRE conforme o tipo.
    Sobrescreve valores errados/vazios - regra fixa da operação.
    """
    if not veiculo or not veiculo.tipo:
        return
    ct = cap_tara_para_tipo(veiculo.tipo)
    veiculo.cap_carga = ct.cap_carga
    veiculo.tara = ct.tara


def classificar_por_texto(texto: str) -> Optional[str]:
    """Só para desempatar cavalo x carreta. Retorna None se não tiver certeza."""
    if not texto:
        return None
    t = _normalizar(texto)
    if any(k in t for k in _KEYWORDS_CARRETA):
        return TIPO_CARRETA
    if any(k in t for k in _KEYWORDS_CAVALO):
        return TIPO_CAVALO
    return None


def classificar_par_documentos(textos: List[str]) -> Tuple[str, ...]:
    """
    Tipos na composição (ordem: veículo, carreta, bi-trem, 3º reboque):
      0 docs -> ()
      1 doc  -> (TRUCK,)
      2 docs -> (CAVALO, CARRETA)
      3 docs -> (CAVALO, CARRETA, CARRETA)   # 3º = Bi-Trem
      4+    -> (CAVALO, CARRETA, CARRETA, CARRETA)  # 4º = 3º Reboque
    """
    n = len(textos)
    if n == 0:
        return tuple()
    if n == 1:
        return (TIPO_TRUCK,)
    if n == 2:
        return (TIPO_CAVALO, TIPO_CARRETA)
    if n == 3:
        return (TIPO_CAVALO, TIPO_CARRETA, TIPO_CARRETA)
    return (TIPO_CAVALO, TIPO_CARRETA, TIPO_CARRETA, TIPO_CARRETA)


def ordenar_composicao(
    itens: List[Tuple[object, str]],
) -> Tuple[Optional[object], Optional[object], Optional[object], Optional[object]]:
    """
    Ordena documentos de veículo nos slots do GW:

      (cavalo_ou_unico, carreta, bitrem, tri_reboque)

    - 1 doc:  (doc, None, None, None)  - tipo TRUCK aplicado fora
    - 2 docs: (cavalo, carreta, None, None)
    - 3 docs: (cavalo, carreta, bitrem, None)
    - 4+ docs: (cavalo, carreta, bitrem, tri)  - extras além do 4º são ignorados

    Texto do CRLV/nome separa o cavalo dos reboques; reboques ficam na ordem
    em que chegaram (exceto o cavalo, que vai para o 1º slot).
    """
    if not itens:
        return None, None, None, None
    if len(itens) == 1:
        return itens[0][0], None, None, None

    classes = [classificar_por_texto(t) for _, t in itens]

    # Preferência: item classificado como CAVALO
    idx_cavalo: Optional[int] = None
    for i, c in enumerate(classes):
        if c == TIPO_CAVALO:
            idx_cavalo = i
            break

    # Senão: primeiro que NÃO parece carreta
    if idx_cavalo is None:
        for i, c in enumerate(classes):
            if c != TIPO_CARRETA:
                idx_cavalo = i
                break

    # Fallback 2 docs legado: se 1º parece carreta e 2º não, cavalo = 2º
    if idx_cavalo is None and len(itens) >= 2:
        t0 = classes[0]
        t1 = classes[1]
        if t0 == TIPO_CARRETA and t1 != TIPO_CARRETA:
            idx_cavalo = 1
        elif t1 == TIPO_CAVALO and t0 != TIPO_CAVALO:
            idx_cavalo = 1

    if idx_cavalo is None:
        idx_cavalo = 0

    cavalo = itens[idx_cavalo][0]
    reboques = [itens[i][0] for i in range(len(itens)) if i != idx_cavalo]

    carreta = reboques[0] if len(reboques) > 0 else None
    bitrem = reboques[1] if len(reboques) > 1 else None
    tri = reboques[2] if len(reboques) > 2 else None
    return cavalo, carreta, bitrem, tri


def ordenar_cavalo_carreta(
    itens: List[Tuple[object, str]],
) -> Tuple[Optional[object], Optional[object]]:
    """
    Compat: com 2+ docs devolve (cavalo, carreta).
    Preferir ordenar_composicao para bi-trem / 3º reboque.
    """
    cavalo, carreta, _bitrem, _tri = ordenar_composicao(itens)
    return cavalo, carreta


def _normalizar(s: str) -> str:
    s = s.lower()
    for a, b in (
        ("ã", "a"),
        ("á", "a"),
        ("â", "a"),
        ("é", "e"),
        ("ê", "e"),
        ("í", "i"),
        ("ó", "o"),
        ("ô", "o"),
        ("ú", "u"),
        ("ç", "c"),
    ):
        s = s.replace(a, b)
    return s
