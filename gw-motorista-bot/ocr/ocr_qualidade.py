"""
Qualidade e validação de campos críticos do OCR (placa, renavam, chassi).

Objetivos:
  - Maximizar acerto local (Tesseract + parsers) sem depender do Gemini
  - Marcar dúvida quando houver candidatos conflitantes ou validação fraca
  - Gemini só entra se campo vazio OU duvidoso
  - Gerar avisos claros para o usuário confirmar/corrigir

Não altera automação do GW - só OCR / confirmação.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Placa Mercosul LLLNLNN  |  antiga LLLNNNN
# ---------------------------------------------------------------------------

# OCR: posição de LETRA (0,1,2,4) vs DÍGITO (3,5,6)
_LETRA_DE = {
    "0": "O", "1": "I", "8": "B", "5": "S", "2": "Z",
    "6": "G", "4": "A", "7": "T", "9": "G",
}
_DIGITO_DE = {
    "O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1",
    "B": "8", "S": "5", "Z": "2", "G": "6", "T": "7", "A": "4",
}

# Pares que o OCR troca com frequência (H↔B, F↔S no Bi-Trem IUM1F64->IUM1S64)
_PARES_CONFUSAO = (
    ("B", "H"), ("H", "B"), ("B", "8"), ("8", "B"),
    ("0", "O"), ("O", "0"), ("1", "I"), ("I", "1"),
    ("Z", "2"), ("2", "Z"), ("S", "5"), ("5", "S"),
    ("G", "6"), ("6", "G"), ("D", "0"), ("Q", "0"),
    ("F", "S"), ("S", "F"),  # IUM1F64 lido como IUM1S64
    ("F", "P"), ("P", "F"),
    ("E", "F"), ("F", "E"),
)


def limpar_placa(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (s or "")).upper()


def so_digitos(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def normalizar_placa_mercosul(s: str) -> str:
    """
    Normaliza placa BR sem destruir o formato antigo.

    - Antiga LLLNNNN (ex: PJO9971) -> mantém como está
    - Mercosul LLLNLNN (ex: PJO9G71) -> corrige confusões OCR nas posições
    - Ambígua -> tenta Mercosul só se pos. 4 já for letra ou não for antiga pura
    """
    p = limpar_placa(s)
    if len(p) < 7:
        return p
    p7 = p[:7]
    # Placa antiga pura (3 letras + 4 dígitos): NÃO converter 9->G na pos 4
    # Bug antigo: PJO9971 virava PJO9G71 e quebrava o cadastro.
    if re.match(r"^[A-Z]{3}\d{4}$", p7):
        return p7
    # Mercosul estrito ou quase: força letra nas pos 0,1,2,4 e dígito no resto
    if len(p7) == 7:
        out = []
        for i, ch in enumerate(p7):
            if i in (0, 1, 2, 4):
                out.append(_LETRA_DE.get(ch, ch) if ch.isdigit() else ch)
            else:
                out.append(_DIGITO_DE.get(ch, ch) if ch.isalpha() else ch)
        return "".join(out)
    return p


def placa_formato_ok(placa: str) -> bool:
    p = limpar_placa(placa)
    if re.match(r"^[A-Z]{3}\d[A-Z0-9]\d{2}$", p):
        return True
    if re.match(r"^[A-Z]{3}\d{4}$", p):
        return True
    return False


def _variantes_confusao_placa(placa: str) -> List[str]:
    """Gera variantes trocando 1 caractere confuso (ex. B↔H)."""
    p = normalizar_placa_mercosul(placa)
    if len(p) != 7:
        return [p] if p else []
    out = {p}
    for i, ch in enumerate(p):
        for a, b in _PARES_CONFUSAO:
            if ch == a:
                cand = p[:i] + b + p[i + 1 :]
                out.add(normalizar_placa_mercosul(cand))
    return list(out)


def extrair_placas_votacao(texto: str) -> Tuple[str, float, List[str]]:
    """
    Encontra todas as placas no texto, vota e devolve:
      (melhor_placa, confianca_0a1, outras_candidatas)
    """
    t = (texto or "").upper()
    t_limpo = re.sub(r"[^A-Z0-9\n ]", " ", t)
    brutas: List[str] = []

    for m in re.finditer(r"\b([A-Z]{3}\s*-?\s*\d\s*[A-Z0-9]\s*\d{2})\b", t_limpo):
        brutas.append(limpar_placa(m.group(1)))
    for m in re.finditer(r"\b([A-Z]{3}\s*-?\s*\d{4})\b", t_limpo):
        brutas.append(limpar_placa(m.group(1)))
    # colado sem word boundary (OCR gruda)
    for m in re.finditer(r"(?<![A-Z0-9])([A-Z]{3}\d[A-Z0-9]\d{2})(?![A-Z0-9])", t):
        brutas.append(limpar_placa(m.group(1)))

    if not brutas:
        return "", 0.0, []

    # normaliza e conta (bruto + score)
    scores: Dict[str, float] = {}
    raw_count: Dict[str, int] = {}
    for raw in brutas:
        p = normalizar_placa_mercosul(raw)
        if len(p) < 7:
            continue
        p = p[:7]
        if not placa_formato_ok(p):
            continue
        scores[p] = scores.get(p, 0.0) + 1.0
        raw_count[p] = raw_count.get(p, 0) + 1
        # bônus se perto da palavra PLACA (campo real do CRLV)
        for m in re.finditer(re.escape(p), t):
            ctx = t[max(0, m.start() - 30) : m.start() + 35]
            if "PLACA" in ctx:
                scores[p] = scores.get(p, 0) + 3.0
                break
            if "RENAVAM" in ctx or "EXERC" in ctx:
                scores[p] = scores.get(p, 0) + 1.0
                break
        # bônus formato mercosul estrito letra na pos 4 - muito maior para
        # preferir a placa atualizada quando o CRLV ainda tem a placa antiga
        if re.match(r"^[A-Z]{3}\d[A-Z]\d{2}$", p):
            scores[p] = scores.get(p, 0) + 2.5

    # penaliza placa ANTIGA se já existe candidata Mercosul (placa atualizada)
    tem_mercosul = any(re.match(r"^[A-Z]{3}\d[A-Z]\d{2}$", p) for p in scores)
    if tem_mercosul:
        for p in list(scores.keys()):
            if re.match(r"^[A-Z]{3}\d{4}$", p):
                scores[p] = max(0.0, scores[p] - 1.5)

    if not scores:
        return "", 0.0, []

    ordenados = sorted(
        scores.items(),
        key=lambda x: (x[1], raw_count.get(x[0], 0)),
        reverse=True,
    )
    melhor, sc = ordenados[0]
    segundo = ordenados[1][0] if len(ordenados) > 1 else ""
    segundo_sc = ordenados[1][1] if len(ordenados) > 1 else 0.0

    # confiança
    total = sum(scores.values()) or 1.0
    conf = min(1.0, sc / max(total * 0.6, sc))
    if sc >= 3 and (sc - segundo_sc) >= 1.5:
        conf = max(conf, 0.85)
    elif segundo and _placas_quase_iguais(melhor, segundo):
        # empate confuso (B/H, 0/O...) -> NÃO confiar no local; Gemini/usuário
        conf = min(conf, 0.38)
        if abs(sc - segundo_sc) < 1.2:
            conf = min(conf, 0.32)
        # se o 2º aparece tantas vezes quanto o 1º no texto bruto, dúvida máxima
        if raw_count.get(melhor, 0) <= raw_count.get(segundo, 0):
            conf = min(conf, 0.30)
    elif sc < 1.5:
        conf = min(conf, 0.55)

    outras = [p for p, _ in ordenados[1:6]]
    return melhor, conf, outras


def _placas_quase_iguais(a: str, b: str) -> bool:
    a, b = limpar_placa(a), limpar_placa(b)
    if len(a) != len(b) or len(a) != 7:
        return False
    diff = sum(1 for x, y in zip(a, b) if x != y)
    if diff == 0:
        return True
    if diff > 2:
        return False
    for i, (x, y) in enumerate(zip(a, b)):
        if x == y:
            continue
        if (x, y) not in _PARES_CONFUSAO and (y, x) not in _PARES_CONFUSAO:
            return False
    return True


# ---------------------------------------------------------------------------
# RENAVAM
# ---------------------------------------------------------------------------

def renavam_dv_ok(renavam: str) -> bool:
    """Valida dígito verificador do RENAVAM (11 dígitos)."""
    r = so_digitos(renavam)
    if len(r) == 9:
        r = r.zfill(11)
    if len(r) != 11:
        return False
    if r == r[0] * 11:
        return False
    d = [int(c) for c in r]
    seq = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(d[i] * seq[i] for i in range(10))
    dig = (soma * 10) % 11
    if dig == 10:
        dig = 0
    return dig == d[10]


def extrair_renavam_melhor(texto: str) -> Tuple[str, float, List[str]]:
    """
    Extrai renavam preferindo label RENAVAM e DV válido.
    Retorna (valor, confianca, avisos).
    """
    t = texto or ""
    avisos: List[str] = []
    cands: List[Tuple[str, float]] = []

    for m in re.finditer(
        r"(?:C[OÓ]DIGO\s*)?RENAVAM\s*[:\.]?\s*(\d{9,11})\b",
        t,
        re.I,
    ):
        cand = m.group(1).zfill(11) if len(m.group(1)) <= 11 else m.group(1)
        if len(cand) == 9:
            cand = cand.zfill(11)
        score = 5.0
        if renavam_dv_ok(cand):
            score += 4.0
        if cand.startswith("00") or cand.startswith("0"):
            score += 1.5
        cands.append((cand[-11:] if len(cand) > 11 else cand.zfill(11), score))

    for m in re.finditer(r"\b(\d{9,11})\b", t):
        raw = m.group(1)
        cand = raw.zfill(11) if len(raw) < 11 else raw
        if len(cand) != 11:
            continue
        pos = m.start()
        ctx = t[max(0, pos - 40) : pos + len(raw) + 20].upper()
        if any(
            x in ctx
            for x in (
                "SEGURAN", "CLA", "CRV", "NUMERO DO CRV", "NÚMERO DO CRV",
                "POTENC", "CILINDR", "CPF",
            )
        ) and "RENAVAM" not in ctx:
            continue
        score = 1.0
        if renavam_dv_ok(cand):
            score += 4.0
        if cand.startswith("00"):
            score += 2.0
        elif cand.startswith("0"):
            score += 1.0
        if "RENAVAM" in ctx:
            score += 3.0
        cands.append((cand, score))

    if not cands:
        return "", 0.0, ["renavam não encontrado no OCR local"]

    # agrupa por valor
    por: Dict[str, float] = {}
    for c, s in cands:
        por[c] = max(por.get(c, 0), s)
    ordenados = sorted(por.items(), key=lambda x: x[1], reverse=True)
    melhor, sc = ordenados[0]

    conf = 0.9 if renavam_dv_ok(melhor) and sc >= 6 else (
        0.7 if renavam_dv_ok(melhor) else (0.4 if sc >= 3 else 0.25)
    )
    if len(ordenados) > 1 and ordenados[1][1] >= sc - 0.5:
        conf = min(conf, 0.4)
        avisos.append(
            f"renavam: candidatos conflitantes "
            f"{melhor} vs {ordenados[1][0]}"
        )
    if not renavam_dv_ok(melhor):
        avisos.append(f"renavam {melhor} não passou no dígito verificador")
        conf = min(conf, 0.4)

    return melhor, conf, avisos


# ---------------------------------------------------------------------------
# CHASSI / VIN
# ---------------------------------------------------------------------------

_VIN_TRANS = str.maketrans(
    {
        "A": "1", "B": "2", "C": "3", "D": "4", "E": "5", "F": "6", "G": "7",
        "H": "8", "J": "1", "K": "2", "L": "3", "M": "4", "N": "5", "P": "7",
        "R": "9", "S": "2", "T": "3", "U": "4", "V": "5", "W": "6", "X": "7",
        "Y": "8", "Z": "9",
    }
)
_VIN_PESOS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


def _norm_vin(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", s or "").upper()
    # I, O, Q não existem em VIN - OCR costuma colocar
    s = s.replace("I", "1").replace("O", "0").replace("Q", "0")
    return s


def vin_check_digit_ok(vin: str) -> bool:
    """ISO 3779 check digit (posição 9). Muitos chassis BR não seguem; uso soft."""
    v = _norm_vin(vin)
    if len(v) != 17:
        return False
    if any(c in v for c in "IOQ"):
        return False
    try:
        vals = []
        for ch in v:
            if ch.isdigit():
                vals.append(int(ch))
            else:
                vals.append(int(ch.translate(_VIN_TRANS)))
        total = sum(vals[i] * _VIN_PESOS[i] for i in range(17))
        resto = total % 11
        esperado = "X" if resto == 10 else str(resto)
        return v[8] == esperado
    except Exception:
        return False


def _vin_ok_basico(vin: str, raw: str = "") -> bool:
    if len(vin) != 17:
        return False
    if not (re.search(r"[A-Z]", vin) and re.search(r"\d", vin)):
        return False
    u = (raw or vin).upper()
    if any(
        x in u or x in vin
        for x in (
            "POTEN", "P0TEN", "PTENC", "CILIN", "MOTOR", "DIESEL", "PRATA",
            "BRANC", "ALUGUE", "CARGA", "TRATO", "POTENC",
        )
    ):
        return False
    letras = sum(1 for c in vin if c.isalpha())
    if letras > 12 or letras < 2:
        return False
    return True


def extrair_chassi_melhor(texto: str) -> Tuple[str, float, List[str]]:
    t = texto or ""
    avisos: List[str] = []
    hits: List[Tuple[str, float]] = []

    # Carreta/semi: chassi só dígitos 11–14 (ex. 264691407839) rotulado CHASSI
    m_num = re.search(r"CHASSI\s*[:\.]?\s*(\d{11,14})\b", t, re.I)
    if m_num:
        cand = m_num.group(1)
        if not cand.startswith("00"):
            # alta confiança - rotulado e numérico (padrão semi-reboque BR)
            hits.append((cand, 9.0))

    m = re.search(
        r"CHASSI\s*[:\.]?\s*([A-Z0-9OIQ][A-Z0-9OIQ \-]{10,22})",
        t,
        re.I,
    )
    if m:
        raw = m.group(1)
        digs = re.sub(r"\D", "", raw)
        if 11 <= len(digs) <= 14 and digs.isdigit() and not digs.startswith("00"):
            hits.append((digs, 8.5))
        vin = _norm_vin(raw)
        if len(vin) >= 17:
            vin = vin[:17]
            if _vin_ok_basico(vin, raw):
                sc = 7.0
                if vin.startswith("9"):
                    sc += 1.5
                if vin_check_digit_ok(vin):
                    sc += 2.0
                hits.append((vin, sc))

    for m in re.finditer(r"\b([A-Z0-9OIQ]{17})\b", t, re.I):
        raw = m.group(1)
        vin = _norm_vin(raw)
        if not _vin_ok_basico(vin, raw):
            continue
        sc = 7.0
        if vin.startswith("9"):
            sc += 1.5
        if vin_check_digit_ok(vin):
            sc += 2.0
        # perto de CHASSI
        pos = m.start()
        ctx = t[max(0, pos - 20) : pos].upper()
        if "CHASSI" in ctx or "CHAS" in ctx:
            sc += 3.0
        hits.append((vin, sc))

    # com espaços
    for m in re.finditer(
        r"\b([A-Z0-9OIQ]{3,}(?:[\s\-][A-Z0-9OIQ]{1,}){2,})\b", t, re.I
    ):
        raw = m.group(1)
        vin = _norm_vin(raw)
        if len(vin) >= 17:
            vin = vin[:17]
            if _vin_ok_basico(vin, raw):
                hits.append((vin, 2.0 + (1.0 if vin.startswith("9") else 0)))

    eh_carreta = bool(re.search(r"SEMI|REBOQUE|CARRETA|RANDON|FACCHINI|GUERRA", t, re.I))

    # 11–14 dígitos (chassi de semi-reboque BR) - score alto em carreta
    for m in re.finditer(r"\b(\d{11,14})\b", t):
        cand = m.group(1)
        if cand.startswith("00"):
            continue  # renavam
        if len(cand) == 14:
            # pode ser CNPJ - só aceita se perto de CHASSI
            pos = m.start()
            ctx = t[max(0, pos - 40) : pos + 15].upper()
            if "CHASSI" not in ctx and "CHAS" not in ctx:
                continue
        pos = m.start()
        ctx = t[max(0, pos - 40) : pos + 15].upper()
        if any(x in ctx for x in ("RENAVAM", "CNPJ", "CPF", "RNTRC", "CRV", "CGC")):
            continue
        if "CHASSI" in ctx or "CHAS" in ctx:
            hits.append((cand, 8.0))
        elif eh_carreta and len(cand) == 12:
            # carreta: 12 dígitos soltos valem mais que VIN OCR inventado
            hits.append((cand, 6.5))
        elif eh_carreta and 11 <= len(cand) <= 13:
            hits.append((cand, 5.0))

    if not hits:
        return "", 0.0, ["chassi não encontrado no OCR local"]

    por: Dict[str, float] = {}
    for v, s in hits:
        por[v] = max(por.get(v, 0), s)
    ordenados = sorted(por.items(), key=lambda x: x[1], reverse=True)
    melhor, sc = ordenados[0]

    # Em carreta/semi: SEMPRE prefere numérico 11–14 sobre VIN 17 com score < 7
    if eh_carreta and (not melhor.isdigit() or len(melhor) == 17):
        for v, s in ordenados:
            if v.isdigit() and 11 <= len(v) <= 14:
                if sc < 7.5 or s >= sc:
                    avisos.append(
                        f"chassi: preferido numérico de carreta {v} "
                        f"(descartado VIN OCR {melhor})"
                    )
                    melhor, sc = v, max(s, 6.5)
                    break

    # VIN 17 com score baixo vs numérico -> prefere numérico
    if not melhor.isdigit() and sc < 7:
        for v, s in ordenados:
            if v.isdigit() and 11 <= len(v) <= 14:
                avisos.append(
                    f"chassi: preferido numérico {v} "
                    f"(VIN OCR duvidoso {melhor} descartado)"
                )
                melhor, sc = v, max(s, 6.0)
                break

    conf = 0.85 if sc >= 7 else (0.65 if sc >= 5 else 0.4)
    if len(melhor) == 17 and len(ordenados) > 1:
        outros_vin = [x for x, _ in ordenados if len(x) == 17 and x != melhor]
        if outros_vin and _chassi_quase(melhor, outros_vin[0]):
            conf = min(conf, 0.4)
            avisos.append(
                f"chassi: variantes próximas {melhor} / {outros_vin[0]}"
            )
    if len(melhor) == 17 and not vin_check_digit_ok(melhor) and not melhor.startswith("9"):
        avisos.append(f"chassi {melhor} com formato atípico")
        conf = min(conf, 0.5)
    # VIN inventado pelo OCR (score baixo)
    if len(melhor) == 17 and sc < 5:
        conf = min(conf, 0.4)
        avisos.append(f"chassi {melhor} com baixa confiança (possível lixo OCR)")
    if melhor.isdigit() and 11 <= len(melhor) <= 14:
        conf = max(conf, 0.7)

    return melhor, conf, avisos


def _chassi_quase(a: str, b: str) -> bool:
    a, b = _norm_vin(a), _norm_vin(b)
    if len(a) != 17 or len(b) != 17:
        return False
    return sum(1 for x, y in zip(a, b) if x != y) <= 2


# ---------------------------------------------------------------------------
# Avaliação de dúvida + avisos
# ---------------------------------------------------------------------------

# limiar: abaixo = duvidoso -> pode chamar Gemini e avisar usuário
LIMIAR_CONFIANCA = 0.55


def avaliar_extracao_crlv(ex: Dict[str, Any], texto: str = "") -> Dict[str, Any]:
    """
    Anexa em ex:
      _confianca: {campo: 0..1}
      _duvida: [campos]
      _avisos_ocr: [mensagens]
      e corrige placa/renavam/chassi se o texto permitir votação melhor.
    """
    avisos: List[str] = list(ex.get("_avisos_ocr") or [])
    conf: Dict[str, float] = dict(ex.get("_confianca") or {})
    duvida: List[str] = []

    # --- PLACA ---
    pl_txt, conf_pl, outras = extrair_placas_votacao(texto or "")
    pl_atual = limpar_placa(str(ex.get("placa") or ""))
    if pl_txt:
        if not pl_atual or pl_atual != pl_txt:
            # se votação melhor e conf ok, usa votação
            if conf_pl >= 0.35:
                if pl_atual and pl_atual != pl_txt and _placas_quase_iguais(pl_atual, pl_txt):
                    avisos.append(
                        f"placa: OCR mostrou {pl_atual} e {pl_txt} "
                        f"(parecidas) - escolhida {pl_txt} por votação"
                    )
                    duvida.append("placa")
                ex["placa"] = pl_txt
        conf["placa"] = conf_pl
        if outras and conf_pl < 0.7:
            avisos.append(
                f"placa: outras candidatas {', '.join(outras[:3])} - confira no documento"
            )
        if conf_pl < LIMIAR_CONFIANCA:
            duvida.append("placa")
    elif pl_atual:
        conf["placa"] = 0.5 if placa_formato_ok(pl_atual) else 0.25
        if conf["placa"] < LIMIAR_CONFIANCA:
            duvida.append("placa")
            avisos.append(f"placa {pl_atual} com confiança baixa")
    else:
        conf["placa"] = 0.0
        duvida.append("placa")
        avisos.append("placa vazia - confira no documento")

    # --- RENAVAM ---
    ren_txt, conf_ren, av_ren = extrair_renavam_melhor(texto or "")
    ren_atual = so_digitos(str(ex.get("renavam") or ""))
    if ren_txt:
        if not ren_atual or ren_atual != ren_txt:
            if conf_ren >= conf.get("renavam", 0) or not ren_atual:
                if ren_atual and ren_atual != ren_txt:
                    avisos.append(
                        f"renavam: local tinha {ren_atual}, votação prefere {ren_txt}"
                    )
                    duvida.append("renavam")
                ex["renavam"] = ren_txt
        conf["renavam"] = conf_ren
    elif ren_atual:
        conf["renavam"] = 0.7 if renavam_dv_ok(ren_atual) else 0.3
        if not renavam_dv_ok(ren_atual):
            avisos.append(f"renavam {ren_atual} DV inválido - confira")
            duvida.append("renavam")
    else:
        conf["renavam"] = 0.0
        duvida.append("renavam")
    avisos.extend(av_ren)
    if conf.get("renavam", 0) < LIMIAR_CONFIANCA and "renavam" not in duvida:
        duvida.append("renavam")

    # --- CHASSI ---
    ch_txt, conf_ch, av_ch = extrair_chassi_melhor(texto or "")
    ch_bruto = re.sub(r"[^A-Za-z0-9]", "", str(ex.get("chassi") or "")).upper()
    # numérico 11–14 não passa por _norm_vin (evita distorcer chassi de carreta)
    if ch_bruto.isdigit() and 11 <= len(ch_bruto) <= 14:
        ch_atual = ch_bruto
    else:
        ch_atual = _norm_vin(str(ex.get("chassi") or ""))
    if ch_txt:
        ch_txt_n = (
            ch_txt
            if (str(ch_txt).isdigit() and 11 <= len(str(ch_txt)) <= 14)
            else _norm_vin(ch_txt)
        )
        if not ch_atual or ch_atual != ch_txt_n:
            # NUNCA trocar numérico bom (carreta) por VIN OCR de baixa conf
            atual_num = ch_atual.isdigit() and 11 <= len(ch_atual) <= 14
            novo_vin = len(ch_txt_n) == 17 and not ch_txt_n.isdigit()
            if atual_num and novo_vin and conf_ch < 0.7:
                avisos.append(
                    f"chassi: mantido numérico {ch_atual} "
                    f"(ignorado VIN OCR fraco {ch_txt_n})"
                )
                conf["chassi"] = max(conf.get("chassi", 0.7), 0.7)
            else:
                preferir = (
                    conf_ch >= conf.get("chassi", 0)
                    or not ch_atual
                    or (
                        len(ch_atual) == 17
                        and ch_txt_n.isdigit()
                        and 11 <= len(ch_txt_n) <= 14
                        and conf_ch >= 0.5
                    )
                )
                # VIN atual fraco -> numérico novo
                if (
                    len(ch_atual) == 17
                    and ch_txt_n.isdigit()
                    and 11 <= len(ch_txt_n) <= 14
                ):
                    preferir = True
                if preferir:
                    if ch_atual and ch_atual != ch_txt_n:
                        avisos.append(
                            f"chassi: OCR local duvidoso ({ch_atual}) -> "
                            f"ajustado com 2ª leitura ({ch_txt_n})"
                        )
                        if len(ch_atual) == 17 and ch_txt_n.isdigit():
                            duvida.append("chassi")
                        elif len(ch_atual) == 17 and len(ch_txt_n) == 17 and _chassi_quase(
                            ch_atual, ch_txt_n
                        ):
                            duvida.append("chassi")
                    ex["chassi"] = ch_txt_n
                    conf["chassi"] = conf_ch
                else:
                    conf["chassi"] = conf.get("chassi", conf_ch)
        else:
            conf["chassi"] = max(conf.get("chassi", 0), conf_ch)
    elif ch_atual:
        if ch_atual.isdigit() and 11 <= len(ch_atual) <= 14:
            conf["chassi"] = 0.7
        else:
            conf["chassi"] = 0.55 if _vin_ok_basico(ch_atual) else 0.25
        if conf["chassi"] < LIMIAR_CONFIANCA:
            duvida.append("chassi")
    else:
        conf["chassi"] = 0.0
        duvida.append("chassi")
    avisos.extend(av_ch)
    if conf.get("chassi", 0) < LIMIAR_CONFIANCA and "chassi" not in duvida:
        duvida.append("chassi")

    # --- MARCA (lixo OCR colado) ---
    mmv = (
        ex.get("marca_modelo_versao")
        or ex.get("marca")
        or ex.get("modelo")
        or ""
    )
    mmv_s = str(mmv or "").strip()
    if mmv_s and re.search(
        r"\.\s*(OO|O0|0O|00|O+)?\s*ENA\b|\bRANDOM\b|\s\.\s+[A-Z]{1,4}\s*$",
        mmv_s,
        re.I,
    ):
        try:
            from ocr.parsers_locais import _limpar_marca_sem_especie

            limpa = _limpar_marca_sem_especie(mmv_s)
            if limpa and limpa.upper() != mmv_s.upper():
                avisos.append(f"marca: limpa de lixo OCR -> {limpa}")
                ex["marca_modelo_versao"] = limpa
                ex["marca"] = limpa
                ex["modelo"] = limpa
                mmv_s = limpa
        except Exception:
            pass
        # ainda suspeito -> Gemini
        if re.search(r"\bENA\b|\bRANDOM\b", mmv_s, re.I) or len(mmv_s) > 45:
            duvida.append("marca_modelo_versao")
            conf["marca_modelo_versao"] = 0.3
            avisos.append(f"marca com lixo OCR ({mmv_s[:40]}) - confira")
    elif mmv_s:
        conf["marca_modelo_versao"] = conf.get("marca_modelo_versao", 0.75)

    # prop nome/cpf leves
    pn = (ex.get("proprietario_nome") or "").strip()
    if not pn or len(pn) < 5:
        duvida.append("proprietario_nome")
        conf["proprietario_nome"] = 0.2
        avisos.append("nome do proprietário fraco/vazio - confira")
    else:
        conf["proprietario_nome"] = conf.get("proprietario_nome", 0.7)

    doc = so_digitos(str(ex.get("proprietario_cpf_cnpj") or ""))
    if len(doc) not in (11, 14):
        duvida.append("proprietario_cpf_cnpj")
        conf["proprietario_cpf_cnpj"] = 0.2
        avisos.append("CPF/CNPJ do proprietário incompleto - confira")
    else:
        conf["proprietario_cpf_cnpj"] = conf.get("proprietario_cpf_cnpj", 0.75)

    # dedupe
    duvida = list(dict.fromkeys(duvida))
    avisos = list(dict.fromkeys(a for a in avisos if a))

    ex["_confianca"] = conf
    ex["_duvida"] = duvida
    ex["_avisos_ocr"] = avisos
    ex["_precisa_gemini"] = bool(duvida) or any(
        conf.get(k, 1) < LIMIAR_CONFIANCA for k in ("placa", "renavam", "chassi")
    )
    return ex


def avaliar_extracao_cnh(ex: Dict[str, Any]) -> Dict[str, Any]:
    """Marca dúvidas básicas em CNH (sem reparse pesado)."""
    avisos: List[str] = list(ex.get("_avisos_ocr") or [])
    conf: Dict[str, float] = dict(ex.get("_confianca") or {})
    duvida: List[str] = []

    for k, label in (
        ("nome", "nome"),
        ("cpf", "CPF"),
        ("cnh", "nº CNH"),
        ("categoria_cnh", "categoria CNH"),
        ("validade_cnh", "validade CNH"),
    ):
        v = (ex.get(k) or "").strip() if isinstance(ex.get(k), str) else ex.get(k)
        if not v:
            duvida.append(k)
            conf[k] = 0.0
            avisos.append(f"{label} vazio - confira no documento")
        elif k == "categoria_cnh" and v == "AB":
            # Para motoristas de caminhão, AB é raro e o Tesseract frequentemente lê AE como AB.
            # Colocamos em dúvida para o Gemini Vision confirmar a letra real.
            duvida.append(k)
            conf[k] = 0.4
            avisos.append(f"categoria AB detectada (pode ser AE) - confirmando com IA")
        else:
            conf[k] = conf.get(k, 0.75)

    cpf = so_digitos(str(ex.get("cpf") or ""))
    if cpf and len(cpf) != 11:
        duvida.append("cpf")
        conf["cpf"] = 0.3
        avisos.append("CPF com tamanho inválido - confira")

    duvida = list(dict.fromkeys(duvida))
    avisos = list(dict.fromkeys(avisos))
    ex["_confianca"] = conf
    ex["_duvida"] = duvida
    ex["_avisos_ocr"] = avisos
    ex["_precisa_gemini"] = bool(duvida)
    return ex


def campo_duvidoso(ex: Dict[str, Any], campo: str) -> bool:
    if campo in (ex.get("_duvida") or []):
        return True
    conf = (ex.get("_confianca") or {}).get(campo)
    if conf is not None and conf < LIMIAR_CONFIANCA:
        return True
    return False


def deve_chamar_gemini(ex: Dict[str, Any], tipo: str = "") -> bool:
    if ex.get("_erro") or ex.get("_ignorar"):
        return False
    if ex.get("_precisa_gemini"):
        return True
    if ex.get("_duvida"):
        return True
    # vazio crítico
    t = (tipo or ex.get("_tipo") or "").lower()
    if t == "crlv":
        for k in ("placa", "renavam", "chassi", "proprietario_nome"):
            if not ex.get(k):
                return True
    if t == "cnh":
        for k in ("nome", "cpf", "cnh"):
            if not ex.get(k):
                return True
    return False


def mesclar_campo_com_duvida(
    cur: Dict[str, Any],
    novo: Dict[str, Any],
    campo: str,
) -> bool:
    """
    Preenche vazio OU sobrescreve se cur está duvidoso e novo tem valor.
    Retorna True se alterou.
    """
    v_novo = novo.get(campo)
    if v_novo in (None, "", False, []):
        return False
    v_cur = cur.get(campo)
    if not v_cur:
        cur[campo] = v_novo
        return True
    if campo_duvidoso(cur, campo) and str(v_novo).strip() != str(v_cur).strip():
        cur[campo] = v_novo
        # limpa dúvida desse campo se novo veio
        duv = list(cur.get("_duvida") or [])
        if campo in duv:
            duv.remove(campo)
        cur["_duvida"] = duv
        avisos = list(cur.get("_avisos_ocr") or [])
        avisos.append(
            f"{campo}: OCR local duvidoso ({v_cur}) -> ajustado com 2ª leitura ({v_novo})"
        )
        # se ainda pode estar errado
        if campo in ("placa", "renavam", "chassi"):
            avisos.append(f"{campo}: confira o valor final {v_novo} no documento")
        cur["_avisos_ocr"] = list(dict.fromkeys(avisos))
        return True
    return False


def coletar_avisos_caso(extracoes: Dict[str, List[Dict]]) -> List[str]:
    """Lista plana de avisos de todas as extrações."""
    out: List[str] = []
    for tipo, lista in (extracoes or {}).items():
        for ex in lista or []:
            arq = ""
            try:
                from pathlib import Path

                arq = Path(ex.get("_arquivo") or "").name
            except Exception:
                arq = str(ex.get("_arquivo") or "")
            for a in ex.get("_avisos_ocr") or []:
                pref = f"[{tipo}/{arq}] " if arq else f"[{tipo}] "
                out.append(pref + a)
            for d in ex.get("_duvida") or []:
                msg = f"campo '{d}' com baixa confiança - confirme antes do GW"
                full = (f"[{tipo}/{arq}] " if arq else f"[{tipo}] ") + msg
                if full not in out:
                    out.append(full)
    return out


def resumo_confianca(ex: Dict[str, Any]) -> str:
    conf = ex.get("_confianca") or {}
    if not conf:
        return ""
    parts = [f"{k}={v:.0%}" for k, v in sorted(conf.items()) if k in (
        "placa", "renavam", "chassi", "cpf", "nome", "cnh"
    )]
    return ", ".join(parts)
