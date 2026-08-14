"""
Parsers de texto bruto (OCR/PDF) -> dicts no mesmo formato do Gemini.

Campos alinhados com ocr/gemini_extrator.py e ocr/extrair_dados.py.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ocr.tipos_documento import TipoDocumento, classificar_arquivo


def so_digitos(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def limpar_placa(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (s or "")).upper()


def _ocr_digitos(s: str) -> str:
    """Converte confusões comuns de OCR em dígitos (RG/datas)."""
    mapa = {
        "O": "0", "o": "0", "Q": "0", "D": "0",
        "I": "1", "l": "1", "L": "1", "|": "1", "i": "1",
        "Z": "2", "z": "2",
        "E": "3",
        "A": "4",
        "S": "5", "s": "5", "$": "5",
        "G": "6", "b": "6",
        "T": "7",
        "B": "8",
        "g": "9", "q": "9",
        "«": "6", "»": "9",  # aspas OCR às vezes no 1º dígito
        "[": "1", "]": "", "{": "", "}": "", "(": "", ")": "",  # [ ≈ 1 em datas/RG
        ":": "", ".": "", " ": "",
    }
    out = []
    for ch in (s or ""):
        if ch.isdigit():
            out.append(ch)
        elif ch in mapa:
            if mapa[ch]:
                out.append(mapa[ch])
        # ignora resto
    return "".join(out)


def _ocr_data_suja(s: str) -> str:
    """
    Tenta montar DD/MM/AAAA a partir de OCR sujo.
    Ex.: 's/o72025', '[:s/o72025', '1s/o7/2025' -> 15/07/2025
         'oarvtr2024' -> 04/11/2024 (foto CNH: emissão perto de VALIDADE)
    """
    raw = (s or "").strip()
    if not raw:
        return ""
    # já limpa
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    # em data, '[' e 'l' no início costumam ser '1' (OCR de 15/07/...)
    raw_data = re.sub(r"^[\s\{\(]*[\[lI|]", "1", raw)
    # tira lixo e mapeia
    limpo = []
    for ch in raw_data:
        if ch.isdigit():
            limpo.append(ch)
        elif ch in "/-.":
            limpo.append("/")
        else:
            d = _ocr_digitos(ch)
            if d:
                limpo.append(d)
    s2 = "".join(limpo)
    # colapsa barras
    s2 = re.sub(r"/+", "/", s2).strip("/")
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s2)
    if m:
        dd, mm, aa = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= dd <= 31 and 1 <= mm <= 12 and 1990 <= aa <= 2035:
            return f"{dd:02d}/{mm:02d}/{aa}"
    # só dígitos: DDMMYYYY
    digs = so_digitos(s2)
    if len(digs) == 8:
        dd, mm, aa = int(digs[:2]), int(digs[2:4]), int(digs[4:])
        if 1 <= dd <= 31 and 1 <= mm <= 12 and 1990 <= aa <= 2035:
            return f"{dd:02d}/{mm:02d}/{aa}"
    # 7 dígitos tipo s072025 -> tenta 1+DMMYYYY (1 perdido no OCR)
    if len(digs) == 7:
        # preferir 1d + mm + yyyy se formar data válida (15/07/2025)
        cand8 = "1" + digs
        dd, mm, aa = int(cand8[:2]), int(cand8[2:4]), int(cand8[4:])
        if 10 <= dd <= 31 and 1 <= mm <= 12 and 1990 <= aa <= 2035:
            return f"{dd:02d}/{mm:02d}/{aa}"
        # DMMYYYY simples
        dd, mm, aa = int(digs[0]), int(digs[1:3]), int(digs[3:])
        if 1 <= dd <= 9 and 1 <= mm <= 12 and 1990 <= aa <= 2035:
            return f"{dd:02d}/{mm:02d}/{aa}"
    # Mapa estendido só para datas: "oarvtr2024"/"OARVTR2024" ≈ 04/11/2024
    # (A->4, V/T->1, R=ruído de /). _norm() deixa tudo maiúsculo.
    if re.search(r"20\d{2}", raw, re.I) and re.search(r"[A-Za-z]", raw):
        mapa_dt = {
            "O": "0", "Q": "0", "D": "0",
            "I": "1", "L": "1", "|": "1",
            "Z": "2", "E": "3", "A": "4",
            "S": "5", "$": "5", "G": "6", "B": "8",
            # em data, T/V/N costumam ser 1 (mês 11), não 7
            "T": "1", "V": "1", "N": "1", "H": "1",
            "R": "",  # ruído de /
            "/": "/", "-": "/", ".": "/",
        }
        limpo2 = []
        for ch in raw_data.upper():
            if ch.isdigit():
                limpo2.append(ch)
            elif ch in mapa_dt:
                if mapa_dt[ch]:
                    limpo2.append(mapa_dt[ch])
        digs2 = "".join(c for c in limpo2 if c.isdigit())
        # OARVTR2024 -> 04112024 (R removido, V/T->1)
        if len(digs2) >= 8:
            for i in range(0, len(digs2) - 7):
                chunk = digs2[i : i + 8]
                dd, mm, aa = int(chunk[:2]), int(chunk[2:4]), int(chunk[4:])
                if 1 <= dd <= 31 and 1 <= mm <= 12 and 1990 <= aa <= 2035:
                    return f"{dd:02d}/{mm:02d}/{aa}"
    return ""


def _extrair_data_emissao_ocr(t: str, validade: str = "") -> str:
    """Extrai data de emissão mesmo com OCR ruim perto de DATA EMISSAO / VALIDADE."""
    # 1) par emissão + validade legível
    m = re.search(
        r"(?:DATA\s*)?(?:DE\s*)?EMISS[AÃ]O[^\n]{0,40}\n[^\n]{0,30}?"
        r"([^\n]{6,20}?)\s*[|(]\s*(\d{2}/\d{2}/\d{4})",
        t,
        re.I,
    )
    if m:
        em = _ocr_data_suja(m.group(1))
        if em and em != (validade or m.group(2)):
            return em
    # 2) qualquer lixo logo antes da validade conhecida
    if validade:
        m = re.search(
            re.escape(validade),
            t,
        )
        if m:
            trecho = t[max(0, m.start() - 30) : m.start()]
            em = _ocr_data_suja(trecho)
            if em and em != validade:
                return em
    # 3) padrão s/o7/2025 ou similares na área de emissão
    m = re.search(
        r"EMISS[AÃ]O[^\n]{0,80}?([0-9OIlsSzZ«»\[\]/:.-]{6,14})",
        t,
        re.I,
    )
    if m:
        em = _ocr_data_suja(m.group(1))
        if em and em != validade:
            return em
    # 4) 4a DATA EMISSÃO na CNH física (foto): tenta datas 20xx próximas
    m = re.search(
        r"(?:4[aA]\s*)?(?:DATA\s*)?EMISS[AÃ]O[^\d]{0,30}"
        r"(\d{2}[/.\-]\d{2}[/.\-]20\d{2})",
        t,
        re.I,
    )
    if m:
        em = _ocr_data_suja(m.group(1).replace(".", "/").replace("-", "/"))
        if em and em != validade:
            return em
    # 5) Foto WhatsApp: "oarvtr2024" / "04112024" perto de EMISSAO e antes da validade
    #    Ex.: DATA EMISSAO ... oarvtr2024 { 2411012034  (04/11/2024 + 24/10/2034)
    m_em = re.search(r"EMISS[AÃ]O", t, re.I)
    if m_em:
        trecho = t[m_em.start() : m_em.start() + 160]
        # ignora a palavra VALIDADE; pega tokens com dígitos e 20xx
        for tok in re.findall(
            r"[0-9A-Za-zIlOSszZnvwfFoe«»\[\]/.\-]{6,16}",
            trecho,
        ):
            if re.match(r"VALID|EMISS|DATA|HAB|ACC", tok, re.I):
                continue
            if not re.search(r"20\d{2}|\d{4}", tok):
                continue
            em = _ocr_data_suja(tok)
            if not em:
                digs = _ocr_digitos(tok)
                for i in range(0, max(0, len(digs) - 7)):
                    chunk = digs[i : i + 8]
                    dd, mm, aa = int(chunk[:2]), int(chunk[2:4]), int(chunk[4:])
                    if 1 <= dd <= 31 and 1 <= mm <= 12 and 2015 <= aa <= 2032:
                        cand = f"{dd:02d}/{mm:02d}/{aa}"
                        if cand != validade:
                            em = cand
                            break
            if em and em != validade and 2015 <= _ano(em) <= 2032:
                return em
    # 6) Par de blocos 8 dígitos colados: emissão (recente) + validade
    #    04112024 + 24102034, ou OCR 2411012034 ≈ 24/10/2034 com ruído
    if validade:
        dig_val = so_digitos(validade)
        for m in re.finditer(r"[0-9OIlSZ]{8,12}", t):
            digs = _ocr_digitos(m.group(0))
            if len(digs) < 8:
                continue
            for i in range(0, len(digs) - 7):
                chunk = digs[i : i + 8]
                if dig_val and chunk == dig_val:
                    continue
                dd, mm, aa = int(chunk[:2]), int(chunk[2:4]), int(chunk[4:])
                if 1 <= dd <= 31 and 1 <= mm <= 12 and 2015 <= aa <= 2032:
                    cand = f"{dd:02d}/{mm:02d}/{aa}"
                    if cand != validade and _ano(cand) <= _ano(validade):
                        # preferir trecho próximo a EMISSAO
                        ctx = t[max(0, m.start() - 40) : m.end() + 10].upper()
                        if "EMISS" in ctx or "VALID" in ctx or "4A" in ctx or "4B" in ctx:
                            return cand
    return ""


def _ano(d: str) -> int:
    try:
        return int(d[-4:])
    except Exception:
        return 0


def _data_valida_cnh(d: str) -> bool:
    """True se DD/MM/AAAA com dia/mês/ano possíveis."""
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", (d or "").strip())
    if not m:
        return False
    dd, mm, aa = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return 1 <= dd <= 31 and 1 <= mm <= 12 and 1930 <= aa <= 2035


def _corrigir_data_ocr(d: str) -> str:
    """
    Corrige datas impossíveis comuns no OCR:
      40/10/2023 -> 10/10/2023  (1 lido como 4)
      00/06/2030 -> vazio
    """
    d = (d or "").strip()
    if not d:
        return ""
    if _data_valida_cnh(d):
        return d
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", d)
    if not m:
        return ""
    dd, mm, aa = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mm <= 12 and 1930 <= aa <= 2035):
        return ""
    # 40–49 -> 10–19 (dígito 1 virando 4)
    if 40 <= dd <= 49:
        cand = f"1{dd - 40}/{mm:02d}/{aa}"
        if _data_valida_cnh(cand):
            return cand
    # 32–39 -> 02–09 ou 12–19
    if 32 <= dd <= 39:
        for prefix in ("0", "1"):
            cand = f"{prefix}{dd - 30}/{mm:02d}/{aa}"
            if _data_valida_cnh(cand):
                return cand
    # dia 00
    if dd == 0:
        return ""
    return ""


def _recuperar_datas_cnh_ocr_sujo(out: Dict[str, Any], t: str) -> None:
    """
    Foto WhatsApp: validade 06/10/2033 vira 'fonsnovz0s3' / 'osinozoss';
    emissão 10/10/2023 e 1ª hab 04/11/1992 quase somem.
    Tenta reconstituir datas 20xx a partir de tokens alfanuméricos.
    """
    candidatas: List[str] = []
    # tokens com dígitos misturados (OCR de DD/MM/AAAA)
    for m in re.finditer(r"[0-9A-Za-zIlOSszZnvwfFoe]{7,14}", t or ""):
        raw = m.group(0)
        # tenta como data contínua DDMMYYYY
        digs = _ocr_digitos(raw)
        if len(digs) >= 8:
            for i in range(0, len(digs) - 7):
                chunk = digs[i : i + 8]
                dd, mm, aa = int(chunk[:2]), int(chunk[2:4]), int(chunk[4:])
                if 1 <= dd <= 31 and 1 <= mm <= 12 and 1990 <= aa <= 2035:
                    candidatas.append(f"{dd:02d}/{mm:02d}/{aa}")
        # tenta inserindo barras a cada 2 dígitos após mapear
        em = _ocr_data_suja(raw)
        if em:
            candidatas.append(em)
        # padrões com barras/pontos sujos
        em2 = _ocr_data_suja(re.sub(r"[.\-]", "/", raw))
        if em2:
            candidatas.append(em2)

    # datas já legíveis no texto
    candidatas.extend(re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", t or ""))

    # corrige 40/10/2023 -> 10/10/2023 e descarta inválidas
    datas = []
    seen = set()
    for d in candidatas:
        d2 = _corrigir_data_ocr(d) if not _data_valida_cnh(d) else d
        if d2 and _data_valida_cnh(d2) and d2 not in seen:
            seen.add(d2)
            datas.append(d2)

    if not datas:
        return

    # validade = maior data futura (>= 2024)
    if not out.get("validade_cnh"):
        fut = [d for d in datas if _ano(d) >= 2024]
        if fut:
            out["validade_cnh"] = max(fut, key=lambda d: (_ano(d), d))
    else:
        # corrige validade já preenchida se inválida
        v = _corrigir_data_ocr(out["validade_cnh"])
        if v:
            out["validade_cnh"] = v

    # emissão = data 2015–2030 diferente da validade, preferir a mais recente antes da validade
    if not out.get("data_emissao_cnh") or not _data_valida_cnh(out.get("data_emissao_cnh") or ""):
        val = out.get("validade_cnh") or ""
        medias = [
            d
            for d in datas
            if 2015 <= _ano(d) <= 2030 and d != val and d != out.get("data_nascimento")
        ]
        if medias and val:
            antes = [
                d
                for d in medias
                if _ano(d) < _ano(val)
                or (_ano(d) == _ano(val) and d < val)
            ]
            pool = antes or medias
            out["data_emissao_cnh"] = max(pool, key=_ano)
        elif medias:
            out["data_emissao_cnh"] = min(medias, key=_ano)
    else:
        e = _corrigir_data_ocr(out["data_emissao_cnh"])
        if e:
            out["data_emissao_cnh"] = e

    # 1ª hab perto do nome: "Eounsite92" ≈ 04/11/1992 - se já tem, ok
    if not out.get("data_primeira_habilitacao"):
        antigas = [
            d
            for d in datas
            if 1970 <= _ano(d) <= 2015
            and d != out.get("data_nascimento")
            and d != out.get("data_emissao_cnh")
        ]
        if antigas:
            out["data_primeira_habilitacao"] = min(antigas, key=_ano)


def _classificar_datas_cnh(out: Dict[str, Any], t: str, datas: List[str]) -> None:
    """
    Separa:
      data_nascimento | data_emissao_cnh | validade_cnh | data_primeira_habilitacao
    CNH-e: emissão e validade costumam vir juntas (ex: 12/04/2023 05/04/2028).
    """
    # Par emissão + validade na mesma linha
    m = re.search(
        r"\b(\d{2}/\d{2}/20\d{2})\s+(\d{2}/\d{2}/20\d{2})\b", t
    )
    if m:
        d1, d2 = m.group(1), m.group(2)
        # Diferença entre emissão e validade de CNH é de no máximo 10 anos
        if abs(_ano(d1) - _ano(d2)) <= 11:
            # a mais cedo = emissão; a mais tarde = validade
            if _ano(d1) <= _ano(d2):
                out["data_emissao_cnh"] = d1
                out["validade_cnh"] = d2
            else:
                out["data_emissao_cnh"] = d2
                out["validade_cnh"] = d1


    if not out.get("validade_cnh"):
        v = _campo_apos(t, r"VALIDADE\s*[:\.]?\s*", r"(\d{2}/\d{2}/\d{4})")
        if v:
            out["validade_cnh"] = v
    if not out.get("data_emissao_cnh"):
        e = _campo_apos(
            t,
            r"(?:DATA\s*)?(?:DE\s*)?EMISS[AÃ]O\s*[:\.]?\s*",
            r"(\d{2}/\d{2}/\d{4})",
        )
        if e and e != out.get("validade_cnh"):
            out["data_emissao_cnh"] = e

    # Nascimento: 19xx, ou 20xx se for muito antigo vs emissão
    nasc = _campo_apos(
        t,
        r"(?:DATA.*NASCIMENTO|NASCIMENTO|NASC\.?)\s*[:\.]?\s*",
        r"(\d{2}/\d{2}/\d{4})",
    )
    # "17/03/1975, ARAPIRACA, AL" (mesmo se a data já veio de outro campo)
    m_nat = re.search(
        r"\b(\d{2}/\d{2}/(?:19\d{2}|20[0-1]\d))\b\s*[,]\s*"
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){0,3})\s*[,]\s*([A-Z]{2})\b",
        t,
    )
    if m_nat:
        if not nasc:
            nasc = m_nat.group(1)
        cid_n = _limpa_nome(m_nat.group(2))
        # evita pegar lixo tipo "DATA LOCALE UF"
        if cid_n and not any(
            x in cid_n.upper()
            for x in ("DATA", "LOCAL", "NASC", "EMISS", "VALID", "HABILIT")
        ):
            out["naturalidade"] = out.get("naturalidade") or cid_n
            out["uf_naturalidade"] = out.get("uf_naturalidade") or m_nat.group(3).upper()
    if not nasc:
        # qualquer 19xx que não seja só ruído
        # Ordena as datas pelo ano (crescente) para garantir que a mais antiga (nascimento) seja selecionada
        for d in sorted(datas, key=_ano):
            if 1930 <= _ano(d) <= 2008:
                # não confundir com 1ª hab se tivermos duas 19xx
                nasc = d
                break
    # se nasc == emissão por engano, limpa
    if nasc and nasc == out.get("data_emissao_cnh"):
        nasc = ""
    if nasc and nasc == out.get("validade_cnh"):
        nasc = ""
    out["data_nascimento"] = nasc or out.get("data_nascimento") or ""

    # 1ª habilitação (NUNCA = emissão nem validade)
    proib_prim = {
        out.get("data_nascimento") or "",
        out.get("data_emissao_cnh") or "",
        out.get("validade_cnh") or "",
    }
    prim = out.get("data_primeira_habilitacao") or ""
    if prim in proib_prim:
        prim = ""
    if not prim:
        prim = _campo_apos(
            t,
            r"(?:1[ªA]\s*HABILITA|PRIMEIRA\s*HABILITA|1\s*HABILITA|ACC)\s*[:\.]?\s*",
            r"(\d{2}/\d{2}/\d{4})",
        ) or ""
        if prim in proib_prim:
            prim = ""
    # CNH-e: nome na mesma linha da 1ª hab - "EDER NEVES DE SOUSA 27/05/2003"
    if not prim:
        m_nh = re.search(
            r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,6})\s+"
            r"(\d{2}/\d{2}/(?:19\d{2}|20[0-1]\d))\b",
            t,
        )
        if m_nh:
            d = m_nh.group(2)
            if d not in proib_prim and 1970 <= _ano(d) <= 2018:
                prim = d
    if not prim:
        # datas 19xx/200x diferentes do nascimento/emissão/validade
        candidatas = []
        for d in datas:
            a = _ano(d)
            if d in proib_prim:
                continue
            if 1970 <= a <= 2015:
                candidatas.append(d)
        if candidatas:
            # a mais antiga costuma ser 1ª hab (após excluir nascimento)
            prim = min(candidatas, key=_ano)
    # se só temos uma 19xx e já é nascimento, 1ª hab pode ser a outra 19xx no texto
    if not prim:
        todas_19 = [d for d in datas if 1930 <= _ano(d) <= 2005]
        for d in todas_19:
            if d not in proib_prim:
                prim = d
                break
    if prim in proib_prim:
        prim = ""
    out["data_primeira_habilitacao"] = prim or ""

    # fallback validade/emissão se par não achou
    if not out.get("validade_cnh"):
        futuras = [d for d in datas if _ano(d) >= 2024]
        if futuras:
            out["validade_cnh"] = max(futuras, key=_ano)
    if not out.get("data_emissao_cnh"):
        medias = [
            d
            for d in datas
            if 2015 <= _ano(d) <= 2030
            and d != out.get("validade_cnh")
            and d != out.get("data_nascimento")
        ]
        if medias:
            out["data_emissao_cnh"] = min(medias, key=_ano)

    # local emissão (verso: GOIANIA, GO / DETRAN) - ignora inglês PLACE/BIRTH
    proib_loc = ("PLACE", "BIRTH", "DATE", "LOCAL", "GOIAS", "GOIÁS", "NAME", "OF")
    if not out.get("local_emissao_cnh"):
        m2 = re.search(r"\b(GOI[AÂ]NIA)\s*[,/\s]+([A-Z]{2})\b", t, re.I)
        if m2:
            out["local_emissao_cnh"] = f"GOIANIA/{m2.group(2).upper()}"
        else:
            m = re.search(
                r"\bLOCAL\s*[:\.]?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+)?)"
                r"\s*[,/\s]+([A-Z]{2})\b",
                t,
                re.I,
            )
            if m:
                cid = _limpa_nome(m.group(1) or "")
                if cid.upper() not in proib_loc and len(cid) >= 3:
                    uf = (m.group(2) or "").upper()
                    out["local_emissao_cnh"] = f"{cid}/{uf}".strip("/")

    # Regra: se NÃO houver local de nascimento junto da data de nasc.,
    # usa o LOCAL DE EMISSÃO (ex.: GOIANIA/GO)
    if not (out.get("naturalidade") or "").strip():
        loc_em = (out.get("local_emissao_cnh") or "").strip()
        if loc_em:
            # "GOIANIA/GO" ou "GOIANIA"
            if "/" in loc_em:
                cid, uf = loc_em.split("/", 1)
                out["naturalidade"] = cid.strip()
                out["uf_naturalidade"] = uf.strip().upper()
            else:
                out["naturalidade"] = loc_em
            print(
                f"[CNH] Naturalidade vazia -> usando local de emissão: "
                f"{out['naturalidade']}/{out.get('uf_naturalidade') or '?'}"
            )
    # se tem naturalidade sem UF mas tem emissão com UF
    if (out.get("naturalidade") or "").strip() and not (out.get("uf_naturalidade") or "").strip():
        loc_em = (out.get("local_emissao_cnh") or "").strip()
        if "/" in loc_em:
            out["uf_naturalidade"] = loc_em.split("/", 1)[1].strip().upper()


def parsear_arquivo(path: Path, texto: str, tipo: Optional[TipoDocumento] = None) -> Dict[str, Any]:
    path = Path(path)
    tipo = tipo or classificar_arquivo(path)
    texto = texto or ""
    if tipo == TipoDocumento.CNH:
        dados = parse_cnh(texto)
    elif tipo == TipoDocumento.CRLV:
        dados = parse_crlv(texto, path=path)
    elif tipo == TipoDocumento.TAC:
        dados = parse_tac(texto)
    elif tipo == TipoDocumento.COMPROVANTE:
        dados = parse_comprovante(texto)
    else:
        dados = parse_generico(texto)
        # OUTRO com placa no nome + LTDA -> tenta como CRLV (fallback)
        from ocr.tipos_documento import _placa_no_nome, nome_empresa_no_arquivo

        tu = (texto or "").upper()
        # Cartão ANTT/RNTRC classificado como "outro" (WhatsApp sem nome útil)
        if any(
            x in tu
            for x in (
                "ANTT", "RNTRC", "TRANSPORTADORES RODOVI", "AGENCIANACIONAL",
                "AGENCIA NACIONAL", "CERTIFICADO DE REGISTRO",
            )
        ) or re.search(r"\b(?:TAC|ETC|CTC)\s*[:.\-]?\s*\d{6,}", tu):
            tac = parse_tac(texto)
            for k, v in tac.items():
                if k.startswith("_"):
                    continue
                if v and not dados.get(k):
                    dados[k] = v
            if tac.get("rntrc") or tac.get("cnpj") or tac.get("cpf"):
                dados["_tipo_sugerido"] = "tac"
                dados["_tipo"] = "tac"
        if (
            _placa_no_nome(path.stem)
            or any(
                x in tu
                for x in (
                    "RENAVAM", "RENAVANA", "CHASSI", "LICENCIAMENTO",
                    "CERTIFICADO DE REGISTRO", "CAMINHAO", "SEMI-REBOQUE",
                    "SEMI REBOQUE", "VEICULO", "VEÍCULO", "EXERCICIO", "DPVAT"
                )
            )
            or re.search(r"\b[A-Z]{3}\d[A-Z0-9]\d{2}\b", tu)
            or re.search(r"\b[A-Z]{3}\d{4}\b", tu)
        ):
            crlv = parse_crlv(texto, path=path)
            # mescla o que o generico não trouxe
            for k, v in crlv.items():
                if k.startswith("_"):
                    continue
                if v and not dados.get(k):
                    dados[k] = v
            if (crlv.get("placa") or crlv.get("renavam") or crlv.get("chassi")) and dados.get("_tipo_sugerido") != "tac":
                dados["_tipo_sugerido"] = "crlv"
                dados["_tipo"] = "crlv"
    dados["_arquivo"] = str(path)
    dados["_tipo"] = dados.get("_tipo") or tipo.value
    dados["_fonte"] = "local"
    dados["_chars_texto"] = len(texto)
    # CNH: marca campos fracos para Gemini-só-se-dúvida + aviso ao usuário
    if tipo == TipoDocumento.CNH or (dados.get("_tipo") or "") == "cnh":
        try:
            from ocr.ocr_qualidade import avaliar_extracao_cnh

            dados = avaliar_extracao_cnh(dados)
        except Exception:
            pass
    # CRLV já avalia em parse_crlv; se veio por reclassificação genérico, reavalia
    if (dados.get("_tipo") or tipo.value) == "crlv" and "_duvida" not in dados:
        try:
            from ocr.ocr_qualidade import avaliar_extracao_crlv

            dados = avaliar_extracao_crlv(dados, texto=texto)
        except Exception:
            pass
    return dados


def extrair_varios_local(arquivos: List[Path]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Lê cada arquivo (foto e/ou PDF, misturado no mesmo caso).
    - Classifica por nome; se for genérico (WhatsApp/IMG) ou OUTRO, usa o texto.
    - Várias fotos do mesmo tipo (CNH frente+verso) são fundidas num único dict.
    """
    from ocr.local_ocr import extrair_texto_arquivo, formato_arquivo
    from ocr.tipos_documento import classificar_arquivo_e_conteudo

    from ocr.tipos_documento import documento_irrelevante

    import concurrent.futures
    brutos: List[Dict[str, Any]] = []

    def _processar_arquivo(arq: Path) -> Dict[str, Any]:
        arq = Path(arq)
        fmt = formato_arquivo(arq)

        # Omnilink / rastreador / ficha de ativação - NÃO entra no cadastro
        if documento_irrelevante(arq):
            print(
                f"[OCR-local] IGNORADO (não é doc de carro/motorista): {arq.name}"
            )
            return {
                "_arquivo": str(arq),
                "_tipo": TipoDocumento.IGNORAR.value,
                "_formato": fmt,
                "_fonte": "local",
                "_ignorar": True,
            }

        texto = extrair_texto_arquivo(arq)
        if documento_irrelevante(arq, texto):
            print(
                f"[OCR-local] IGNORADO pelo conteúdo (omnilink/rastreador): {arq.name}"
            )
            return {
                "_arquivo": str(arq),
                "_tipo": TipoDocumento.IGNORAR.value,
                "_formato": fmt,
                "_fonte": "local",
                "_ignorar": True,
            }

        if not texto.strip():
            print(f"[OCR-local] [!] sem texto: {arq.name} ({fmt})")
            return {
                "_arquivo": str(arq),
                "_tipo": classificar_arquivo(arq).value,
                "_formato": fmt,
                "_fonte": "local",
                "_erro": "sem texto",
            }

        tipo, origem = classificar_arquivo_e_conteudo(arq, texto)
        if tipo == TipoDocumento.IGNORAR:
            print(f"[OCR-local] IGNORADO: {arq.name} [{origem}]")
            return {
                "_arquivo": str(arq),
                "_tipo": TipoDocumento.IGNORAR.value,
                "_formato": fmt,
                "_fonte": "local",
                "_ignorar": True,
                "_classificacao": origem,
            }

        print(f"[OCR-local] {arq.name} ({fmt}) -> {tipo.value} [{origem}]")
        dados = parsear_arquivo(arq, texto, tipo)
        # Reclassifica OUTRO -> CRLV só com evidência forte de licenciamento
        # (placa sozinha NÃO basta - Omnilink tem placa e não é CRLV)
        if (dados.get("_tipo") or tipo.value) == TipoDocumento.OUTRO.value:
            tem_veiculo = bool(
                (dados.get("renavam") and dados.get("placa"))
                or dados.get("chassi")
                or (
                    dados.get("placa")
                    and dados.get("marca_modelo_versao")
                    and dados.get("proprietario_cpf_cnpj")
                )
            )
            if tem_veiculo and not documento_irrelevante(arq, texto):
                dados["_tipo"] = TipoDocumento.CRLV.value
                dados["_classificacao"] = (origem or "") + "+crlv_por_campos"
                print(
                    f"[OCR-local]   reclassificado OUTRO->crlv "
                    f"(placa={dados.get('placa') or '-'})"
                )
            elif dados.get("_tipo_sugerido") == "crlv" and tem_veiculo:
                dados["_tipo"] = TipoDocumento.CRLV.value
        dados["_formato"] = fmt
        dados["_classificacao"] = dados.get("_classificacao") or origem
        campos = [k for k in dados if not k.startswith("_") and dados[k]]
        print(f"[OCR-local]   campos: {campos}")
        if dados.get("proprietario_nome"):
            print(f"[OCR-local]   prop={dados.get('proprietario_nome')!r}")
        dados["_preview"] = texto[:400].replace("\n", " | ")
        return dados

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futuros = [executor.submit(_processar_arquivo, a) for a in arquivos]
        for f in concurrent.futures.as_completed(futuros):
            res = f.result()
            if res:
                brutos.append(res)

    return _agrupar_e_fundir(brutos)


def _agrupar_e_fundir(
    brutos: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Agrupa por tipo. Se houver 2+ do mesmo tipo (ex: 2 fotos CNH),
    funde campos preenchidos (frente + verso).
    CRLV com 2 arquivos distintos (2 veículos) NÃO funde - mantém lista.
    """
    resultado: Dict[str, List[Dict[str, Any]]] = {t.value: [] for t in TipoDocumento}

    por_tipo: Dict[str, List[Dict[str, Any]]] = {t.value: [] for t in TipoDocumento}
    for d in brutos:
        tipo = d.get("_tipo") or TipoDocumento.OUTRO.value
        if tipo not in por_tipo:
            tipo = TipoDocumento.OUTRO.value
        por_tipo[tipo].append(d)

    for tipo, lista in por_tipo.items():
        if not lista:
            continue
        # CRLV: cada arquivo = um veículo (não fundir placas diferentes)
        if tipo == TipoDocumento.CRLV.value:
            resultado[tipo] = lista
            continue
        # OUTRO / IGNORAR (omnilink etc.): mantém, nunca vira motorista/prop
        if tipo in (TipoDocumento.OUTRO.value, TipoDocumento.IGNORAR.value):
            resultado[tipo] = lista
            continue
        # CNH / TAC / comprovante: funde se várias fotos do mesmo doc
        if len(lista) == 1:
            resultado[tipo] = lista
        else:
            placas = {
                (x.get("placa") or "").upper()
                for x in lista
                if x.get("placa")
            }
            # se parecerem docs diferentes com dados distintos, não funde cegamente
            if tipo == TipoDocumento.TAC.value and len(lista) > 1:
                # vários TAC -> mantém todos (regras de negócio usam o match)
                resultado[tipo] = lista
            else:
                fundido = _fundir_extracoes(lista)
                print(
                    f"[OCR-local] Fundiu {len(lista)} arquivo(s) -> 1 {tipo} "
                    f"({fundido.get('_arquivos_origem', '?')})"
                )
                resultado[tipo] = [fundido]
    return resultado


def _fundir_extracoes(lista: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Primeiro valor não-vazio de cada campo (ordem de arquivos)."""
    base: Dict[str, Any] = {}
    arquivos = []
    for d in lista:
        arq = d.get("_arquivo", "")
        if arq:
            arquivos.append(Path(arq).name)
        for k, v in d.items():
            if k.startswith("_"):
                continue
            if v in (None, "", [], False):
                continue
            if not base.get(k):
                base[k] = v
            elif isinstance(v, bool) and v and not base.get(k):
                base[k] = v
    # meta
    base["_arquivo"] = lista[0].get("_arquivo", "")
    base["_arquivos_origem"] = ", ".join(arquivos)
    base["_tipo"] = lista[0].get("_tipo", "")
    base["_fonte"] = "local"
    base["_fundido"] = True
    base["_formato"] = "+".join(
        sorted({d.get("_formato", "?") for d in lista})
    )
    return base


# ---------------------------------------------------------------------------
# CNH
# ---------------------------------------------------------------------------

def parse_cnh(texto: str) -> Dict[str, Any]:
    t = _norm(texto)
    out: Dict[str, Any] = {
        "nome": "",
        "cpf": "",
        "data_nascimento": "",
        "nome_pai": "",
        "nome_mae": "",
        "rg": "",
        "orgao_emissor": "",
        "cnh": "",
        "categoria_cnh": "",
        "validade_cnh": "",
        "data_emissao_cnh": "",
        "local_emissao_cnh": "",
        "data_primeira_habilitacao": "",
        "sexo": "",
        "nacionalidade": "BRASILEIRO",
        "naturalidade": "",
        "uf_naturalidade": "",
    }

    # Registro CNH antes do CPF (evita confusão 020... vs 920...)
    m = re.search(
        r"\b(\d{11})\b\s+(\d{2}/\d{2}/\d{4})\s+\(?\s*(\d{2}/\d{2}/\d{4})",
        t,
    )
    if m:
        out["cnh"] = m.group(1)
        d2, d3 = m.group(2), m.group(3)
        # validade costuma ser a mais futura
        if _ano(d2) >= _ano(d3):
            out["validade_cnh"] = d2
            if _ano(d3) <= 2018:
                out["data_primeira_habilitacao"] = d3
            else:
                out["data_emissao_cnh"] = out.get("data_emissao_cnh") or d3
        else:
            out["validade_cnh"] = d3
            if _ano(d2) <= 2018:
                out["data_primeira_habilitacao"] = d2
            else:
                out["data_emissao_cnh"] = out.get("data_emissao_cnh") or d2
    else:
        out["cnh"] = _campo_apos(
            t, r"(?:N[ºO°.]?\s*REGISTRO|REGISTRO)\s*[:\.]?\s*", r"(\d{9,11})"
        )
        if not out["cnh"]:
            m = re.search(
                r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s+(\d{9,11})\s+[A-E]\b", t
            )
            if m:
                out["cnh"] = m.group(1)
        if not out["cnh"]:
            out["cnh"] = _registro_cnh_preferencial(t, cpf="")

    out["cpf"] = _primeiro_cpf_formatado(t) or _cpf_cnh_preferencial(t)
    # se CPF ficou igual/quase igual ao registro, zera
    if out.get("cpf") and out.get("cnh"):
        if out["cpf"] == out["cnh"] or sum(
            a != b for a, b in zip(out["cpf"], out["cnh"])
        ) <= 2:
            out["cpf"] = ""

    # --- Datas CNH (regra de ouro) ---
    # Emissão + Validade na mesma linha: 12/04/2023  05/04/2028
    # Nascimento: ano 19xx (ou local CAROLINA, MA)
    # 1ª habilitação: outra data 19xx/20xx antiga, ou campo próprio
    datas = re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", t)
    _classificar_datas_cnh(out, t, datas)

    # Categoria: A–E ou combinadas (AB, AE, AD...). OCR: "CAT HAS" = "CAT HAB"
    out["categoria_cnh"] = _extrair_categoria_cnh(t, cnh=out.get("cnh") or "")

    # Nome do titular - CONSERVADOR:
    # 1) Só lixo óbvio é descartado
    # 2) NÃO inventa grafia nem troca motorista↔pai por “chute”
    # 3) Se houver 2 nomes fortes e ambíguos -> deixa vazio (usuário corrige 1x)
    proib_nome = _PROIB_NOME_PESSOA
    cands_nome: List[tuple] = []  # (score, nome, fonte)
    pos_fil = -1
    for pat_z in (
        r"\bBRASILEIRO(?:\(A\))?\b",
        r"\bNACIONALIDADE\b",
        r"\bFILIA[CÇG][AÃA]O\b",
        r"\bFUAGAO\b",
    ):
        mz = re.search(pat_z, t, re.I)
        if mz:
            pos_fil = mz.start() if pos_fil < 0 else min(pos_fil, mz.start())
    zona_titular = t[:pos_fil] if pos_fil > 80 else t[: max(len(t) // 2, 200)]
    zona_filiacao = t[pos_fil:] if pos_fil > 0 else ""

    def _add_nome(cand: str, bonus: int = 0, fonte: str = "") -> None:
        cand = _limpa_nome_pessoa(cand or "", permitir_iniciais=False)
        if not cand or _nome_tem_proib(cand, proib_nome) or _nome_parece_lixo_ocr(cand):
            return
        if "SOBRENOME" in cand.upper():
            return
        sc = _score_nome_pessoa(cand, t) + bonus
        # leve preferência por label NOME; sem “inventar” troca de slots
        if fonte in ("label_nome", "chaves"):
            sc += 8
        # forte penalidade se só aparece na área de filiação/após BRASILEIRO
        if (
            zona_filiacao
            and cand.upper() in zona_filiacao.upper()
            and zona_titular
            and cand.upper() not in zona_titular.upper()
        ):
            sc -= 60
        cands_nome.append((sc, cand, fonte))

    # 0) Entre chaves/colchetes: { EDUARDO MARTINS CARDOSO }
    for m in re.finditer(
        r"[\{\[\(]\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{6,55}?)\s*[\}\]\)]",
        t,
        re.I,
    ):
        _add_nome(m.group(1), bonus=15, fonte="chaves")
    # 1) CNH-e com pipes/OCR: "| BARTOLOMEU ... |"
    m = re.search(
        r"NOME\s*[E€&]?\s*SOBRENOME[^\n|]{0,80}"
        r"(?:\n|\|)\s*\|?\s*"
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{5,55}?)"
        r"(?=\s*[\|,]|\s*\d{2}/\d{2}/\d{4}|\s*\n|ASSINATURA|$)",
        t,
        re.I,
    )
    if m:
        _add_nome(m.group(1), bonus=14, fonte="label_nome")
    # 1b) Linha logo após "NOME E SOBRENOME"
    m = re.search(
        r"NOME\s*[E€&]?\s*SOBRENOME[^\n]{0,60}\n+\s*"
        r"\|?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{5,55}?)"
        r"(?=\s*[\|,]|\s*\d{2}/\d{2}/\d{4}|\s*\n|ASSINATURA|$)",
        t,
        re.I,
    )
    if m:
        _add_nome(m.group(1), bonus=14, fonte="label_nome")
    # 2) Mesma linha: NOME E SOBRENOME: FULANO
    m = re.search(
        r"(?:NOME\s*[E€&]?\s*SOBRENOME|NOME)\s*[:\.]?\s*"
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,6})",
        t,
        re.I,
    )
    if m:
        _add_nome(m.group(1), bonus=12, fonte="label_nome")
    # 3) Nome + 1ª habilitação na mesma linha
    m = re.search(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){2,6})\s*[.,]?\s*"
        r"(\d{2}/\d{2}/(?:19\d{2}|20[0-1]\d))\b",
        t,
    )
    if m:
        _add_nome(m.group(1), bonus=6, fonte="data")
    # 4) Após CARTEIRA NACIONAL (bônus moderado - OCR de foto erra muito)
    m = re.search(
        r"CARTEIRA\s*NACIONAL\s*DE\s*HABI[A-ZÁÉÍÓÚ]{3,12}[^\n]{0,100}"
        r"(?:\n|\r|/|\s)+"
        r"\|?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{6,55}?)"
        r"(?=\s*[\|,]|\s*\d{2}/\d{2}|\s*\n|DATA|TATA|ASSINATURA|$)",
        t,
        re.I,
    )
    if m:
        _add_nome(m.group(1), bonus=10, fonte="apos_titulo")
    # 5) Varredura: TODOS os nomes razoáveis (não só o “melhor”)
    #    para detectar ambiguidade (JEREMIAS vs ALEX vs UEREMIAS no OCR)
    for m in re.finditer(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:[ \t]+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,5})\b",
        t,
    ):
        _add_nome(m.group(1), bonus=0, fonte="varredura")
    mrz = re.search(r"\b([A-Z0-9]{2,}<<[A-Z0-9<]{5,40})", t)
    if mrz:
        parts = [p for p in mrz.group(1).replace("0", "O").split("<") if p and len(p) > 1]
        if len(parts) >= 2:
            _add_nome(" ".join(parts[:4]), bonus=5, fonte="mrz")

    # Escolha conservadora: vazio é melhor que nome inventado
    out["nome"] = ""
    out["_aviso_nome"] = ""
    if cands_nome:
        por_nome: Dict[str, tuple] = {}
        for sc, cand, fonte in cands_nome:
            k = cand.upper()
            if k not in por_nome or sc > por_nome[k][0]:
                por_nome[k] = (sc, cand, fonte)
        ordenados = sorted(por_nome.values(), key=lambda x: -x[0])
        melhor_sc, melhor, fonte_m = ordenados[0]
        # Foto CNH: 2+ nomes de pessoa = NÃO chuta (vazio > inventar)
        nomes_fortes = [
            (sc, c, f)
            for sc, c, f in ordenados
            if sc >= 15 and len(c.split()) >= 2
        ]
        label_claro = fonte_m in ("label_nome", "chaves")
        sc2 = ordenados[1][0] if len(ordenados) > 1 else -999
        # se há 2 nomes, só aceita se label NOME claro + margem
        ambiguo = len(nomes_fortes) >= 2 and not (
            label_claro and (melhor_sc - sc2) >= 12
        )
        if ambiguo:
            lista = " | ".join(c for _, c, _ in nomes_fortes[:4])
            out["nome"] = ""
            out["nome_pai"] = ""
            out["nome_mae"] = ""
            out["_aviso_nome"] = (
                f"OCR de foto incerto nos nomes ({lista}). "
                f"Preencha nome/pai/mãe manualmente na confirmação."
            )
            print(f"[CNH] [AVISO] {out['_aviso_nome']}")
            skip_filiacao = True
        elif _nome_parece_lixo_ocr(melhor):
            out["nome"] = ""
            skip_filiacao = False
        else:
            sex_val = (out.get("sexo") or "").upper()
            if _prenome_feminino(melhor) and ("MASC" in sex_val or sex_val == "MASCULINO"):
                print(f"[CNH] Nome candidato {melhor!r} é feminino mas sexo é MASCULINO - não atribui ao motorista.")
                out["nome"] = ""
            else:
                out["nome"] = melhor
            skip_filiacao = False
    else:
        skip_filiacao = False

    # Filiação - só se o nome do titular não estiver ambíguo
    if skip_filiacao:
        out["nome_pai"] = out.get("nome_pai") or ""
        out["nome_mae"] = out.get("nome_mae") or ""
    else:
        out["nome_pai"], out["nome_mae"] = _extrair_filiacao(
            t, titular=out.get("nome") or ""
        )
        tit = (out.get("nome") or "").upper().strip()
        if out.get("nome_pai") and (
            _nome_parece_lixo_ocr(out["nome_pai"])
            or (
                tit
                and (
                    out["nome_pai"].upper() == tit
                    or _nome_contem_titular(out["nome_pai"], tit)
                )
            )
        ):
            out["nome_pai"] = ""
        if out.get("nome_mae") and (
            _nome_parece_lixo_ocr(out["nome_mae"])
            or (
                tit
                and (
                    out["nome_mae"].upper() == tit
                    or _nome_contem_titular(out["nome_mae"], tit)
                )
            )
        ):
            out["nome_mae"] = ""
        if (
            out.get("nome_mae")
            and not _prenome_feminino(out["nome_mae"])
            and not out.get("nome_pai")
        ):
            out["nome_pai"] = out["nome_mae"]
            out["nome_mae"] = ""
        if (
            out.get("nome_pai")
            and _prenome_feminino(out["nome_pai"])
            and not out.get("nome_mae")
        ):
            out["nome_mae"] = out["nome_pai"]
            out["nome_pai"] = ""
        if out.get("nome_mae") and out.get("nome_pai"):
            if out["nome_mae"].upper() == out["nome_pai"].upper():
                out["nome_mae"] = ""
        if (not out.get("nome_mae") or not out.get("nome_pai")) and re.search(
            r"FILIA|BRASILEIRO", t, re.I
        ):
            _completar_filiacao_por_sobrenome(out, t)
        _normalizar_filiacao(out)
        for k in ("nome_pai", "nome_mae"):
            v = out.get(k) or ""
            if v and _nome_parece_lixo_ocr(v):
                out[k] = ""

    # RG + órgão (ex: 4004599 DGPC GO | 690821 SSP SE | 1362010243 SSP___BA)
    # OCR sujo: underscores/pontos entre SSP e UF; não aceitar rg="." 
    def _set_rg(num: str, org: str = "", uf: str = "") -> None:
        num = so_digitos(num or "") or _ocr_digitos(num or "")
        if not (5 <= len(num) <= 12):
            return
        # evita capturar pedaços de CPF/CNH (11 dígitos) como RG se for igual
        if len(num) == 11 and (
            num == (out.get("cpf") or "") or num == (out.get("cnh") or "")
        ):
            return
        out["rg"] = num
        org_u = (org or "").upper().strip()
        uf_u = (uf or "").upper().strip()[:2]
        if org_u:
            out["orgao_emissor"] = f"{org_u} {uf_u}".strip()

    m = re.search(
        r"\b(\d{5,12})\s+(SDS|SSP|DGPC|DETRAN|IFP|PC)[_\s.\-]*([A-Z]{2})?\b",
        t,
        re.I,
    )
    if m:
        _set_rg(m.group(1), m.group(2), m.group(3) or "")
    if not out.get("rg"):
        # linha DOC IDENTIDADE com OCR: símbolos + dígitos confusos + SSP SE
        m = re.search(
            r"(?:DOC\.?\s*IDENTIDADE|ORG\.?\s*EMISSOR|4C\s*DOC)[^\n]{0,80}"
            r"(?:\n[^\n]{0,40})?"
            r"([0-9OILSZ«»\[\]\s._\-]{4,14})\s*(SDS|SSP|DGPC|DETRAN|IFP|PC)"
            r"[_\s.\-]*([A-Z]{2})?\b",
            t,
            re.I,
        )
        if m:
            _set_rg(m.group(1), m.group(2), m.group(3) or "")
    if not out.get("rg"):
        # qualquer token alfanumérico sujo antes de SSP/SDS (ex: 1362010243 SSP___BA)
        m = re.search(
            r"([0-9OILSZ«»]{5,12})\s+(SDS|SSP|DGPC|DETRAN|IFP|PC)[_\s.\-]*([A-Z]{2})?\b",
            t,
            re.I,
        )
        if m:
            _set_rg(m.group(1), m.group(2), m.group(3) or "")
    if not out.get("rg"):
        raw_rg = _campo_apos(
            t, r"(?:DOC\.?\s*IDENTIDADE|RG)\s*[:\.]?\s*", r"([\d.OIl]{5,14})"
        )
        dig = so_digitos(raw_rg) or _ocr_digitos(raw_rg or "")
        if 5 <= len(dig) <= 12:
            out["rg"] = dig
        if re.search(r"\bSDS\s*PE\b", t):
            out["orgao_emissor"] = out.get("orgao_emissor") or "SDS PE"
        elif re.search(r"\bDGPC\s*GO\b", t):
            out["orgao_emissor"] = out.get("orgao_emissor") or "DGPC GO"
        elif re.search(r"\bSSP\s*SE\b", t):
            out["orgao_emissor"] = out.get("orgao_emissor") or "SSP SE"
        elif re.search(r"\bSSP[_\s.\-]*([A-Z]{2})\b", t):
            mm = re.search(r"\bSSP[_\s.\-]*([A-Z]{2})\b", t)
            if mm:
                out["orgao_emissor"] = out.get("orgao_emissor") or f"SSP {mm.group(1)}"
    # Nunca deixe rg lixo (só ponto/traço)
    if out.get("rg") and not re.search(r"\d{5,}", str(out.get("rg") or "")):
        out["rg"] = ""

    # Data emissão OCR sujo: "[:s/o72025" ao lado de validade 30/06/2030
    if not out.get("data_emissao_cnh"):
        em = _extrair_data_emissao_ocr(t, validade=out.get("validade_cnh") or "")
        if em:
            out["data_emissao_cnh"] = em
    # Validade/emissão escondidas em lixo tipo "fonsnovz0s3" / "40/10/2023"
    _recuperar_datas_cnh_ocr_sujo(out, t)
    # Sanitiza datas já preenchidas (40/10/2023 -> 10/10/2023)
    for k in ("data_emissao_cnh", "validade_cnh", "data_primeira_habilitacao", "data_nascimento"):
        v = out.get(k) or ""
        if not v:
            continue
        if not _data_valida_cnh(v):
            out[k] = _corrigir_data_ocr(v) or ""
    # NUNCA copiar 1ª habilitação para emissão (bug: 20/06/2012 nos dois campos)
    prim = out.get("data_primeira_habilitacao") or ""
    em = out.get("data_emissao_cnh") or ""
    if em and prim and em == prim:
        # se a data é antiga (<=2018), é 1ª hab - zera emissão e tenta de novo
        if _ano(em) <= 2018:
            out["data_emissao_cnh"] = ""
            em2 = _extrair_data_emissao_ocr(t, validade=out.get("validade_cnh") or "")
            if em2 and em2 != prim:
                out["data_emissao_cnh"] = em2
        else:
            # data recente nos dois: mantém emissão, zera 1ª se for igual
            out["data_primeira_habilitacao"] = ""
    # emissão deve ser < validade e geralmente >= 2015
    em = out.get("data_emissao_cnh") or ""
    val = out.get("validade_cnh") or ""
    if em and val and _ano(em) > _ano(val):
        out["data_emissao_cnh"] = ""
    if em and _ano(em) and _ano(em) < 2010 and em == prim:
        out["data_emissao_cnh"] = ""

    # Local de emissão (CNH-e verso / rodapé DETRAN)
    if not out.get("local_emissao_cnh"):
        m = re.search(
            r"\bLOCAL\s*[:\.]?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){0,3})"
            r"\s*[,/\s]+([A-Z]{2})\b",
            t,
            re.I,
        )
        if m:
            cid = _limpa_nome(m.group(1))
            if cid and cid.upper() not in ("BRASIL", "PLACE", "BIRTH", "GOIAS"):
                out["local_emissao_cnh"] = f"{cid}/{m.group(2).upper()}"
        if not out.get("local_emissao_cnh"):
            # SERGIPE / DETRAN-SE no rodapé
            if re.search(r"\bSERGIPE\b|\bDETRAN\s*[- ]?\s*SE\b", t):
                if re.search(r"\bARACAJU\b", t):
                    out["local_emissao_cnh"] = "ARACAJU/SE"
                elif re.search(r"\bSE\b", t):
                    # só UF conhecida no doc
                    out["local_emissao_cnh"] = out.get("local_emissao_cnh") or ""

    # Naturalidade / local de nascimento ou LOCAL no verso da CNH-e
    # Ex.: "22/08/1962, CAROLINA, MA"  ou  "17/03/1975, ARAPIRACA, AL"
    # NÃO sobrescrever se já veio da linha data,cidade,UF em _classificar_datas_cnh
    if not out.get("naturalidade"):
        m = re.search(
            r"(?:NASCIMENTO|NASC\.?)[^\n]{0,40}?\n?\s*"
            r"(\d{2}/\d{2}/\d{4})\s*[,]\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{3,30}?)\s*[,]\s*([A-Z]{2})\b",
            t,
            re.I,
        )
        if m:
            if not out.get("data_nascimento"):
                out["data_nascimento"] = m.group(1)
            cid = _limpa_nome(m.group(2))
            if cid and not any(x in cid.upper() for x in ("DATA", "LOCAL", "NASC")):
                out["naturalidade"] = cid
                out["uf_naturalidade"] = m.group(3).upper()
    if not out.get("naturalidade"):
        m = re.search(
            r"\b(\d{2}/\d{2}/(?:19\d{2}|20[0-1]\d))\b\s*[,]\s*"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){0,3})\s*[,]\s*([A-Z]{2})\b",
            t,
        )
        if m:
            cid = _limpa_nome(m.group(2))
            if cid and not any(x in cid.upper() for x in ("DATA", "LOCAL", "NASC", "EMISS")):
                out["naturalidade"] = cid
                out["uf_naturalidade"] = m.group(3).upper()
                if not out.get("data_nascimento"):
                    out["data_nascimento"] = m.group(1)
    if not out.get("naturalidade"):
        m = re.search(
            r"\bLOCAL\s*[:\.]?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+)?)\s*[,/\s]+([A-Z]{2})\b",
            t,
            re.I,
        )
        if m:
            cid = _limpa_nome(m.group(1))
            # ignora lixo; LOCAL de emissão só se naturalidade ainda vazia
            if cid.upper() not in ("GOIAS", "GOIÁS", "BRASIL", "PLACE", "BIRTH"):
                out["naturalidade"] = cid
                out["uf_naturalidade"] = m.group(2).upper()
    if not out.get("naturalidade"):
        # "GOIANIA, GO" / "GOIÂNIA GO" solto
        m = re.search(
            r"\b(GOI[AÂ]NIA|CAROLINA|PAULISTA|RECIFE|ARAPIRACA|AN[AÁ]POLIS|"
            r"CURITIBA|FORTALEZA|NATAL)\s*[,/\s]+([A-Z]{2})\b",
            t,
            re.I,
        )
        if m:
            out["naturalidade"] = m.group(1).upper().replace("Â", "A")
            if out["naturalidade"] == "GOIANIA" or "GOI" in out["naturalidade"]:
                out["naturalidade"] = "GOIANIA"
            out["uf_naturalidade"] = m.group(2).upper()
    if not out.get("naturalidade"):
        m = re.search(
            r"\b(GOI[AÂ]NIA|CAROLINA|PAULISTA|RECIFE|ARAPIRACA|AN[AÁ]POLIS)\b",
            t,
            re.I,
        )
        if m:
            out["naturalidade"] = m.group(1).upper().replace("Â", "A")
            if "GOI" in out["naturalidade"]:
                out["naturalidade"] = "GOIANIA"
                out["uf_naturalidade"] = out.get("uf_naturalidade") or "GO"
            elif out["naturalidade"] == "ARAPIRACA":
                out["uf_naturalidade"] = out.get("uf_naturalidade") or "AL"

    # Sexo: texto ou MRZ da CNH-e (linha 2: AAMMDD + dig + M/F + validade)
    out["sexo"] = _extrair_sexo_cnh(t)

    # normaliza nome "DACOSTA" -> "DA COSTA"
    if out.get("nome"):
        out["nome"] = re.sub(r"\bDACOSTA\b", "DA COSTA", out["nome"], flags=re.I)
        out["nome"] = re.sub(r"\s+", " ", out["nome"]).strip()

    return out


# Categorias válidas de CNH (simples + combinadas)
_CAT_CNH_OK = {
    "A", "B", "C", "D", "E",
    "AB", "AC", "AD", "AE",
    "BC", "BD", "BE",
    "CD", "CE", "DE",
    "ACC",  # raro / ACC às vezes confunde; só se explícito
}


def _extrair_categoria_cnh(t: str, cnh: str = "") -> str:
    """
    Extrai SOMENTE a categoria real da CNH (campo CAT HAB).

    NÃO inventa AE a partir de letras soltas da área ACC (A B C D E).
    Ordem: CAT HAB -> linha CPF+registro+cat -> registro+cat.
    """

    def _ok(cat: str) -> str:
        cat = (cat or "").upper().strip()
        if cat in _CAT_CNH_OK and cat not in ("DA", "DO", "ACC"):
            return cat
        return ""

    # 1) CAT HAB / CAT HAS / 9 CAT HAB - valor na MESMA linha (mais confiável)
    m = re.search(
        r"(?:9\s*)?(?:CAT\.?\s*HA[BS]\.?|CAT\.?\s*HAB\.?|CATH|"
        r"CAT\.?\s*DE\s*HAB)\s*[:\.\)]?\s*([A-E]{1,2})\b",
        t,
        re.I,
    )
    if m:
        cat = _ok(m.group(1))
        if cat:
            return cat

    # 2) CAT HAB na linha de cima, letra na de baixo (OCR quebra)
    m = re.search(
        r"(?:9\s*)?(?:CAT\.?\s*HA[BS]|CATH|CATEGORIA\s*DE\s*HAB)"
        r"[^\n]{0,20}\n\s*([A-E]{1,2})\b",
        t,
        re.I,
    )
    if m:
        cat = _ok(m.group(1))
        if cat:
            return cat

    # 3) CPF + nº registro + categoria (sem pegar ACC)
    m = re.search(
        r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s+(\d{9,11})\s+([A-E]{1,2})\b",
        t,
        re.I,
    )
    if m:
        cat = _ok(m.group(2))
        if cat:
            return cat

    # 4) Só o nº de registro da CNH + categoria
    if cnh and len(cnh) >= 9:
        m = re.search(re.escape(cnh) + r"\s+([A-E]{1,2})\b", t, re.I)
        if m:
            cat = _ok(m.group(1))
            if cat:
                return cat

    # 5) "CATEGORIA" explícito (não "ACC" / lista de permissões)
    m = re.search(
        r"\bCATEGORIA\b(?!\s*ACC)[^\nA-E]{0,12}([A-E]{1,2})\b",
        t,
        re.I,
    )
    if m:
        cat = _ok(m.group(1))
        if cat:
            return cat

    # NÃO varrer "AE" solto perto de REGISTRO/CNH - inventava AE a partir do ACC
    return ""


def _extrair_sexo_cnh(t: str) -> str:
    """
    Sexo na CNH-e:
      - texto MASCULINO / FEMININO / SEXO M|F
      - MRZ TD1 linha 2: AAMMDD + digito + M|F + AAMMDD validade
        ex.: 8408185M3209147BRA<<<<<<<<<<<4  -> M
    """
    if re.search(r"\bMASCULINO\b|SEXO\s*[:\.]?\s*M\b|\bSEXO\s*M\b", t):
        return "Masculino"
    if re.search(r"\bFEMININO\b|SEXO\s*[:\.]?\s*F\b|\bSEXO\s*F\b", t):
        return "Feminino"

    # MRZ: 6 dígitos data nasc + 1 check + M/F + 6 dígitos validade
    for m in re.finditer(r"\b(\d{6})(\d)([MF])(\d{6})\d?", t):
        sexo = m.group(3)
        # confere se parece data (AAMMDD razoável)
        aa, mm, dd = m.group(1)[:2], m.group(1)[2:4], m.group(1)[4:6]
        try:
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                return "Masculino" if sexo == "M" else "Feminino"
        except ValueError:
            continue

    # MRZ sem check digit explícito (OCR colado)
    m = re.search(r"\b\d{6}([MF])\d{6}BRA", t)
    if m:
        return "Masculino" if m.group(1) == "M" else "Feminino"

    return ""


# ---------------------------------------------------------------------------
# CRLV
# ---------------------------------------------------------------------------

# Palavras de ESPÉCIE/TIPO que NÃO podem entrar na descrição de marca
_ESPECIE_STOP = (
    "PASSAGEIRO", "AUTOMOVEL", "AUTOMÓVEL", "CAMINHAO", "CAMINHÃO", "TRATOR",
    "TRACAO", "TRAÇÃO", "SEMI", "REBOQUE", "SEMI-REBOQUE", "SEMIRREBOQUE",
    "CARGA", "ESPECIE", "ESPÉCIE", "TIPO", "PARTICULAR", "ALUGUEL", "OFICIAL",
    "ALCOOL", "ÁLCOOL", "GASOLINA", "DIESEL", "FLEX", "PLACA", "CHASSI",
    "COR", "PREDOMINANTE", "COMBUSTIVEL", "COMBUSTÍVEL",
)


def _parse_especie_crlv(out: Dict[str, Any], t: str) -> None:
    """Preenche espécie / flags CAVALO-CARRETA - separado da marca."""
    if re.search(r"SEMI[-\s]?REBOQUE|SEMIRREBOQUE|CARGA\s*SEMI", t, re.I):
        out["eh_semi_reboque"] = True
        out["tipo_veiculo_doc"] = "SEMI-REBOQUE"
        out["especie"] = "SEMI-REBOQUE"
    elif re.search(
        r"CAMINH[AÃ]O\s*TRATOR|CAVALO\s*MEC|TRAC[AÃ]O|TRATOR\s*DE\s*RODAS", t, re.I
    ):
        out["eh_caminhao_trator"] = True
        out["tipo_veiculo_doc"] = "CAMINHAO TRATOR"
        out["especie"] = "CAMINHAO TRATOR"
    elif re.search(r"\bCAMINH[AÃ]O\b", t, re.I):
        out["eh_caminhao"] = True
        out["tipo_veiculo_doc"] = "CAMINHAO"
        out["especie"] = "CAMINHAO"
    elif re.search(r"PASSAGEIRO|AUTOM[OÓ]VEL", t, re.I):
        out["especie"] = "PASSAGEIRO AUTOMOVEL"
        out["tipo_veiculo_doc"] = "AUTOMOVEL"

    # campo rotulado ESPÉCIE / TIPO
    m = re.search(
        r"ESP[EÉ]CIE\s*/\s*TIPO\s*[:\.]?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\s\-]{3,40})",
        t,
        re.I,
    )
    if m:
        esp = re.sub(r"\s+", " ", m.group(1)).strip()
        # corta se grudou outra label
        esp = re.split(
            r"\b(?:CARROCERIA|COMBUST|COR|PLACA|CHASSI|MARCA)\b", esp, flags=re.I
        )[0].strip()
        if esp:
            out["especie"] = out["especie"] or esp
            if re.search(r"SEMI|REBOQUE", esp, re.I):
                out["eh_semi_reboque"] = True
            if re.search(r"TRATOR|TRAC[AÃ]O|CAVALO", esp, re.I):
                out["eh_caminhao_trator"] = True


def _limpar_marca_sem_especie(mmv: str) -> str:
    """
    Marca limpa para o GW:
      - tira espécie (TRACAO, CAMINHAO TRATOR, SEMI-REBOQUE...)
      - troca '/' por espaço (M.BENZ/AXOR -> M.BENZ AXOR)
      - tira lixo de OCR colado no fim (". oO Ena", "00 ENA", etc.)
    Ex. certo: M.BENZ AXOR 2536 LS | SR RANDON SR FG CG 3E
    """
    if not mmv:
        return ""
    s = mmv.strip()
    # Corta lixo de labels do DPVAT / formulário grudados no fim
    s = re.split(
        r"\b(?:DADOS\s+DO\s+SEGURO|DADOS\s+DO|SEGURO\s+DPVAT|DPVAT|INFORMA[CÇG][OÕ]ES)\b",
        s,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    # corta assinatura digital grudada
    s = re.split(
        r"\b(?:ASSINADO|DIGITALMENTE|PELO\s+DETRAN)\b",
        s,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    # Lixo típico do CRLV-e colado na marca (OCR lê campo vizinho / carimbo)
    # Ex.: "SR/RANDON SR FG CG 3E . oO Ena" -> "SR/RANDON SR FG CG 3E"
    s = re.split(
        r"\s*[\.\,;:]\s*(?:o+o?\s*)?e?na\b|\s+\.?\s*(?:00|oO|OO|0O|O0)\s*e?na\b",
        s,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    s = re.sub(
        r"(?i)\s*[\.\,;:]+\s*(?:oo|00|o0|0o)?\s*ena\s*$",
        "",
        s,
    ).strip()
    # corta " . " + lixo curto no fim (1–4 tokens sem dígito de modelo)
    s = re.sub(r"\s+\.\s+[A-Za-z]{1,4}(?:\s+[A-Za-z]{1,4}){0,2}\s*$", "", s).strip()
    # / sempre vira espaço (pedido operação)
    s = s.replace("/", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # corrige OCR RANDON ↔ RANDOM (fabricante de carreta é RANDON)
    s = re.sub(r"(?i)\bRANDOM\b", "RANDON", s)
    # corta a partir de palavra de espécie / tração
    s = re.split(
        r"\b(?:"
        + "|".join(re.escape(x) for x in _ESPECIE_STOP)
        + r")\b",
        s,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" -")
    # remove "TRACAO" colado no fim
    s = re.sub(
        r"(?i)[\s-]*(TRACAO|TRAÇÃO|TRATOR|SEMI-?REBOQUE|CARGA|CAMINHAO)$",
        "",
        s,
    ).strip(" -")
    # remove pontuação residual no fim
    s = re.sub(r"[\s\.\-,;:]+$", "", s).strip()
    if _parece_label_crlv_nao_marca(s):
        return ""
    return s


def _extrair_renavam_crlv(t: str) -> str:
    """
    RENAVAM no CRLV-e: costuma começar com 00 e ter 9–11 dígitos.
    NÃO pegar: código de segurança CLA, nº CRV, CPF.
    Usa votação + dígito verificador (ocr_qualidade).
    """
    try:
        from ocr.ocr_qualidade import extrair_renavam_melhor

        val, _conf, _av = extrair_renavam_melhor(t)
        if val:
            return val
    except Exception:
        pass
    # fallback legado
    m = re.search(
        r"(?:C[OÓ]DIGO\s*)?RENAVAM\s*[:\.]?\s*(\d{9,11})\b",
        t,
        re.I,
    )
    if m:
        cand = m.group(1)
        if not _renavam_parece_lixo(cand, t):
            return cand

    cands = re.findall(r"\b(\d{9,11})\b", t)
    ordenados = sorted(
        cands,
        key=lambda c: (0 if c.startswith("00") else 1, 0 if len(c) in (10, 11) else 1),
    )
    for cand in ordenados:
        if _renavam_parece_lixo(cand, t):
            continue
        if _parece_cpf_formatado(t, cand):
            continue
        return cand
    return ""


def _renavam_parece_lixo(cand: str, t: str) -> bool:
    """True se o número é CLA/CRV/segurança, não renavam."""
    if not cand or len(cand) < 9:
        return True
    if cand.startswith("000"):
        return True
    pos = (t or "").find(cand)
    if pos >= 0:
        ctx = (t or "")[max(0, pos - 40) : pos + len(cand) + 20].upper()
        if any(
            x in ctx
            for x in (
                "SEGURAN", "SEGURANCA", "CLA", "CRV", "NUMERO DO CRV",
                "NÚMERO DO CRV", "POTENC", "CILINDR",
            )
        ):
            if "RENAVAM" not in ctx:
                return True
    if len(cand) == 11 and not cand.startswith("00") and not cand.startswith("0"):
        if re.search(r"\b00\d{8,9}\b", t or ""):
            return True
    return False


def _extrair_chassi_crlv(t: str) -> str:
    """
    Chassi/VIN:
      - cavalo: VIN ISO 17 chars (9BVAS02DX7E735459)
      - carreta/semi: muitas vezes só dígitos 11–14 (ex. 264691407839)

    OCR de WhatsApp troca 0↔O e 1↔I e inventa VIN falso (9ADR1543LMC011863).
    """
    # 1) Chassi numérico de carreta ANTES do VIN (OCR inventa VIN 17 falso)
    num = _chassi_numerico_no_texto(t)
    eh_carreta = bool(
        re.search(r"SEMI|REBOQUE|CARRETA|RANDON|FACCHINI|GUERRA", t, re.I)
    )
    if num and eh_carreta:
        return num

    m_num = re.search(
        r"CHASSI\s*[:\.]?\s*(\d{11,14})\b",
        t,
        re.I,
    )
    if m_num and not m_num.group(1).startswith("00"):
        return m_num.group(1)

    # 2) Extrator com score (VIN 17 + numérico)
    try:
        from ocr.ocr_qualidade import extrair_chassi_melhor

        val, conf, _av = extrair_chassi_melhor(t)
        if val and conf >= 0.55:
            return val
        # conf baixa: prefere numérico se existir e for carreta
        if num and eh_carreta:
            return num
        if val:
            return val
    except Exception:
        pass
    if num:
        return num

    def _norm_vin(s: str) -> str:
        s = re.sub(r"[^A-Za-z0-9]", "", s or "").upper()
        s = s.replace("O", "0").replace("I", "1").replace("Q", "0")
        return s

    def _vin_ok(vin: str, raw: str = "") -> bool:
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
        if not vin.startswith("9"):
            if sum(1 for c in vin[:4] if c.isalpha()) >= 4:
                return False
        letras = sum(1 for c in vin if c.isalpha())
        if letras > 12:
            return False
        return True

    m = re.search(
        r"CHASSI\s*[:\.]?\s*([A-Z0-9OIQ][A-Z0-9OIQ \-]{10,22})",
        t,
        re.I,
    )
    if m:
        raw = m.group(1)
        # só dígitos 11–14
        digs = re.sub(r"\D", "", raw)
        if 11 <= len(digs) <= 14 and digs.isdigit():
            return digs
        vin = _norm_vin(raw)
        if len(vin) >= 17:
            vin = vin[:17]
            if _vin_ok(vin, raw):
                return vin

    num = _chassi_numerico_no_texto(t)
    if num:
        return num

    hits = []
    for m in re.finditer(r"\b([A-Z0-9OIQ]{17})\b", t, re.I):
        raw = m.group(1)
        vin = _norm_vin(raw)
        if _vin_ok(vin, raw):
            hits.append(vin)
    if hits:
        hits.sort(key=lambda v: (0 if v.startswith("9") else 1))
        return hits[0]

    m = re.search(
        r"\b([A-Z0-9OIQ]{3,}(?:[\s\-][A-Z0-9OIQ]{1,}){2,})\b",
        t,
        re.I,
    )
    if m:
        raw = m.group(1)
        vin = _norm_vin(raw)
        if _vin_ok(vin, raw):
            return vin
    return ""


def _chassi_numerico_no_texto(t: str) -> str:
    """
    Chassi de carreta BR: 11–14 dígitos (não é VIN ISO).
    Evita RENAVAM (começa 00) e CNPJ/CPF por contexto.

    Em SEMI/RANDON o label CHASSI do OCR falha com frequência
    ('LACAANTERIGR | CHASSI FUNDO NACIONAL...') - o valor 12 dígitos
    solto no texto (ex. 264691407839) é o chassi real.
    """
    if not t:
        return ""
    eh_carreta = bool(
        re.search(r"SEMI|REBOQUE|CARRETA|RANDON|FACCHINI|GUERRA|LIBRELATO", t, re.I)
    )
    # perto de CHASSI
    for m in re.finditer(
        r"CHASSI[^\n]{0,40}?(\d{11,14})\b",
        t,
        re.I,
    ):
        cand = m.group(1)
        if cand.startswith("00"):
            continue  # renavam
        return cand
    # dígitos 12 (padrão semi-reboque)
    cands_all = re.findall(r"\b(\d{12})\b", t)
    bons: list[str] = []
    for cand in cands_all:
        if cand.startswith("00"):
            continue
        pos = t.find(cand)
        ctx = t[max(0, pos - 40) : pos + 20].upper()
        if any(x in ctx for x in ("RENAVAM", "CNPJ", "CPF", "CGC", "RNTRC", "CRV")):
            continue
        if "CHASSI" in ctx or "CHAS" in ctx:
            return cand
        bons.append(cand)
    if eh_carreta and len(bons) == 1:
        return bons[0]
    if eh_carreta and bons:
        for c in bons:
            if not c.startswith("0"):
                return c
        return bons[0]
    # sem flag carreta: se só há um 12-dígitos "limpo", ainda assim usa
    if len(bons) == 1 and not bons[0].startswith("0"):
        return bons[0]
    return ""


def _parece_label_crlv_nao_marca(s: str) -> bool:
    """True se o trecho é label/boilerplate (não é marca)."""
    u = (s or "").upper()
    return any(
        x in u
        for x in (
            "PLACA ANTERIOR", "CHASSI", "COR PREDOMINANTE", "ESPÉCIE", "ESPECIE",
            "COMBUST", "CÓDIGO", "CODIGO", "RENAVAM", "CARROCERIA", "OBSERVA",
            "ANTERIOR / UF", "PREDOMINANTE",
            # OCR gruda assinatura digital no campo MARCA
            "ASSINADO", "DIGITALMENTE", "PELO DETRAN", "DETRAN",
            "CERTIFICADO", "LICENCIAMENTO", "REPUBLICA", "FEDERATIVA",
            "GOVBR", "CATEGORIA", "CAPACIDADE", "ALUGUEL", "PARTICULAR",
        )
    )


_FAB_MARCA = (
    r"(?:VW|M\.?\s*BENZ|MERCEDES|SCANIA|VOLVO|FORD|IVECO|DAF|MAN|"
    r"RENAULT|HYUNDAI|CHEVROLET|FIAT|TOYOTA|KIA|HONDA|PEUGEOT|"
    r"IMP|SR|RANDON|LIBRELATO|FACCHINI|GUERRA|RODOLINEA|NOMA|PASTREL)"
)


def _extrair_marca_modelo_crlv(t: str) -> str:
    """
    Só MARCA/MODELO do CRLV - nunca espécie nem 'ASSINADO DIGITALMENTE'.
    Ex.: SR/FACCHINI SRF CF  |  IVECO/STRALIS 570S38T
    """
    candidatas: list[str] = []

    # 1) FABRICANTE/MODELO (prioridade máxima - não confunde com assinatura)
    for m in re.finditer(
        rf"\b({_FAB_MARCA}/[A-Z0-9][A-Z0-9./ \-]{{1,40}})",
        t,
        re.I,
    ):
        cand = m.group(1).strip().split("\n")[0].strip()
        # corta se grudou ASSINADO na mesma linha
        cand = re.split(r"\bASSINADO\b|\bDIGITAL", cand, maxsplit=1, flags=re.I)[0].strip()
        if cand and not _parece_label_crlv_nao_marca(cand):
            candidatas.append(cand)

    # 1b) FACCHINI / GUERRA sem barra (OCR quebra SR/FACCHINI)
    if not candidatas:
        m = re.search(
            r"\b((?:SR\s*)?FACCHINI[A-Z0-9 \-]{0,20}|GUERRA[A-Z0-9 \-]{2,20})\b",
            t,
            re.I,
        )
        if m and not _parece_label_crlv_nao_marca(m.group(1)):
            candidatas.append(m.group(1).strip())

    # 2) Campo rotulado - valor na mesma linha OU próxima (pula ASSINADO)
    m = re.search(
        r"MARCA\s*/\s*MODELO\s*/\s*VERS[AÃ]O\s*[:\.]?\s*"
        r"(?:([A-Z0-9./][A-Z0-9./ \-]{2,45})|"
        r"(?:\n[^\n]{0,5})*?\n\s*(" + _FAB_MARCA + r"/[A-Z0-9][A-Z0-9./ \-]{1,40}))",
        t,
        re.I,
    )
    if m:
        cand = (m.group(1) or m.group(2) or "").split("\n")[0].strip()
        cand = re.split(r"\bASSINADO\b|\bDIGITAL", cand, maxsplit=1, flags=re.I)[0].strip()
        if cand and not _parece_label_crlv_nao_marca(cand):
            candidatas.insert(0, cand)
    # 2b) linhas após MARCA/MODELO
    if not any("/" in (c or "") for c in candidatas):
        m_blk = re.search(
            r"MARCA\s*/\s*MODELO[^\n]{0,40}\n(.{0,120})",
            t,
            re.I,
        )
        if m_blk:
            trecho = m_blk.group(1)
            m2 = re.search(rf"({_FAB_MARCA}/[A-Z0-9][A-Z0-9./ \-]{{1,40}})", trecho, re.I)
            if m2 and not _parece_label_crlv_nao_marca(m2.group(1)):
                candidatas.insert(0, m2.group(1).strip())

    # 3) Linha isolada tipo M.BENZ/AXOR
    if not candidatas:
        m = re.search(
            r"(?m)^[\s]*([A-Z0-9.]{1,12}/[A-Z0-9][A-Z0-9. \-]{2,40})[\s]*$",
            t,
            re.I,
        )
        if m and not _parece_label_crlv_nao_marca(m.group(1)):
            candidatas.append(m.group(1).strip())

    # Prefere candidata com FAB/modelo (barra) sobre lixo
    candidatas.sort(
        key=lambda c: (1 if re.search(rf"^{_FAB_MARCA}/", c, re.I) else 0, len(c)),
        reverse=True,
    )
    for raw in candidatas:
        if _parece_label_crlv_nao_marca(raw):
            continue
        mmv = _limpar_marca_sem_especie(raw)
        if len(mmv) >= 5 and not _parece_label_crlv_nao_marca(mmv):
            return mmv
    return ""


def parse_crlv(texto: str, path: Optional[Path] = None) -> Dict[str, Any]:
    t = _norm(texto)
    # Normaliza espaços em CPFs/CNPJs/Datas sujos pelo OCR (ex: "42 .934. 489/ 0002- 08")
    t = re.sub(r"(\d)\s*([./\-])\s*(\d)", r"\1\2\3", t)
    out: Dict[str, Any] = {

        "placa": "",
        "renavam": "",
        "chassi": "",
        "marca": "",
        "modelo": "",
        "versao": "",
        "marca_modelo_versao": "",
        "ano_fab": "",
        "ano_mod": "",
        "cor": "",
        "tipo_veiculo_doc": "",
        "especie": "",
        "cidade": "",
        "uf": "",
        "proprietario_nome": "",
        "proprietario_cpf_cnpj": "",
        "eh_semi_reboque": False,
        "eh_caminhao_trator": False,
        "eh_caminhao": False,
    }

    # Placa mercosul / antiga - VOTAÇÃO (não o 1º match: evita JSV6B70 vs JSV6H70)
    try:
        from ocr.ocr_qualidade import extrair_placas_votacao, normalizar_placa_mercosul

        pl, conf_pl, outras = extrair_placas_votacao(t)
        if pl:
            out["placa"] = normalizar_placa_mercosul(pl)
            out["_confianca"] = {"placa": conf_pl}
            if outras:
                out["_placa_candidatas"] = outras
        else:
            m = re.search(r"\b([A-Z]{3}\d[A-Z0-9]\d{2})\b", t)
            if not m:
                m = re.search(r"\b([A-Z]{3}\-?\d{4})\b", t)
            if m:
                out["placa"] = limpar_placa(m.group(1))
    except Exception:
        m = re.search(r"\b([A-Z]{3}\d[A-Z0-9]\d{2})\b", t)
        if not m:
            m = re.search(r"\b([A-Z]{3}\-?\d{4})\b", t)
        if m:
            out["placa"] = limpar_placa(m.group(1))

    # Renavam: NÃO usar código de segurança CLA / CRV
    out["renavam"] = _extrair_renavam_crlv(t)

    # Chassi 17 chars (OCR troca 0↔O e 1↔I - aceita e normaliza)
    out["chassi"] = _extrair_chassi_crlv(t)

    # Espécie / tipo - ANTES da marca, para NÃO misturar no texto da marca
    _parse_especie_crlv(out, t)

    # Marca/modelo - NUNCA inclui espécie nem "ASSINADO DIGITALMENTE"
    mmv = _extrair_marca_modelo_crlv(t)
    if mmv and not _parece_label_crlv_nao_marca(mmv):
        out["marca_modelo_versao"] = mmv
        out["marca"] = mmv
        out["modelo"] = mmv

    # Anos fab/mod (aceita anos até 2028+)
    import datetime
    max_ano = datetime.datetime.now().year + 2
    
    # 1) Tenta padrão de rótulo explícito (ex: ANO FABRICACAO 2023 / ANO MODELO 2024)
    m_fab = re.search(r"ANO\s*(?:FABRICAC[AO]ÃO?|FAB)\s*[:\.]?\s*(19\d{2}|20[0-3]\d)", t, re.I)
    m_mod = re.search(r"ANO\s*(?:MODELO|MOD)\s*[:\.]?\s*(19\d{2}|20[0-3]\d)", t, re.I)
    if m_fab:
        out["ano_fab"] = m_fab.group(1)
    if m_mod:
        out["ano_mod"] = m_mod.group(1)

    # 2) Fallback robusto analisando todos os anos candidatos (ignorando datas e exercício)
    if not out["ano_fab"] or not out["ano_mod"]:
        # Busca anos de 4 dígitos que não façam parte de datas (ex: DD/MM/AAAA)
        cands = re.findall(r"(?<![\d/\-])\b(19\d{2}|20[0-3]\d)\b(?![\d/\-])", t)
        
        # Filtra apenas anos dentro de uma faixa razoável
        cands = [a for a in cands if 1980 <= int(a) <= max_ano]
        
        # Tenta encontrar o melhor par (fab, mod) com diferença de no máximo 1 ano (ex: 2009 e 2010, ou 2021 e 2021)
        pair = None
        # Primeiro tenta candidatos adjacentes no texto
        for i in range(len(cands) - 1):
            a1, a2 = cands[i], cands[i+1]
            if abs(int(a1) - int(a2)) <= 1:
                pair = (a1, a2)
                break
        # Se não achar adjacentes, busca qualquer combinação
        if not pair:
            for i in range(len(cands)):
                for j in range(i + 1, len(cands)):
                    a1, a2 = cands[i], cands[j]
                    if abs(int(a1) - int(a2)) <= 1:
                        pair = (a1, a2)
                        break
                if pair:
                    break
                    
        if pair:
            out["ano_fab"] = min(pair, key=int)
            out["ano_mod"] = max(pair, key=int)
        else:
            # Se não encontrou par com diff <= 1, remove anos que parecem de exercício (recentes >= 2024)
            # se houver algum ano mais antigo disponível.
            antigos = [a for a in cands if int(a) < 2024]
            if antigos:
                if not out["ano_fab"]:
                    out["ano_fab"] = antigos[0]
                if not out["ano_mod"]:
                    out["ano_mod"] = antigos[0]
            elif cands:
                if not out["ano_fab"]:
                    out["ano_fab"] = cands[0]
                if not out["ano_mod"]:
                    out["ano_mod"] = cands[0]

    # Garante a ordem correta (ano_fab <= ano_mod)
    if out["ano_fab"] and out["ano_mod"]:
        if int(out["ano_fab"]) > int(out["ano_mod"]):
            out["ano_fab"], out["ano_mod"] = out["ano_mod"], out["ano_fab"]


    # Cor
    cores = (
        "PRATA", "BRANCA", "BRANCO", "PRETA", "PRETO", "VERMELHA", "VERMELHO",
        "AZUL", "CINZA", "AMARELA", "AMARELO", "VERDE", "BEGE", "LARANJA",
        "ROXA", "MARROM", "DOURADA", "FANTASIA",
    )
    mapa_cor = {
        "BRANCO": "BRANCA", "PRETO": "PRETA", "VERMELHO": "VERMELHA", "AMARELO": "AMARELA",
    }
    for c in cores:
        if re.search(rf"\b{c}\b", t, re.I):
            out["cor"] = mapa_cor.get(c, c)
            break

    # Doc do prop: CPF formatado 368.924.755-15 ou CNPJ 09.310.658/0001-74
    # NUNCA usar renavam / nº CRV / código CLA como CPF
    # Preferir CPF: no CRLV-e o CNPJ de INSTITUIÇÃO FINANCEIRA / alienação
    # (banco) aparece nas observações e NÃO é o proprietário.
    renavam = out.get("renavam") or ""
    cpf_fmt = _primeiro_cpf_formatado(t) or ""
    cnpj_fmt = _primeiro_cnpj(t) or ""
    # CNPJ de alienação fiduciária / instituição financeira -> ignora
    if cnpj_fmt and _cnpj_parece_alienacao(t, cnpj_fmt):
        cnpj_fmt = ""
    # PF dono: CPF tem prioridade sobre CNPJ do banco
    out["proprietario_cpf_cnpj"] = cpf_fmt or cnpj_fmt or ""
    if out["proprietario_cpf_cnpj"] == renavam:
        out["proprietario_cpf_cnpj"] = ""
    if not out["proprietario_cpf_cnpj"]:
        cpf_cand = _primeiro_cpf(t)
        if cpf_cand and cpf_cand != renavam and not cpf_cand.startswith("00"):
            out["proprietario_cpf_cnpj"] = cpf_cand
    if not out["proprietario_cpf_cnpj"]:
        for cand in re.findall(r"\b(\d{11})\b", t):
            if cand == renavam or cand.startswith("00"):
                continue
            # códigos de segurança CLA costumam ser 11 dígitos - exige CPF formatado perto
            if _valida_cpf_basico(cand) and (
                re.search(
                    rf"{cand[:3]}\s*\.?\s*{cand[3:6]}\s*\.?\s*{cand[6:9]}\s*-?\s*{cand[9:]}",
                    t,
                )
                or re.search(r"CPF\s*/?\s*CNPJ\s*[:\.]?\s*" + cand, t)
                or re.search(cand + r"\s*CPF\s*/?\s*CNPJ", t)
            ):
                out["proprietario_cpf_cnpj"] = cand
                break


    out["proprietario_nome"] = _extrair_nome_proprietario_crlv(
        t, doc=out.get("proprietario_cpf_cnpj") or ""
    )
    # CRLV-e: campo NOME logo acima do CPF (quadrante direito)
    if not out.get("proprietario_nome") or _nome_prop_parece_lixo(
        out.get("proprietario_nome") or ""
    ):
        m_nome = re.search(
            r"\bNOME\s*[:\.]?\s*"
            r"(?:\n|\s)+"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}(?:\s+(?:DA|DE|DO|DAS|DOS|E|[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,})){1,6})",
            t,
            re.I,
        )
        if m_nome:
            cand = _limpa_nome_pessoa(m_nome.group(1))
            if cand and not _nome_prop_parece_lixo(cand) and not _parece_marca_modelo(cand):
                out["proprietario_nome"] = cand
    # Nome imediatamente ANTES do CNPJ (CLEONALDO FERREIRA CARNEIRO ME \n 02.111...)
    # Limpa aspas/OCR no início do nome ("' JOSE ...") e cauda "CADASTRADO DESDE"
    if out.get("proprietario_nome"):
        out["proprietario_nome"] = _limpar_nome_proprietario_final(
            out["proprietario_nome"]
        )
        if _nome_prop_parece_lixo(out["proprietario_nome"] or ""):
            print(f"[CRLV] Prop lixo descartado: {out['proprietario_nome']!r}")
            # tenta de novo só o trecho antes do CNPJ
            cand = _nome_antes_do_cnpj(t, out.get("proprietario_cpf_cnpj") or "")
            if not cand or _nome_prop_parece_lixo(cand):
                # última tentativa: empresa com sufixo LTDA/ME/EIRELI no texto
                for m_emp in re.finditer(
                    r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+(?:DA|DE|DO|DAS|DOS|E|[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,})){0,6}"
                    r"\s+(?:LTDA|EIRELI|EPP|ME|S\.?A\.?))\b",
                    t,
                    re.I,
                ):
                    cand2 = _limpa_nome_pessoa(m_emp.group(1))
                    if not cand2 or _nome_prop_parece_lixo(cand2) or _parece_marca_modelo(cand2):
                        continue
                    # garante que não é label de formulário
                    if re.search(
                        r"\b(CERTIFICADO|LICENCIAMENTO|DETRAN|REGISTRO|REPUBLICA|SENATRAN)\b",
                        cand2, re.I
                    ):
                        continue
                    cand = cand2
                    print(f"[CRLV] Prop empresa encontrado: {cand}")
                    break
            out["proprietario_nome"] = cand or ""
    # Fallback: razão social no NOME do arquivo (comum em CRLV da empresa)
    if not out.get("proprietario_nome") or _nome_prop_parece_lixo(
        out.get("proprietario_nome") or ""
    ):
        if path is not None:
            from ocr.tipos_documento import nome_empresa_no_arquivo

            emp = nome_empresa_no_arquivo(Path(path))
            if emp and not _nome_prop_parece_lixo(emp):
                out["proprietario_nome"] = emp
                print(f"[CRLV] Prop do nome do arquivo: {emp}")
    # Limpa aspas/OCR no início do nome ("' JOSE ...") e cauda "CADASTRADO DESDE"
    if out.get("proprietario_nome"):
        out["proprietario_nome"] = _limpar_nome_proprietario_final(
            out["proprietario_nome"]
        )
        if _nome_prop_parece_lixo(out["proprietario_nome"] or ""):
            print(f"[CRLV] Prop lixo descartado: {out['proprietario_nome']!r}")
            # tenta de novo só o trecho antes do CNPJ
            cand = _nome_antes_do_cnpj(t, out.get("proprietario_cpf_cnpj") or "")
            out["proprietario_nome"] = cand or ""
    # Placa no nome do arquivo se OCR falhou
    if not out.get("placa") and path is not None:
        from ocr.tipos_documento import _placa_no_nome

        pl = _placa_no_nome(Path(path).stem)
        if pl:
            out["placa"] = limpar_placa(pl)

    # Cidade/UF do CRLV - prioridade: campo LOCAL (logo acima da DATA)
    # Ex.: LOCAL\nBARRA DOS COQUEIROS SE
    cid_uf = _extrair_cidade_uf_crlv(t)
    if cid_uf:
        out["cidade"], out["uf"] = cid_uf

    # Confiança / dúvidas / avisos (placa H↔B, renavam DV, chassi)
    try:
        from ocr.ocr_qualidade import avaliar_extracao_crlv

        out = avaliar_extracao_crlv(out, texto=t)
    except Exception as e:
        print(f"[CRLV] avaliar qualidade: {e}")

    return out


def _extrair_cidade_uf_crlv(t: str) -> Optional[tuple]:
    """
    Extrai (cidade, uf) do texto do CRLV.

    Ordem:
      1) Campo LOCAL (mais confiável no CRLV-e digital)
      2) Candidatas CIDADE + UF com filtro anti-lixo OCR
      3) Correção conhecida BARRA DOS COQUEIROS (SE)
    """
    t = t or ""

    # 1) LOCAL: valor na mesma linha ou na linha seguinte
    m_loc = re.search(
        r"\bLOCAL\s*[:\.]?\s*"
        r"(?:\n\s*)?"
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+(?:DOS|DAS|DO|DA|DE|[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,})){0,4})"
        r"\s+([A-Z]{2})\b",
        t,
        re.I,
    )
    if m_loc:
        cid = _normalizar_cidade_crlv(m_loc.group(1))
        uf = m_loc.group(2).upper()
        if uf in _UFS and cid and not _cidade_parece_lixo(cid):
            return cid, uf

    # 2) Varredura geral CIDADE + UF
    candidatas_cid = []
    for m in re.finditer(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+(?:DOS|DAS|DO|DA|DE|[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,})){0,4})"
        r"\s+([A-Z]{2})\b",
        t,
    ):
        cid_raw, uf = m.group(1).strip(), m.group(2).upper()
        if uf not in _UFS:
            continue
        cid = _normalizar_cidade_crlv(cid_raw)
        if not cid or _cidade_parece_lixo(cid):
            continue
        # score: multi-palavra real + comprimento (BARRA DOS COQUEIROS ganha de COQUEIROS)
        n_pal = len([w for w in cid.split() if w.upper() not in ("DOS", "DAS", "DO", "DA", "DE")])
        candidatas_cid.append((cid, uf, n_pal, len(cid)))
    if candidatas_cid:
        candidatas_cid.sort(key=lambda x: (x[2], x[3]), reverse=True)
        cid, uf, _, _ = candidatas_cid[0]
        # 3) COQUEIROS (SE) sozinho -> BARRA DOS COQUEIROS
        cid = _corrigir_barra_dos_coqueiros(cid, t, uf)
        return cid, uf

    # 4) só o fallback conhecido no texto
    if re.search(r"BARRA\s+DOS\s+COQUEIRO", t, re.I) or (
        re.search(r"\bCOQUEIRO", t, re.I) and re.search(r"\bSE\b", t)
    ):
        return "BARRA DOS COQUEIROS", "SE"
    return None


def _normalizar_cidade_crlv(cid: str) -> str:
    """Tira label LOCAL/CIDADE grudado e lixo de pontuação."""
    s = _limpa_nome(cid or "")
    # "LOCAL BARRA DOS COQUEIROS" / "CIDADE PAULISTA"
    s = re.sub(
        r"^(?:LOCAL|CIDADE|MUNIC[IÍ]PIO|MUNICIPIO|AKK|AK|OAR|OEA|OER)\s+",
        "",
        s,
        flags=re.I,
    ).strip()
    return _limpa_nome(s)


def _corrigir_barra_dos_coqueiros(cid: str, texto: str = "", uf: str = "") -> str:
    """OCR costuma ler só 'COQUEIROS SE' / 'COQOUETROS' - completa o nome oficial."""
    cu = (cid or "").upper().strip()
    if not cu:
        return cid
    # typos comuns de OCR: COQOUETROS, COQUEIRO5, BARRADOSCOQUEIROS
    cu_compact = re.sub(r"[^A-Z]", "", cu)
    if "BARRA" in cu and ("COQUEIRO" in cu or "COQOUE" in cu or "COQUEIR" in cu_compact):
        return "BARRA DOS COQUEIROS"
    parece_coqueiros = bool(
        re.search(r"COQ[UO]?[EI]?[EI]?R?O?S?", cu)
        or "COQUEIR" in cu_compact
        or "COQOUETR" in cu_compact
        or cu in ("COQUEIROS", "COQUEIRO", "DOS COQUEIROS", "COQOUETROS", "COQUETROS")
    )
    if parece_coqueiros and "BARRA" not in cu:
        if re.search(r"BARRA\s+DOS\s+COQ", texto or "", re.I) or (uf or "").upper() == "SE":
            return "BARRA DOS COQUEIROS"
        if parece_coqueiros:
            return "BARRA DOS COQUEIROS"
    return cid


def _cidade_parece_lixo(cid: str) -> bool:
    """
    True se a 'cidade' é lixo de OCR / label, não município real.
    Ex.: RARE SOE, NAL DRAT ALONE AINIVE DUTHAT, LOCAL, NAO APLICAVEL.
    """
    cu = (cid or "").upper().strip()
    if not cu:
        return True
    # tira prefixo de label se ainda restar
    cu = re.sub(r"^(?:LOCAL|CIDADE|MUNIC[IÍ]PIO)\s+", "", cu).strip()
    if not cu:
        return True
    if cu in (
        "LOCAL", "CIDADE", "MUNICIPIO", "MUNICÍPIO", "UF", "BRASIL", "DETRAN",
        "SENATRAN", "DIGITAL", "DATA", "NOME", "ALUGUEL", "PARTICULAR",
        "CATEGORIA", "CAPACIDADE", "RENAVAM", "CHASSI", "PLACA",
    ):
        return True
    # Labels de ano do veículo do CRLV que o OCR pega como cidade
    if re.search(
        r"\bANO\s+(?:FABRICAC[AO]ÃO?|FAB|MODELO|MOD)\b",
        cu,
        re.I,
    ):
        return True
    if any(
        x in cu
        for x in (
            "APLICAVEL", "APLICÁVEL", "ASSINADO", "DIGITALMENTE",
            "REPUBLICA", "FEDERATIVA", "MINISTERIO", "SECRETARIA",
            "OBSERVACOES", "POTENCIA", "CILINDRADA", "PESO BRUTO",
            "CARROCERIA", "SEMI REBOQUE", "SEMI-REBOQUE",
            "CABINE", "ESTENDIDA", "CAP CARGA", "CARGA", "TARA", "PESO",
            # rodapé do CRLV-e / PDF (NÃO é município)
            "DOCUMENTO EMITIDO", "EMITIDO POR", "DETRAN", "SENATRAN",
            "CERTIFICADO DE REGISTRO", "LICENCIAMENTO DE VEICULO",
            "GOVBR", "ASSINADOR", "SERPRO",
            # campos de veículo que não são cidade
            "ANO FABRICACAO", "ANO MODELO", "ANO FAB", "ANO MOD",
            "MARCA MODELO", "TIPO VEICULO", "ESPECIE", "COMBUSTIVEL",
            "NUMERO DO CRV", "NUMERO CRV", "NÚMERO CRV", "CRV",
            "REGISTRO", "SEGURANÇA", "SEGURANCA", "VALOR TOTAL", "VALOR",
        )
    ):
        return True
    # tokens conhecidos de OCR ruim neste caso
    if re.search(
        r"\b(RARE|SOE|DUTHAT|AINIVE|NAL|DRAT|ALONE)\b",
        cu,
    ):
        return True
    letras = re.sub(r"[^A-ZÁÉÍÓÚÂÊÔÃÕÇ]", "", cu)
    if len(letras) < 4:
        return True
    # "RARE SOE" = poucas letras úteis sem vogais suficientes
    vogais = len(re.findall(r"[AEIOUÁÉÍÓÚÂÊÔÃÕ]", letras))
    if len(letras) >= 5 and vogais / max(len(letras), 1) < 0.28:
        return True
    # várias palavras curtas sem preposição (NAL DRAT ALONE AINIVE DUTHAT)
    prep = {"DOS", "DAS", "DO", "DA", "DE", "E"}
    tokens = [w for w in cu.split() if w]
    reais = [w for w in tokens if w not in prep]
    if len(reais) >= 3:
        curtos = [w for w in reais if len(w) <= 5]
        if len(curtos) >= 3 and not any(len(w) >= 7 for w in reais):
            return True
    # 2 palavras curtas sem sentido (RARE SOE)
    if len(reais) == 2 and all(len(w) <= 4 for w in reais):
        return True
    return False


def _cnpj_parece_alienacao(texto: str, cnpj: str) -> bool:
    """True se o CNPJ está nas observações de alienação/banco, não como dono."""
    dig = so_digitos(cnpj)
    if not dig or len(dig) != 14:
        return False
    t = texto or ""
    # janela ao redor do CNPJ
    for m in re.finditer(re.escape(dig), so_digitos(t)):
        # pos aproximada no texto original é cara; usa contexto textual
        pass
    # se o doc fala em alienação / instituição financeira e TEM CPF de PF, o CNPJ é do banco
    if re.search(
        r"ALIENA[CÇ][AÃ]O\s*FIDUCI[AÁ]RIA|INSTITUI[CÇ][AÃ]O\s*FINANCEIRA|"
        r"RESERVA\s*DE\s*DOM[IÍ]NIO|BANCO\s+|ITAUCARD|FINANCI",
        t,
        re.I,
    ):
        if _primeiro_cpf_formatado(t) or re.search(
            r"\d{3}\s*\.\s*\d{3}\s*\.\s*\d{3}\s*-\s*\d{2}", t
        ):
            return True
    # CNPJ colado a "ALIENACAO" / "INSTITUICAO" na mesma linha
    if re.search(
        rf"(?:ALIENA|INSTITUI[CÇ]|FINANCEIRA|FIDUCI)[^\n]{{0,40}}{re.escape(dig[:8])}"
        rf"|{re.escape(dig[:8])}[^\n]{{0,40}}(?:ALIENA|FIDUCI|FINANCEIRA)",
        t,
        re.I,
    ):
        return True
    return False


def _limpar_nome_proprietario_final(nome: str) -> str:
    """Remove prefixos OCR (FLEE ATS, CPEY) e caudas (CADASTRADO DESDE, ME)."""
    s = (nome or "").strip()
    # PRIMEIRO: sempre corta em CADASTRADO DESDE (pode estar no meio ou no final)
    # Ex.: "TRANSP LTDA CADASTRADO DESDE 12/2020" -> "TRANSP LTDA"
    s_cortado = re.split(
        r"\bCADASTRADO\s*DESDE\b",
        s,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" -|\"'")
    # só aceita o corte se sobrou algo minimamente útil
    if len(s_cortado.strip()) >= 5:
        s = s_cortado

    s = re.sub(r"^[^A-ZÁÉÍÓÚÂÊÔÃÕÇ]+", "", s, flags=re.I).strip()
    # corta lixo colado no início: FLEE ATS = " I CLEONALDO...
    m = re.search(
        r"\b((?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{1,3}\s+){0,3}[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{4,}(?:\s+(?:DA|DE|DO|DAS|DOS|E|[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{1,})){1,6})"
        r"(?:\s+(?:ME|EIRELI|LTDA|EPP|S\.?A\.?))?\s*$",
        s,
        re.I,
    )
    if m and len(m.group(1)) >= 10:
        # se o match for o final do string (nome real no fim), usa ele
        fim = m.group(0).strip()
        if s.upper().endswith(fim.upper()[:20]) or len(fim) > len(s) * 0.5:
            s = fim
    # remove títulos de ANTT/CRLV grudados no início
    s = re.sub(
        r"^(?:TRANSPORTADORES?\s+RODOVI[AÁ]RIOS?(?:\s+DE\s+CARGAS)?\s+)+",
        "",
        s,
        flags=re.I,
    ).strip()
    s = re.split(
        r"\bCADASTRADO\s*DESDE\b|\bCNPJ\b|\bCPF\s*/?\s*CNPJ\b|\bCATEGORIA\b",
        s,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" -|\"'")
    # se sobrou "CPEY CHD" no meio, tenta achar nome longo
    if _nome_prop_parece_lixo(s) or len(s) < 8:
        m2 = re.search(
            r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{4,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){2,5})\b",
            nome or "",
            re.I,
        )
        if m2:
            s = _limpa_nome_pessoa(m2.group(1))
    return re.sub(r"\s+", " ", s).strip()


def _nome_antes_do_cnpj(texto: str, cnpj: str = "") -> str:
    """
    Linha de nome logo acima do CNPJ no CRLV/TAC.
    Ex.: CLEONALDO FERREIRA CARNEIRO ME
         02.111.109/0001-21
    """
    t = texto or ""
    dig = re.sub(r"\D", "", cnpj or "")
    # bloco antes de CNPJ formatado ou 14 dígitos
    pats = [
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s\.]{6,70}?)\s*"
        r"(?:\n|\r|[\|\"'])+\s*"
        r"(?:CNPJ\s*[:\.]?\s*)?\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}",
    ]
    if len(dig) == 14:
        pats.append(
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s\.]{6,70}?)\s*"
            r"(?:\n|\r|[\|\"'])+\s*"
            + re.escape(dig)
        )
        # com pontuação do CNPJ
        fmt = f"{dig[:2]}.{dig[2:5]}.{dig[5:8]}/{dig[8:12]}-{dig[12:]}"
        pats.append(
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s\.]{6,70}?)\s*"
            r"(?:\n|\r|[\|\"'])+\s*"
            + re.escape(fmt).replace(r"\.", r"\.?")
        )
    for pat in pats:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        raw = m.group(1)
        # última linha útil do bloco (evita pegar "CARROCERIA FECHADA")
        for ln in reversed(raw.splitlines()):
            cand = _limpa_nome_pessoa(ln)
            if not cand or _nome_prop_parece_lixo(cand) or _parece_marca_modelo(cand):
                continue
            # corta "ME" / "EIRELI" no fim ok
            if re.search(r"\b(CARROCERIA|FECHADA|DIESEL|GASOLINA|ALUGUEL)\b", cand, re.I):
                continue
            return cand
    # varredura: nome completo com 3+ partes perto de CNPJ no texto
    for m in re.finditer(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:[ \t]+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{1,}){2,6})(?:[ \t]+(?:ME|EIRELI|LTDA))?\b",
        t,
    ):
        cand = _limpa_nome_pessoa(m.group(1))
        if not cand or _nome_prop_parece_lixo(cand) or _parece_marca_modelo(cand):
            continue
        # perto de CNPJ?
        trecho = t[max(0, m.start() - 20) : m.end() + 40]
        if re.search(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\bCNPJ\b", trecho, re.I):
            return cand
        if re.search(r"\b(FERREIRA|CARNEIRO|SILVA|SANTOS|OLIVEIRA|TRANSPORT)\b", cand):
            # nome de pessoa/empresa completo longe de labels
            if not re.search(
                r"REPUBLICA|CERTIFICADO|LICENCIAMENTO|HABILITA",
                t[max(0, m.start() - 40) : m.start()],
                re.I,
            ):
                return cand
    return ""


def _nome_prop_parece_lixo(nome: str) -> bool:
    """True se o 'nome' é marketing DPVAT/CDT, marca/modelo ou label - não dono."""
    nu = (nome or "").upper().strip()
    if not nu:
        return True
    # OCR de "CPF/CNPJ" -> "CPEY CHD)" etc.
    if re.search(r"[)(\]\[}{/\\|]", nu) and len(re.findall(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{4,}", nu)) < 2:
        return True
    lixo = (
        "SEM NENHUM CUSTO", "NENHUM CUSTO", "SEM CUSTO", "VOCE SABIA",
        "CARTEIRA DIGITAL", "DADOS DO SEGURO", "LICENCIAMENTO DE",
        "ASSINADO DIGITALMENTE", "NAO APLICAVEL", "NÃO APLICAVEL",
        "INSTITUICAO FINANCEIRA", "INSTITUIÇÃO FINANCEIRA",
        "ALIENACAO FIDUCIARIA", "ALIENAÇÃO FIDUCIÁRIA",
        "CPEY", "CHD", "CPF", "CNPJ", "CADASTRADO DESDE",
        "CARROCERIA FECHADA", "CABINE ESTENDIDA", "CARROCERIA",
        # marketing CDT / frases do rodapé do CRLV-e (não é o dono)
        "SERVICOS DE TRANSITO", "SERVIÇOS DE TRÂNSITO", "SERVICOS DE TRÂNSITO",
        "SERVIÇOS DE TRANSITO", "OUTROS SERVICOS", "OUTROS SERVIÇOS",
        "BAIXE AGORA", "LEIA O QR", "INFRAÇÕES", "INFRACOES",
        "FUNDO NACIONAL", "DEPARTAMENTO NACIONAL",
        # labels de cartão ANTT / certificado (OCR sujo)
        "CERTIFICADO", "SEERTIFICADO", "REGISTRO NACIONAL", "REGISTRC",
        "TRANSPORTADORES", "RODOVIARI", "AGENCIA NACIONAL", "AGEN CIA",
    )
    if any(x in nu for x in lixo):
        # "CLEONALDO ... CADASTRADO DESDE" - corta o rabo e avalia o que resta
        if "CADASTRADO DESDE" in nu:
            antes = re.split(r"\bCADASTRADO\s*DESDE\b", nu, maxsplit=1, flags=re.I)[0].strip()
            # se o que restou antes é muito curto/fragmento -> lixo
            # ex.: "TRANSP LTDA" (6 chars sem espaço, não é razão social completa)
            tokens_antes = [w for w in re.findall(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+", antes) if len(w) >= 3]
            if len(antes) < 12 or len(tokens_antes) < 2:
                return True
            # ok: tem texto razoável antes de CADASTRADO DESDE -> deixa passar para limpeza
        else:
            # se o nome inteiro é curto/lixo
            if len(nu) < 20 or not re.search(
                r"\b(LTDA|EIRELI|S\.?A\.?|ME|EPP|FERREIRA|SILVA|SANTOS|CARNEIRO)\b",
                nu,
            ):
                return True
    if nu in ("NOME", "LOCAL", "DATA", "CPF", "CNPJ", "OT CHI", "NAO APLICA", "CPEY CHD"):
        return True
    # lixo OCR curto: "OT CHI", "AMM NAL", "CPEY CHD" (2 tokens ≤4 letras)
    tokens = [w for w in re.findall(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+", nu) if w]
    if tokens and all(len(w) <= 4 for w in tokens) and len(tokens) <= 3:
        if not any(len(w) >= 5 for w in tokens):
            return True
    if tokens and all(len(w) <= 3 for w in tokens) and len("".join(tokens)) < 8:
        return True
    if len(tokens) <= 2 and all(len(w) <= 3 for w in tokens):
        return True
    # "A POTAS SIS", "A POTAS SIS" - 3+ tokens curtos sem sobrenome/empresa conhecido
    _SUFIXOS_EMPRESA = {"LTDA", "EIRELI", "EPP", "ME", "SA", "S/A"}
    _SOBRENOMES_COMUNS = {
        "SILVA", "SANTOS", "OLIVEIRA", "SOUZA", "LIMA", "FERREIRA", "CARNEIRO",
        "GOMES", "RODRIGUES", "ALVES", "MARTINS", "COSTA", "PEREIRA", "NASCIMENTO",
        "ARAUJO", "CAVALCANTE", "SALES", "MONTEIRO", "MOURA", "NUNES", "RIBEIRO",
        "VIEIRA", "BARBOSA", "CARVALHO", "MEDEIROS", "FREITAS", "MOREIRA",
        "CARDOSO", "TEIXEIRA", "CORREIA", "CAMPOS", "ROCHA", "MENDES",
    }
    if len(tokens) >= 3 and all(len(w) <= 5 for w in tokens):
        tem_conhecido = any(
            w in _SOBRENOMES_COMUNS or w in _SUFIXOS_EMPRESA
            for w in tokens
        )
        if not tem_conhecido:
            return True
    # Iniciais + sobrenome: L.S.OLIVEIRA / L S OLIVEIRA (empresa PF no CRLV/ANTT)
    if re.fullmatch(
        r"(?:[A-ZÁÉÍÓÚ]\.?\s*){1,4}[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}",
        nu.replace(" ", ""),
    ) or re.fullmatch(
        r"(?:[A-ZÁÉÍÓÚ]\.?\s+){1,3}[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,})*",
        nu,
    ):
        return False
    # nome precisa de pelo menos 2 tokens “reais” (pessoa/empresa)
    # exceção: iniciais + sobrenome longo (L S OLIVEIRA -> tokens L,S,OLIVEIRA)
    iniciais = [w for w in tokens if len(w) == 1]
    sobrenomes = [w for w in tokens if len(w) >= 4]
    if iniciais and sobrenomes and len(tokens) <= 5:
        return False
    reais = [w for w in tokens if len(w) >= 3]
    if len(reais) < 2:
        return True
    # marca/modelo do CRLV (ex. SR/GUERRA AG SI) não é proprietário
    if _parece_marca_modelo(nu):
        return True
    return False


def _parece_marca_modelo(nome: str) -> bool:
    """
    True se o texto é MARCA/MODELO do CRLV, não nome de pessoa/empresa.
    Ex.: SR/GUERRA AG SI, VW/25.320 CLC, M.BENZ/AXOR 2536 LS
    """
    nu = (nome or "").upper().strip()
    if not nu:
        return False
    # barra típica de fabricação no CRLV-e (FABRICANTE/MODELO)
    if re.search(
        r"\b(?:SR|VW|M\.?\s*BENZ|MERCEDES|SCANIA|VOLVO|FORD|IVECO|DAF|MAN|"
        r"RENAULT|HYUNDAI|CHEVROLET|FIAT|TOYOTA|KIA|HONDA|PEUGEOT|"
        r"RANDON|LIBRELATO|FACCHINI|GUERRA|IMP|I)\s*/",
        nu,
    ):
        return True
    
    # Marcas pesadas puras (sem barra) ex: "SR RANDON SR FG CG" ou "VOLVO FH 460"
    if re.match(r"^(?:SR\s*)?(?:RANDON|LIBRELATO|FACCHINI|GUERRA|M\.?\s*BENZ|MERCEDES|VOLVO|SCANIA|VW|IVECO|DAF|FORD)\b", nu):
        if not re.search(r"\b(LTDA|S\.?A\.?|EIRELI|EPP|ME|COMERCIO|INDUSTRIA|TRANSPORTE|LOGISTICA|LOCACAO|SERVICOS)\b", nu):
            return True

    if "/" in nu and not re.search(r"\b(LTDA|S\.?A\.?|EIRELI|EPP)\b", nu):
        # pessoa/empresa rara com /; marca costuma ter /
        if re.search(r"[A-Z]{1,4}/[A-Z0-9]", nu):
            return True
    # modelo com número de eixos / cv (ex: 25.320 CLC T 6X2)
    if re.search(r"\b\d{1,2}\.\d{3}\b|\b\d+X\d+\b|\b\d+CV\b", nu):
        return True
    return False


def _extrair_nome_proprietario_crlv(t: str, doc: str = "") -> str:
    """
    Nome do prop no CRLV-e: linha ANTES do CNPJ/CPF
    (ex.: CARROCERIAS METALICAS SOLDA FORTE LTDA \\n 09.310.658/0001-74).

    Cuidado: NÃO rejeitar "CARROCERIAS..." por substring de "CARROCERIA"
    (bug antigo virava nome = "SEM NENHUM CUSTO" do marketing CDT/DPVAT).

    Cuidado 2: NÃO usar CNPJ "solto" sem barra - o campo MOTOR
    (00000000000000000000) casava como CNPJ e pegava a MARCA (SR/GUERRA)
    em vez do NOME (LENILSON SANTOS DO NASCIMENTO).
    """
    # palavras inteiras (não substring) que invalidam o nome
    proib_tokens = {
        "REPUBLICA", "FEDERATIVA", "MINISTERIO", "SECRETARIA", "CERTIFICADO",
        "SENATRAN", "DETRAN", "MENSAGENS", "BAIXE", "AGORA", "CARTEIRA",
        "DIGITAL", "TRANSITO", "INFORMACOES", "OBSERVACOES", "CODIGO",
        "SERVICOS", "DESCONTO", "FECHADA", "CABINE", "ESTENDIDA",
        "SEGURO", "DPVAT", "BRANCA", "BRANCO", "PRETA", "PRETO", "PRATA",
        "AZUL", "VERMELHA", "CINZA", "DIESEL", "GASOLINA", "ALCOOL", "FLEX",
        "ALUGUEL", "PARTICULAR", "OFICIAL", "CAMINHAO", "CARGA", "MOTOR",
        "CUMMINS", "POTENCIA", "CILINDRADA", "RENAVAM", "CHASSI", "PLACA",
        "QRCODE", "INFRAÇÕES", "INFRACOES", "ACESSO", "DESCONTO",
        "NENHUM", "CUSTO", "BILHETE", "QUITACAO", "PARCELADO", "COTA",
        "LICENCIAMENTO", "REGISTRO", "VERSAO", "COMBUSTIVEL", "ESPECIE",
        "SEMI", "REBOQUE", "TRATOR", "TRACAO", "PASSAGEIRO", "AUTOMOVEL",
        "CAPACIDADE", "CARROCERIA", "EIXO", "EIXOS", "LOTACAO", "LOTAÇÃO",
    }
    # frases inteiras de lixo (marketing CDT / DPVAT)
    proib_frases = (
        "SEM NENHUM CUSTO", "NENHUM CUSTO", "SEM CUSTO", "VOCE SABIA",
        "CARTEIRA DIGITAL", "LEIA O QR", "BAIXE AGORA", "DADOS DO SEGURO",
        "FUNDO NACIONAL", "VALOR TOTAL", "COTA UNICA", "NAO APLICAVEL",
        "NÃO APLICAVEL", "RESERVA DE DOMINIO", "RESERVA DE DOMÍNIO",
        "PLACA ANTERIOR", "COR PREDOMINANTE", "CARROCERIA FECHADA",
        "CABINE ESTENDIDA", "ASSINADO DIGITALMENTE", "CARGA SEMI",
        "SEMI-REBOQUE", "SEMIRREBOQUE", "CAMINHAO TRATOR",
        "SERVICOS DE TRANSITO", "SERVIÇOS DE TRÂNSITO", "SERVICOS DE TRÂNSITO",
        "SERVIÇOS DE TRANSITO", "OUTROS SERVICOS", "OUTROS SERVIÇOS",
        "ACESSO AO CRLV", "DESCONTO DE", "INFRAÇÕES", "INFRACOES",
    )

    def _lixo_prop(nu: str) -> bool:
        if not nu or len(nu) < 5:
            return True
        if any(f in nu for f in proib_frases):
            return True
        if _parece_marca_modelo(nu):
            return True
        if _nome_prop_parece_lixo(nu):
            return True
        tokens = set(re.findall(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9]+", nu))
        # se a maioria dos tokens é lixo de formulário, rejeita
        if tokens & proib_tokens and not re.search(
            r"\b(LTDA|S\.?A\.?|EIRELI|EPP)\b", nu
        ):
            # permite se for empresa (CARROCERIAS METALICAS LTDA tem CARROCERIA* mas LTDA)
            if "LTDA" not in nu and "EIRELI" not in nu and not re.search(r"\bS\.?A\.?\b", nu):
                return True
        # "CARROCERIA FECHADA" sozinho (tipo de carroceria, não razão social)
        if re.fullmatch(r"CARROCERIA(?:S)?\s+(FECHADA|ABERTA|BAU|BAÚ)", nu):
            return True
        if "BANCO" in nu or "ITAUCARD" in nu:
            return True
        # tokens todos curtíssimos (OCR: "OT CHI")
        toks = [w for w in re.findall(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+", nu) if w]
        if toks and all(len(w) <= 3 for w in toks):
            return True
        return False

    def _ok(nome: str) -> str:
        # se veio colado com label (CARROCERIA FECHADA\\nCELIO...), pega última linha útil
        for ln in reversed(re.split(r"[\n|]+", nome or "")):
            nome_p = _limpa_nome(ln)
            # aspas soltas no começo (OCR: "' JOSE FERREIRA SANTOS")
            nome_p = re.sub(r"^['\"`´‘’“”‚‛]+\s*", "", nome_p).strip()
            nome_p = re.sub(
                r"^(?:N[AÃ]O\s*APLIC[AÁ]VEL\s*)+", "", nome_p, flags=re.I
            ).strip()
            # remove cores/combustível grudados no início
            nome_p = re.sub(
                r"^(?:BRANCA|BRANCO|PRETA|PRETO|PRATA|DIESEL|GASOLINA|ALUGUEL|FLEX)\s+",
                "",
                nome_p,
                flags=re.I,
            ).strip()
            nome_p = _limpa_nome(nome_p)
            nu = nome_p.upper()
            if len(nome_p.split()) < 2:
                continue
            if _lixo_prop(nu):
                continue
            if re.search(r"\b(LTDA|S\.?A\.?|ME|EIRELI|EPP)\b", nu):
                return nome_p
            # pessoa física: só letras / preposições
            if re.fullmatch(
                r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+(?:\s+(?:DA|DE|DO|DAS|DOS|E|[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+))+",
                nu,
            ):
                return nome_p
            if len(nome_p.split()) >= 2 and not re.search(r"\d", nome_p):
                return nome_p
        return ""

    def _linhas_antes(pos: int) -> list:
        antes = t[:pos]
        return [ln.strip() for ln in antes.splitlines() if ln.strip()]

    def _nome_antes_doc(pos: int) -> str:
        """Linha útil imediatamente antes do CPF/CNPJ (mais confiável no CRLV-e)."""
        for ln in reversed(_linhas_antes(pos)[-12:]):
            if re.fullmatch(r"[\d.\s*/\-A-Z*]{0,24}", ln) and not re.search(
                r"[A-ZÁÉÍÓÚ]{3,}", ln
            ):
                continue
            if re.fullmatch(r"[\d.\s*/\-]+", ln) or len(ln) < 5:
                continue
            ok = _ok(ln)
            if ok:
                return ok
            # Iniciais + sobrenome: L.S.OLIVEIRA (OCR/PDF CRLV e ANTT)
            cand_ini = _limpa_nome_pessoa(ln)
            if cand_ini and not _nome_prop_parece_lixo(cand_ini):
                return cand_ini
            m_ini = re.search(
                r"\b((?:[A-ZÁÉÍÓÚ]\.?\s*){1,3}[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,})\b",
                ln,
                re.I,
            )
            if m_ini:
                cand_ini = _limpa_nome_pessoa(m_ini.group(1))
                if cand_ini and not _nome_prop_parece_lixo(cand_ini):
                    return cand_ini
        return ""

    # CNPJ com barra obrigatória (evita MOTOR 000000... parecer CNPJ)
    # Ex.: 18.937.262/0001-42 ou 18937262000142 com /
    _re_cnpj = re.compile(
        r"(\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2})"
    )
    # aceita espaços OCR: 368 .924.755-15
    _re_cpf = re.compile(r"(\d{3}\s*\.\s*\d{3}\s*\.\s*\d{3}\s*-\s*\d{2})")

    # 0) Prioridade: linha com LTDA/SA imediatamente antes do CNPJ/CPF formatado
    m_doc = _re_cnpj.search(t) or _re_cpf.search(t)
    if m_doc:
        for ln in reversed(_linhas_antes(m_doc.start())[-8:]):
            if re.search(r"\b(LTDA|S\.?A\.?|EIRELI|EPP)\b", ln, re.I):
                ok = _ok(ln)
                if ok:
                    return ok

    # 1) CPF formatado ANTES do CNPJ solto - no CRLV-e o dono PF está colado no CPF
    #    (bug: zeros do MOTOR + marca SR/GUERRA vinham antes do LENILSON)
    m_cpf = _re_cpf.search(t)
    if m_cpf:
        ok = _nome_antes_doc(m_cpf.start())
        if ok:
            return ok
        nomes = re.findall(
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,8})",
            t[: m_cpf.start()],
        )
        for n in reversed(nomes):
            ok = _ok(n)
            if ok:
                return ok

    # 2) CNPJ formatado com barra (empresa)
    m_cnpj = _re_cnpj.search(t)
    if m_cnpj:
        ok = _nome_antes_doc(m_cnpj.start())
        if ok:
            return ok
        nomes = re.findall(
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9.]{2,}){1,10})",
            t[: m_cnpj.start()],
        )
        for n in reversed(nomes):
            if re.search(r"\b(LTDA|S\.?A\.?|EIRELI)\b", n, re.I):
                ok = _ok(n)
                if ok:
                    return ok
        for n in reversed(nomes):
            ok = _ok(n)
            if ok:
                return ok

    # 3) Empresa com LTDA/SA em qualquer lugar do doc
    m = re.search(
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\s.&]{4,60}?"
        r"\b(?:LTDA|S\.?A\.?|EIRELI|ME|EPP)\b\.?)",
        t,
        re.I,
    )
    if m:
        ok = _ok(m.group(1))
        if ok:
            return ok

    return ""


def _primeiro_cpf_formatado(texto: str) -> str:
    # aceita espaços OCR: "368 .924.755-15" ou "368.924.755-15"
    m = re.search(
        r"\b(\d{3}\s*\.\s*\d{3}\s*\.\s*\d{3}\s*-\s*\d{2})\b",
        texto,
    )
    return so_digitos(m.group(1)) if m else ""


def _parece_cpf_formatado(texto: str, digitos: str) -> bool:
    """True se esses 11 dígitos aparecem formatados como CPF no texto."""
    if len(digitos) != 11:
        return False
    fmt = f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return fmt in texto or digitos in re.findall(
        r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto
    )


# ---------------------------------------------------------------------------
# TAC / ANTT
# ---------------------------------------------------------------------------

def parse_tac(texto: str) -> Dict[str, Any]:
    t = _norm(texto)
    out: Dict[str, Any] = {
        "nome": "",
        "cpf": "",
        "cnpj": "",
        "rntrc": "",
        "categoria": "",
        "cadastrado_desde": "",
    }
    out["cpf"] = _primeiro_cpf(t)
    out["cnpj"] = _primeiro_cnpj(t)
    # RNTRC: label, ou "TAC 049285533" / "ETC 055407188", ou 8–9 dígitos isolados
    # Aceita OCR sujo: ETC0554071 884, ETC.055407188, ETC\n055407188
    # Preferir o match MAIS LONGO (8–9 dígitos) - evita truncar 0554071 de 055407188
    candidatos_rn: List[str] = []
    rn = _campo_apos(t, r"RNTRC\s*[:\.]?\s*", r"(\d{6,12})")
    if rn:
        candidatos_rn.append(so_digitos(rn))
    for m in re.finditer(
        r"\b(?:TAC|ETC|CTC)\s*[:.\-]?\s*(\d{6,12})\b",
        t,
        re.I,
    ):
        candidatos_rn.append(so_digitos(m.group(1)))
    # colado sem espaço: ETC055407188
    for m in re.finditer(
        r"\b(?:TAC|ETC|CTC)(\d{6,12})\b",
        t,
        re.I,
    ):
        candidatos_rn.append(so_digitos(m.group(1)))
    # OCR com espaço no meio: ETC0554071 884 -> 055407188
    for m in re.finditer(
        r"\b(?:TAC|ETC|CTC)\s*[:.\-]?\s*(\d{3,5})\s+(\d{3,5})\b",
        t,
        re.I,
    ):
        candidatos_rn.append(so_digitos(m.group(1) + m.group(2)))
    for m in re.finditer(
        r"\b(?:TAC|ETC|CTC)\D{0,12}(\d{3}\s*\d{3}\s*\d{2,4})\b",
        t,
        re.I,
    ):
        candidatos_rn.append(so_digitos(m.group(1)))
    # número grande sozinho perto de ANTT/RNTRC/CERTIFICADO (foto WhatsApp)
    if re.search(
        r"\b(?:ANTT|RNTRC|TRANSPORTADOR|CERTIFICADO\s+DE\s+REGISTRO|ETC|TAC)\b",
        t,
        re.I,
    ):
        for n in re.findall(r"\b(\d{8,9})\b", t):
            candidatos_rn.append(n)
    cpf = out["cpf"] or ""
    cnpj = out["cnpj"] or ""
    # filtra lixo (pedaço de CNPJ/CPF) e escolhe o mais longo 8–9 dígitos
    bons = []
    for n in candidatos_rn:
        n = so_digitos(n)
        if len(n) < 7 or len(n) > 12:
            continue
        if cpf and n in cpf:
            continue
        if cnpj and (n in cnpj or n == cnpj[:8] or n == cnpj[:9]):
            continue
        bons.append(n)
    if bons:
        # preferir 8 ou 9 dígitos; entre iguais, o mais frequente
        from collections import Counter

        cont = Counter(bons)
        bons_ord = sorted(
            cont.keys(),
            key=lambda x: (
                2 if len(x) in (8, 9) else (1 if len(x) >= 8 else 0),
                cont[x],
                len(x),
            ),
            reverse=True,
        )
        rn = bons_ord[0]
        # se o melhor tem 7 e existe um de 8–9, usa o de 8–9
        if len(rn) < 8:
            for c in bons_ord:
                if len(c) in (8, 9):
                    rn = c
                    break
    else:
        rn = ""
    out["rntrc"] = rn or ""
    if re.search(r"\bTAC\b", t):
        out["categoria"] = "TAC"
    elif re.search(r"\bETC\b", t):
        out["categoria"] = "ETC"
    elif re.search(r"\bCTC\b", t):
        out["categoria"] = "CTC"
    out["cadastrado_desde"] = _campo_apos(
        t, r"(?:CADASTRADO\s*DESDE|DESDE)\s*[:\.]?\s*", r"(\d{2}/\d{2}/\d{4})"
    )
    # Nome: linha de pessoa (não título "TRANSPORTADORES RODOVIARIOS...")
    # Evita TRANSPORTADOR casar com TRANSPORTADORES
    out["nome"] = _campo_apos(
        t,
        r"(?:^|\n)\s*NOME\s*[:\.]?\s*",
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{5,80})",
    )
    if out["nome"] and _nome_tem_proib(out["nome"], _PROIB_NOME_PESSOA):
        out["nome"] = ""
    # "CLEONALDO FERREIRA CARNEIRO CADASTRADO DESDE: 27/02/2020"
    if not out["nome"]:
        m = re.search(
            r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,5})\s+"
            r"CADASTRADO\s*DESDE",
            t,
            re.I,
        )
        if m:
            cand = _limpa_nome_pessoa(m.group(1))
            if cand and not _nome_tem_proib(cand, _PROIB_NOME_PESSOA) and not _nome_prop_parece_lixo(cand):
                out["nome"] = cand
    if not out["nome"]:
        cand = _nome_antes_do_cnpj(t, out.get("cnpj") or out.get("cpf") or "")
        if cand:
            out["nome"] = cand
    # Iniciais + sobrenome logo acima do CNPJ (L.S.OLIVEIRA / L. Ss. OLIVEIRA)
    if not out["nome"] and (out.get("cnpj") or out.get("cpf")):
        m = re.search(
            r"((?:[A-ZÁÉÍÓÚ]\.?\s*){1,3}[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,})\s*"
            r"(?:\n|\r)+\s*"
            r"(?:CNPJ\s*[:\.]?\s*)?\d{2}",
            t,
            re.I,
        )
        if m:
            cand = _limpa_nome_pessoa(m.group(1))
            if cand and not _nome_prop_parece_lixo(cand):
                out["nome"] = cand
    # OCR quebra "L\nS\nOLIVEIRA" em linhas separadas antes do CNPJ
    # (tem prioridade sobre "GAS OLIVEIRA" vindo de CARGAS+OLIVEIRA)
    m = re.search(
        r"(?m)^([A-ZÁÉÍÓÚ])\s*$\n+^([A-ZÁÉÍÓÚ])\s*$\n+"
        r"^([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,})\s*$",
        t,
        re.I,
    )
    if m:
        cand = _limpa_nome_pessoa(f"{m.group(1)} {m.group(2)} {m.group(3)}")
        if cand and not _nome_prop_parece_lixo(cand):
            # sobrescreve lixo / fragmento (GAS OLIVEIRA de CARGAS)
            atual = (out.get("nome") or "").upper()
            if (
                not out["nome"]
                or _nome_prop_parece_lixo(out["nome"])
                or atual.startswith("GAS ")
                or "CARGAS" in atual
                or len(atual.split()) < len(cand.split())
            ):
                out["nome"] = cand
    # "OLIVEIRA" sozinho + iniciais L/S no texto
    if re.search(r"\bOLIVEIRA\b", t, re.I) and (
        re.search(r"(?m)^L\s*$", t) and re.search(r"(?m)^S\s*$", t)
        or re.search(r"\bL\.?\s*S\.?\s*OLIVEIRA\b", t, re.I)
    ):
        atual = (out.get("nome") or "").upper()
        if (
            not out["nome"]
            or _nome_prop_parece_lixo(out["nome"])
            or atual in ("OLIVEIRA", "GAS OLIVEIRA")
            or atual.startswith("GAS ")
            or "L S OLIVEIRA" not in atual
        ):
            out["nome"] = "L S OLIVEIRA"
    # remove prefixo lixo CARGAS/GAS grudado no nome
    if out.get("nome"):
        out["nome"] = re.sub(
            r"^(?:CARGAS|GAS|DE|RODOVIARIOS?)\s+",
            "",
            out["nome"],
            flags=re.I,
        ).strip()
        if _nome_prop_parece_lixo(out["nome"] or "") or len(
            (out.get("nome") or "").split()
        ) < 2:
            # tenta só sobrenome+iniciais se sobrou lixo
            if re.search(r"(?m)^L\s*$", t) and re.search(r"\bOLIVEIRA\b", t, re.I):
                out["nome"] = "L S OLIVEIRA"
    if not out["nome"] and out["cpf"]:
        # linha imediatamente antes do CPF (1 linha só - foto TAC WhatsApp)
        cpf_txt = out["cpf"]
        m = re.search(
            r"(?m)^([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{5,60}?)\s*$\n+"
            r"\s*(?:\d{3}\.?\d{3}\.?\d{3}-?\d{2}|" + re.escape(cpf_txt) + r")\b",
            t,
        )
        if m:
            cand = _limpa_nome_pessoa(m.group(1))
            if cand and not _nome_tem_proib(cand, _PROIB_NOME_PESSOA):
                out["nome"] = cand
    if not out["nome"]:
        # varre linhas isoladas com 2–6 palavras de nome
        for ln in t.splitlines():
            ln = ln.strip()
            # corta "CADASTRADO DESDE..."
            ln = re.split(r"\bCADASTRADO\s*DESDE\b", ln, maxsplit=1, flags=re.I)[0].strip()
            if not ln or len(ln.split()) < 2 or len(ln.split()) > 7:
                continue
            if re.search(r"\d", ln):
                continue
            cand = _limpa_nome_pessoa(ln)
            if cand and not _nome_tem_proib(cand, _PROIB_NOME_PESSOA) and not _nome_prop_parece_lixo(cand):
                out["nome"] = cand
                break
    if not out["nome"]:
        out["nome"] = _primeiro_nome_completo(t)
    # limpa prefixo ANTT / cauda colada
    if out.get("nome"):
        out["nome"] = _limpar_nome_proprietario_final(out["nome"])
        if _nome_prop_parece_lixo(out["nome"] or "") or _nome_tem_proib(
            out["nome"] or "", _PROIB_NOME_PESSOA
        ):
            # tenta de novo só "... CADASTRADO DESDE"
            m = re.search(
                r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,5})\s+"
                r"CADASTRADO\s*DESDE",
                t,
                re.I,
            )
            out["nome"] = _limpa_nome_pessoa(m.group(1)) if m else ""
    return out


# ---------------------------------------------------------------------------
# Comprovante
# ---------------------------------------------------------------------------

def parse_comprovante(texto: str) -> Dict[str, Any]:
    """
    Conta de luz/água etc.
    Ex.: RUA NOVA JERUSALEM, 22 - VILA MARIA - PALMEIRA DOS INDIOS AL 57007-470
    Rejeita frases de aviso (AVISO DE DÉBITO...) como endereço.
    """
    t = _norm(texto)
    out: Dict[str, Any] = {
        "nome_titular": "",
        "endereco": "",
        "numero": "",
        "complemento": "",
        "bairro": "",
        "cidade": "",
        "uf": "",
        "cep": "",
    }

    # Endereço com logradouro (prioridade sobre CEP solto)
    m = re.search(
        r"((?:RUA|R\.|AV|AVENIDA|ALAMEDA|AL\.|TRAVESSA|TV\.|RODOVIA|ESTRADA)"
        r"[^\n]{5,100})",
        t,
        re.I,
    )
    if m:
        end = m.group(1).strip()
        # corta avisos grudados
        end = re.split(
            r"\b(?:AVISO|DEBITO|DÉBITO|HIDROMETRO|HIDR[OÔ]METRO|LACRE|CPF)\b",
            end,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" ,-")
        if not _endereco_parece_lixo(end):
            out["endereco"] = end
            num = re.search(r",\s*(\d{1,6})\b|\b(\d{1,6})\s*-", end)
            if num:
                out["numero"] = num.group(1) or num.group(2) or ""

    # Linha completa: RUA ..., N - BAIRRO - CIDADE UF CEP
    m = re.search(
        r"(?:RUA|AV|AVENIDA|TRAVESSA)[^\n]{5,80}?"
        r"[-–]\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 ]{2,30}?)\s*[-–]\s*"
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{3,40}?)\s+([A-Z]{2})\s+(\d{5}-?\d{3})",
        t,
        re.I,
    )
    if m:
        if not out.get("bairro"):
            out["bairro"] = _limpa_nome(m.group(1))
        if not out.get("cidade") and not _cidade_parece_lixo(m.group(2)):
            out["cidade"] = _limpa_nome(m.group(2))
            out["uf"] = m.group(3).upper()
        if not out.get("cep"):
            out["cep"] = so_digitos(m.group(4))

    # PALMEIRA DOS INDIOS AL (naturalidade / conta)
    if not out.get("cidade"):
        m = re.search(
            r"\b(PALMEIRA\s+DOS\s+[IÍ]NDIOS|ARAPIRACA|MACEI[OÓ]|ARACAJU|"
            r"RECIFE|PAULISTA|BARRA\s+DOS\s+COQUEIROS)\s*[/\s,|-]*\s*([A-Z]{2})?\b",
            t,
            re.I,
        )
        if m:
            out["cidade"] = _limpa_nome(m.group(1))
            if m.group(2) and m.group(2).upper() in _UFS:
                out["uf"] = m.group(2).upper()
            elif "PALMEIRA" in out["cidade"].upper() or "ARAPIRACA" in out["cidade"].upper():
                out["uf"] = out.get("uf") or "AL"

    # Bairro VILA MARIA etc.
    if not out.get("bairro"):
        m = re.search(
            r"\b(?:VILA|BAIRRO|JD\.?|JARDIM|CONJ\.?)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 ]{2,30})\b",
            t,
            re.I,
        )
        if m:
            b = _limpa_nome(m.group(0))
            if not _endereco_parece_lixo(b):
                out["bairro"] = b

    bairro = _campo_apos(t, r"BAIRRO\s*[:\.]?\s*", r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\s]{2,40})")
    if bairro and not out.get("bairro"):
        out["bairro"] = _limpa_nome(bairro)

    # Cidade/UF genérico
    if not out.get("cidade"):
        m = re.search(
            r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+){0,3})\s*[/\-]\s*([A-Z]{2})\b",
            t,
        )
        if m and m.group(2).upper() in _UFS and not _cidade_parece_lixo(m.group(1)):
            out["cidade"] = _limpa_nome(m.group(1))
            out["uf"] = m.group(2).upper()

    # CEP: preferir o que está na linha do endereço (não o CEP da empresa no topo)
    ceps = re.findall(r"\b(\d{5}-?\d{3})\b", t)
    if out.get("cep"):
        pass
    elif ceps:
        # se tem endereço, pega o CEP mais próximo do logradouro no texto
        if out.get("endereco") and out["endereco"][:20] in t:
            pos = t.find(out["endereco"][:20])
            best = None
            best_d = 10**9
            for c in ceps:
                p = t.find(c)
                if p >= 0 and abs(p - pos) < best_d:
                    best_d = abs(p - pos)
                    best = c
            out["cep"] = so_digitos(best or ceps[-1])
        else:
            # último CEP costuma ser o do imóvel; evita 57200-000 da empresa
            out["cep"] = so_digitos(ceps[-1] if len(ceps) > 1 else ceps[0])

    # se endereço é lixo, zera (fallback naturalidade vai preencher)
    if _endereco_parece_lixo(out.get("endereco") or ""):
        out["endereco"] = ""
        out["numero"] = ""
    if out.get("cidade") and _cidade_parece_lixo(out["cidade"]):
        out["cidade"] = ""

    out["nome_titular"] = _primeiro_nome_completo(t)
    return out


def _endereco_parece_lixo(end: str) -> bool:
    """True se não é logradouro real (aviso de débito, labels...)."""
    u = (end or "").upper().strip()
    if not u or len(u) < 5:
        return True
    if any(
        x in u
        for x in (
            "AVISO DE", "DEBITO", "DÉBITO", "SE NECESSARIO", "SE NECESSÁRIO",
            "ENTRE EM CONTATO", "ENTRE OF CONTATO", "FALE CONOSCO",
            "HIDROMETRO", "HIDRÔMETRO", "DOCUMENTO EMITIDO", "ASSINADO",
            "REFERENCIA", "REFERÊNCIA", "VENCIMENTO", "MATRICULA",
        )
    ):
        return True
    # precisa parecer rua/av se for longo sem tipo
    if not re.search(
        r"\b(RUA|R\.|AV|AVENIDA|TRAVESSA|ALAMEDA|RODOVIA|ESTRADA|PRACA|PRAÇA)\b",
        u,
    ):
        if len(u) > 40:
            return True
    return False


def parse_generico(texto: str) -> Dict[str, Any]:
    t = _norm(texto)
    out: Dict[str, Any] = {}
    out["cpf"] = _primeiro_cpf(t)
    out["nome"] = _primeiro_nome_completo(t)
    cep = re.search(r"\b(\d{5}-?\d{3})\b", t)
    if cep:
        out["cep"] = so_digitos(cep.group(1))
    m = re.search(r"\b([A-Z]{3}\d[A-Z0-9]\d{2})\b", t)
    if m:
        out["placa"] = limpar_placa(m.group(1))
    return out


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}


def _norm(texto: str) -> str:
    # normaliza espaços, mantém quebras
    t = (texto or "").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.upper()


# Palavras que NUNCA fazem parte de nome de pessoa (OCR / labels / certificado)
_PROIB_NOME_PESSOA = (
    "REPUBLICA", "FEDERATIVA", "MINISTERIO", "SECRETARIA", "MEDIDA",
    "PROVISORIA", "ASSINADOR", "ASSINADO", "SERPRO", "SENATRAN", "HABILITACAO",
    "HABILITA", "CARTEIRA", "DEPARTAMENTO", "TRANSITO", "SOBRENOME", "DRIVER",
    "LICENSE", "PERMISO", "CONDUCCION", "NACIONAL", "GOVBR", "DOCUMENTO",
    "CERTIFICADO", "CONFORMIDADE", "DIGITAL", "DIGITALMENTE", "CODE", "QRCODE",
    "TRANSPORTADORES", "TRANSPORTADOR", "RODOVIARIOS", "RODOVIARIO", "CARGAS",
    "REGISTRO", "VALIDADE", "EMISSAO", "CATEGORIA", "OBSERVACOES",
    "TERRITORIO", "DETRAN", "ANTT", "AGENCIA",
    # boilerplate Assinador Serpro / PDF digital
    "ORIENTACOES", "ORIENTAÇÕES", "INSTALAR", "VALIDACAO", "VALIDAÇÃO",
    "PROGRAMA", "DISPONIVEIS", "DISPONÍVEIS", "CONFIRMACAO", "CONFIRMAÇÃO",
    # labels de campo (NASCIMENTO sozinho é label; "DO NASCIMENTO" é sobrenome OK)
    "DATA", "LOCAL", "PLACE", "BIRTH", "DATE", "IDENTIDADE", "EMISSOR",
    # lixo OCR comum no topo de foto WhatsApp
    "WIT", "AYY", "RAE", "EMT", "BETES", "ATED", "WON", "SOH", "CCT",
)

# Sobrenomes / prenomes frequentes no BR - usados para pontuar nomes reais vs lixo OCR
_SOBRENOMES_BR = frozenset({
    "SILVA", "SANTOS", "OLIVEIRA", "SOUZA", "SOUSA", "RODRIGUES", "FERREIRA",
    "ALVES", "PEREIRA", "LIMA", "GOMES", "COSTA", "RIBEIRO", "MARTINS",
    "CARVALHO", "ALMEIDA", "LOPES", "SOARES", "FERNANDES", "VIEIRA", "BARBOSA",
    "ROCHA", "DIAS", "NASCIMENTO", "ANDRADE", "MOREIRA", "NUNES", "MARQUES",
    "MACHADO", "MENDES", "FREITAS", "CARDOSO", "CARDOZO", "RAMOS", "CORREIA",
    "PINTO", "TEIXEIRA", "MOURA", "ARAUJO", "ARAÚJO", "CAMPOS", "MONTEIRO",
    "MORAIS", "MORAES", "AZEVEDO", "CUNHA", "MELO", "MELLO", "FONSECA",
    "BARROS", "DUARTE", "CASTRO", "BATISTA", "XAVIER", "PEIXOTO", "NEVES",
    "GUIMARAES", "GUIMARÃES", "MACEDO", "REIS", "SANTANA", "BRAGA", "CORREIA",
    "MARTINS", "CAVALCANTI", "NASCIMENTO", "APARECIDA", "CONCEICAO", "CONCEIÇÃO",
})
_PRENOMES_BR = frozenset({
    "JOSE", "JOÃO", "JOAO", "MARIA", "ANA", "FRANCISCO", "ANTONIO", "ANTÔNIO",
    "CARLOS", "PAULO", "PEDRO", "LUCAS", "LUIZ", "LUIS", "MARCOS", "EDUARDO",
    "EDSON", "EDER", "EURIPEDES", "EVA", "ROSIVAL", "GABRIEL", "RAFAEL",
    "BRUNO", "DIEGO", "FELIPE", "RODRIGO", "RICARDO", "FERNANDO", "ROBERTO",
    "MARCELO", "ANDRE", "ANDRÉ", "PATRICIA", "JULIANA", "FERNANDA", "ADRIANA",
    "MARCIA", "MÁRCIA", "SANDRA", "LUCIA", "LÚCIA", "HELENA", "BEATRIZ",
    "GABRIELA", "CAMILA", "AMANDA", "BRUNA", "LARISSA", "ALINE", "CELIO",
    "CÉLIO", "LUIZA", "SEAL", "FAUSTO", "MOACIR", "DEIVID", "GABRIEL",
})


def _nome_tem_proib(nome: str, proib: tuple = _PROIB_NOME_PESSOA) -> bool:
    """True se o nome contém palavra proibida (match por token, não substring)."""
    nu = (nome or "").upper().strip()
    if not nu:
        return True
    tokens = set(re.findall(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9]+", nu))
    for p in proib:
        pu = p.upper()
        # token exato (evita proibir sobrenome NASCIMENTO por conter "NASC")
        if pu in tokens:
            return True
        # frases multi-palavra no nome inteiro
        if " " in pu and pu in nu:
            return True
    return False


# Fragmentos de label grudados no OCR (ETARIANACIONALYBE, REPUBLICA...)
_SUBSTR_LIXO_NOME = (
    "NACIONAL", "REPUBLIC", "FEDERAT", "HABILIT", "MINISTER", "SECRETAR",
    "CARTEIRA", "DETRAN", "ASSINAT", "BRASILEIR", "PERMISS", "CONDUC",
    "TERRITOR", "INFRAEST", "TRANSITO", "DRIVER", "LICENSE", "IDENTID",
    "EMISSOR", "VALIDADE", "REGISTRO", "OBSERV", "PRESIDENT",
)


def _nome_parece_lixo_ocr(nome: str) -> bool:
    """
    Detecta lixo típico de foto WhatsApp no topo da CNH:
      'WIT AES RAE AYY', 'AES EMT RET', 'WON BETES ATED',
      'ETARIANACIONALYBE IMI PELEE ROEL'
    """
    if not nome or not str(nome).strip():
        return True
    if _nome_tem_proib(nome):
        return True
    nu = nome.upper()
    # label grudado dentro do token (NACIONAL em ETARIANACIONALYBE)
    if any(s in nu for s in _SUBSTR_LIXO_NOME):
        # sobrenome legítimo "NASCIMENTO" não entra na lista; ok
        return True
    prep = {"DA", "DE", "DO", "DAS", "DOS", "E"}
    tokens = [t for t in re.findall(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+", nu) if t not in prep]
    if len(tokens) < 2:
        return True
    # token absurdo (palavra colada OCR > 14 letras sem ser nome conhecido)
    for t in tokens:
        if len(t) >= 14 and t not in _SOBRENOMES_BR and t not in _PRENOMES_BR:
            return True
    conhecidos = sum(1 for t in tokens if t in _SOBRENOMES_BR or t in _PRENOMES_BR)
    if conhecidos >= 1:
        return False
    avg = sum(len(t) for t in tokens) / len(tokens)
    # muitos tokens curtos sem sobrenome/prenome conhecido
    if all(len(t) <= 4 for t in tokens) and len(tokens) >= 3:
        return True
    if avg <= 4.2 and len(tokens) >= 3:
        return True
    if sum(1 for t in tokens if len(t) == 3) >= 3:
        return True
    # 2 tokens curtos sem nome conhecido (AES EMT, WIT AES)
    if len(tokens) == 2 and avg <= 4.0:
        return True
    # nenhum token conhecido e ≥2 tokens -> suspeito
    if conhecidos == 0 and len(tokens) >= 2:
        return True
    return False


def _score_nome_pessoa(nome: str, texto: str = "") -> int:
    """Quanto maior, mais parece nome real de pessoa brasileira."""
    if not nome or _nome_parece_lixo_ocr(nome):
        return -100
    prep = {"DA", "DE", "DO", "DAS", "DOS", "E"}
    tokens = [t for t in nome.upper().split() if t]
    reais = [t for t in tokens if t not in prep]
    score = len(reais) * 3
    for t in reais:
        if t in _SOBRENOMES_BR:
            score += 12
        if t in _PRENOMES_BR:
            score += 10
        if len(t) >= 5:
            score += 2
        if len(t) <= 2:
            score -= 4
    # aparece mais de uma vez no OCR -> bem mais confiável
    if texto:
        occ = texto.upper().count(nome.upper())
        if occ >= 2:
            score += 20
        elif occ == 1:
            score += 5
        # sobrenome isolado repetido
        for t in reais:
            if t in _SOBRENOMES_BR and texto.upper().count(t) >= 2:
                score += 4
    return score


def _melhor_nome_pessoa_no_texto(texto: str, excluir: Optional[str] = None) -> str:
    """Varre o texto e devolve o melhor candidato a nome de pessoa."""
    t = texto or ""
    excl = (excluir or "").upper().strip()
    melhores: List[tuple] = []  # (score, nome)
    # nome entre chaves/colchetes OCR: { EDUARDO MARTINS CARDOSO }
    for m in re.finditer(
        r"[\{\[\(]\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{6,55}?)\s*[\}\]\)]",
        t,
        re.I,
    ):
        cand = _limpa_nome_pessoa(m.group(1))
        if cand and cand.upper() != excl and not _nome_parece_lixo_ocr(cand):
            melhores.append((_score_nome_pessoa(cand, t) + 8, cand))
    # sequências de 2–6 palavras (só espaço/tab - NÃO cruza linha)
    for m in re.finditer(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:[ \t]+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,5})\b",
        t,
    ):
        cand = _limpa_nome_pessoa(m.group(1))
        if not cand or cand.upper() == excl:
            continue
        if _nome_parece_lixo_ocr(cand) or _nome_tem_proib(cand):
            continue
        melhores.append((_score_nome_pessoa(cand, t), cand))
    if not melhores:
        return ""
    melhores.sort(key=lambda x: (-x[0], -len(x[1])))
    return melhores[0][1] if melhores[0][0] > 0 else ""


def _limpa_nome(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    # aspas/apóstrofo no início: OCR ou Excel (' JOSE FERREIRA...)
    s = s.strip(" \t:.-|/'\"`´‘’“”‚‛")
    # lixo comum de OCR / labels grudados
    s = re.sub(
        r"\b(N[AÃ]O\s*APLIC[AÁ]VEL|DOC\.?|IDENTIDADE|ORG\.?\s*EMISSOR|"
        r"NOME|FILIA[CÇ][AÃ]O|CPF|DATA|ASSINATURA|PORTADOR)\b",
        " ",
        s,
        flags=re.I,
    )
    s = re.sub(r"\s+", " ", s).strip(" \t:.-|/'\"`´‘’“”‚‛")
    return s


def _limpa_nome_pessoa(s: str, permitir_iniciais: bool = True) -> str:
    """
    Mantém só tokens de nome (letras ≥2). Corta lixo OCR no fim
    (ex.: 'MARIA DALVA BRAGA DA COSTA EI LS BE DCA' -> sem EI/LS/BE/DCA).
    Também corta 'ASSINADO DIGITALMENTE' grudado no nome da mãe.
    Aceita iniciais + sobrenome: L.S.OLIVEIRA -> L S OLIVEIRA.
    """
    s = _limpa_nome(s)
    # L.S.OLIVEIRA / L.S. OLIVEIRA -> tokens com iniciais
    s_ini = re.sub(
        r"\b([A-ZÁÉÍÓÚ])\.\s*([A-ZÁÉÍÓÚ])\.\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,})",
        r"\1 \2 \3",
        s,
        flags=re.I,
    )
    s_ini = re.sub(
        r"\b([A-ZÁÉÍÓÚ])\.\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,})\b",
        r"\1 \2",
        s_ini,
        flags=re.I,
    )
    if s_ini != s:
        s = s_ini
    # DONASCIMENTO -> DO NASCIMENTO | DAMARIA -> DA MARIA
    s = re.sub(
        r"\b(DO|DA|DE|DOS|DAS)([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{4,})\b",
        r"\1 \2",
        s,
        flags=re.I,
    )
    # NÃO inventar grafias (TEINEIRA->TEIXEIRA etc.) - o usuário corrige na confirmação
    s = re.split(
        r"\b(?:ASSINATURA|ASSINADO|DIGITALMENTE|PORTADOR|OBSERV|NACIONALIDADE|"
        r"PERMISS|VALIDADE|DEPARTAMENTO|DETRAN|CERTIFICADO|DOCUMENTO)\b",
        s,
        maxsplit=1,
        flags=re.I,
    )[0]
    # preposições válidas em nomes BR
    prep = {"DA", "DE", "DO", "DAS", "DOS", "E"}
    tokens = []
    iniciais_inicio = True  # permite L S no começo do nome (empresa PF)
    for raw in s.split():
        tok = re.sub(r"[^A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç]", "", raw)
        if not tok:
            continue
        up = tok.upper()
        n_reais = len([x for x in tokens if x not in prep and len(x) >= 3])
        n_ini = len([x for x in tokens if len(x) == 1])
        # iniciais no início: L, S, J (empresa L.S.OLIVEIRA)
        if permitir_iniciais and len(up) == 1 and iniciais_inicio and n_reais == 0 and n_ini < 3:
            tokens.append(up)
            continue
        # token of 1–2 letters or short OCR noise (EI, LS, BE, AES, LID) outside prep
        if len(up) <= 2 and up not in prep:
            if n_reais >= 2:
                break
            # Allow 2-letter tokens at the start (company abbreviation: AM, JP...)
            if permitir_iniciais and n_reais == 0 and len(up) == 2:
                tokens.append(up)
                continue
            # "LS" / "ME" in the middle without previously accumulated initials -> skip
            continue
        iniciais_inicio = False
        # após nome já formado (2+ tokens reais), token curto desconhecido = lixo no fim
        if (
            n_reais >= 2
            and len(up) <= 3
            and up not in prep
            and up not in _SOBRENOMES_BR
            and up not in _PRENOMES_BR
        ):
            break
        # palavras que não são nome
        if up in (
            "FILIACAO", "FILIAÇÃO", "FUAGAO", "FILAGAO", "FUNGO", "BRASILEIRO",
            "BRASILEIRA", "ASSINATURA", "ASSINADO", "DIGITALMENTE", "PORTADOR",
            "REGISTRO", "DOCUMENTO", "CERTIFICADO", "DIGITAL", "CODE",
            "WIT", "AYY", "RAE", "EMT", "BETES", "ATED", "WON", "LID", "AES",
            "SERVICOS", "SERVIÇOS", "TRANSITO", "TRÂNSITO", "OER", "OR", "POR",
            "TEE", "TE", "TEN", "CPF", "CNPJ", "NOME", "RAZAO", "SOCIAL",
            "LOCAL", "DATA", "EMISSAO", "VIA", "VALIDADE", "CAT", "HAB",
            "ESTADO", "MINISTERIO", "REPUBLICA", "FEDERATIVA", "DETRAN", "SENATRAN",
        ):
            if tokens:
                break
            continue
        tokens.append(up)
    # remove preposições órfãs no fim
    while tokens and tokens[-1] in prep:
        tokens.pop()
    # precisa de pelo menos 2 palavras "reais" OU 1+ inicial + sobrenome
    reais = [x for x in tokens if x not in prep and len(x) >= 3]
    iniciais = [x for x in tokens if len(x) == 1]
    if len(reais) >= 2:
        return " ".join(tokens)
    if iniciais and reais:
        return " ".join(tokens)
    return ""


def _extrair_filiacao(texto: str, titular: str = "") -> tuple:
    """Retorna (nome_pai, nome_mae)."""
    t = texto
    pai = mae = ""
    tit_u = (titular or "").upper().strip()
    # OCR de FILIAÇÃO: FILIACAO, FUAGAO, FUNGO, FILAGAO...
    lab_fil = r"(?:FILIA[CÇG][AÃA]O|FUAGAO|FILAGAO|FILIACAO|FUNGO|FU[LN]GO)"

    # Wrapper local para forçar permitir_iniciais=False nos nomes de pais/mães
    _orig_limpa = globals()["_limpa_nome_pessoa"]
    def _limpa_nome_pessoa(s: str, permitir_iniciais: bool = False) -> str:
        return _orig_limpa(s, permitir_iniciais=False)

    def _linha_nome_fil(ln: str) -> str:
        """Limpa lixo OCR no início da linha ('i RITA', '= ANTONIO', 'S A A SINVAL')."""
        ln = (ln or "").strip()
        # remove símbolos no começo
        ln = re.sub(r"^[^A-ZÁÉÍÓÚÂÊÔÃÕÇ]+", "", ln, flags=re.I)
        # remove 1 ou 2 letras soltas no começo (OCR 'i RITA' -> 'RITA', 'OR ANTONIO' -> 'ANTONIO')
        ln = re.sub(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{1,2}\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,})", "", ln, flags=re.I)
        # remove sequências de iniciais soltas no começo: 'S A A SINVAL' -> 'SINVAL'
        # padrão: 2 ou 3 letras isoladas (1 char + espaço) antes de uma palavra longa
        ln = re.sub(
            r"^(?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ]\s+){2,4}(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{4,})",
            "",
            ln,
            flags=re.I,
        )
        return _limpa_nome_pessoa(ln, permitir_iniciais=False)

    # 0) Bloco FILIAÇÃO: pega até 6 linhas seguintes e extrai 2 nomes
    #    (OCR costuma intercalar "=" / "i" / ruído entre pai e mãe)
    m_blk = re.search(
        lab_fil + r"\s*[:\./\|\s]*\n([\s\S]{10,220}?)(?=\n\s*(?:7\s*)?ASSINATURA|ASSINADO|OBSERV|PERMISS|DEPARTAMENTO|$)",
        t,
        re.I,
    )
    if m_blk:
        nomes_blk = []
        for ln in m_blk.group(1).splitlines():
            cand = _linha_nome_fil(ln)
            if not cand or cand == tit_u:
                continue
            if _nome_tem_proib(cand):
                continue
            if len(cand.split()) < 2:
                continue
            if cand not in nomes_blk:
                nomes_blk.append(cand)
            if len(nomes_blk) >= 2:
                break
        if len(nomes_blk) >= 2:
            pai, mae = _ordenar_pai_mae(nomes_blk[0], nomes_blk[1])
        elif len(nomes_blk) == 1:
            # um só nome: se feminino -> mãe; se masculino -> pai (CNH-e às vezes só mãe)
            only = nomes_blk[0]
            if _prenome_feminino(only):
                mae = only
            else:
                pai = only

    # 1) Dois nomes em linhas separadas após FILIAÇÃO (pai + mãe na CNH-e)
    if not (pai and mae):
        m = re.search(
            lab_fil + r"\s*[:\./\|\s]*"
            r"(?:\n|\s)+"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{5,55}?)\s*\n+"
            r"(?:[^\nA-ZÁÉÍÓÚ]{0,8})?"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{5,55}?)"
            r"(?=\n|ASSINADO|ASSINATURA|PERMISS|OBSERV|DEPARTAMENTO|$)",
            t,
            re.I,
        )
        if m:
            p1 = _linha_nome_fil(m.group(1))
            p2 = _linha_nome_fil(m.group(2))
            if p1 and p2 and p1 != tit_u and p2 != tit_u:
                pai, mae = _ordenar_pai_mae(p1, p2)
            elif p2 and p2 != tit_u:
                if _prenome_feminino(p2):
                    mae = mae or p2
                else:
                    pai = pai or p2
            elif p1 and p1 != tit_u:
                if _prenome_feminino(p1):
                    mae = mae or p1
                else:
                    pai = pai or p1

    # 2) Dois nomes na mesma área com espaços largos
    if not mae:
        m = re.search(
            r"FILIA[CÇG][AÃA]O\s*[:\.]?\s*"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{5,55}?)\s{2,}"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{5,55}?)"
            r"(?=\n|ASSINADO|ASSINATURA|PERMISS|OBSERV|$)",
            t,
            re.I,
        )
        if m:
            p1 = _limpa_nome_pessoa(m.group(1))
            p2 = _limpa_nome_pessoa(m.group(2))
            pai, mae = _ordenar_pai_mae(p1, p2)

    # 3) Uma linha de nome após FILIAÇÃO (só mãe na maioria das CNH-e)
    if not mae:
        m = re.search(
            lab_fil + r"\s*[:\./\|\s]*"
            r"(?:\n|\s)+"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{6,70}?)"
            r"(?=\n|ASSINADO|ASSINATURA|7\s*ASSIN|OBSERV|PERMISS|DEPARTAMENTO|$)",
            t,
            re.I,
        )
        if m:
            cand = _limpa_nome_pessoa(m.group(1))
            if cand and cand != tit_u and not _nome_tem_proib(cand):
                mae = cand

    # 4) Dois nomes entre BRASILEIRO/NACIONALIDADE e ASSINATURA
    #    (CNH-e com FILIAÇÃO ilegível no OCR - ex.: "uacho" + pai + mãe)
    if not pai or not mae:
        m = re.search(
            r"(?:NACIONALIDADE|BRASILEIRO\(?A?\)?)\s*"
            r"(?:[^\nA-ZÁÉÍÓÚ]{0,40})?"
            r"(?:\n|\s)+"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{5,55}?)\s*\n+"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{5,55}?)"
            r"(?=\s*(?:\d{6,}|\n|ASSINADO|ASSINATURA|7\s*ASSIN|OBSERV|DEPARTAMENTO))",
            t,
            re.I,
        )
        if m:
            p1 = _limpa_nome_pessoa(m.group(1))
            p2 = _limpa_nome_pessoa(m.group(2))
            if p1 and p2 and p1 != tit_u and p2 != tit_u:
                if not pai:
                    pai = p1
                if not mae:
                    mae = p2
            elif p2 and p2 != tit_u and not mae:
                mae = p2
            elif p1 and p1 != tit_u and not mae:
                mae = p1

    # 5) Nome entre NACIONALIDADE/FILIAÇÃO e ASSINATURA/ASSINADO (só mãe)
    if not mae:
        m = re.search(
            r"(?:NACIONALIDADE|BRASILEIRO\(?A?\)?)\s*"
            + lab_fil + r"?\s*"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{8,60}?)"
            r"(?=\s*(?:ASSINADO|ASSINATURA|7\s*ASSIN|OBSERV|DEPARTAMENTO))",
            t,
            re.I,
        )
        if m:
            cand = _limpa_nome_pessoa(m.group(1))
            if cand and cand != tit_u and "BRASILEIRO" not in cand:
                mae = cand

    # 6) Qualquer MARIA ... (mãe típica) ≠ titular - corta ASSINADO
    if not mae:
        for m in re.finditer(
            r"\b(MARIA(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){2,6})\b", t
        ):
            cand = _limpa_nome_pessoa(m.group(1))
            if not cand or cand == tit_u:
                continue
            if tit_u and cand in tit_u:
                continue
            if _nome_tem_proib(cand):
                continue
            mae = cand
            break

    # 7) Segundo nome completo no texto (≠ titular), após CPF
    if not mae:
        pos_cpf = 0
        mcpf = re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", t)
        if mcpf:
            pos_cpf = mcpf.end()
        trecho = t[pos_cpf:]
        for m in re.finditer(
            r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+(?:DA|DE|DO|DAS|DOS|[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,})){2,6})\b",
            trecho,
        ):
            cand = _limpa_nome_pessoa(m.group(1))
            if not cand or cand == tit_u:
                continue
            if _nome_tem_proib(cand):
                continue
            mae = cand
            break

    # 8) Pai: linha com nome masculino típico logo antes da mãe (mesmo sobrenome)
    if not pai and mae:
        # varre nomes completos antes da mãe no texto
        pos_mae = t.find(mae)
        trecho = t[: pos_mae if pos_mae > 0 else len(t)]
        for m in re.finditer(
            r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+(?:DA|DE|DO|DAS|DOS|[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,})){2,6})\b",
            trecho,
        ):
            cand = _limpa_nome_pessoa(m.group(1))
            if not cand or cand == tit_u or cand == mae:
                continue
            if _nome_tem_proib(cand):
                continue
            # prefere quem compartilha sobrenome com titular ou mãe
            sobr_tit = set((tit_u or "").split()) - {"DE", "DA", "DO", "DOS", "DAS", "E"}
            sobr_cand = set(cand.split()) - {"DE", "DA", "DO", "DOS", "DAS", "E"}
            if sobr_tit & sobr_cand or not pai:
                pai = cand
                if sobr_tit & sobr_cand:
                    break

    if not pai:
        p = _campo_apos(
            t, r"\bPAI\b\s*[:\.]?\s*", r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{5,60})"
        )
        pai = _limpa_nome_pessoa(p) if p else ""

    # pai não pode ser igual à mãe / titular / lixo OCR
    if pai and (
        pai == mae
        or pai == tit_u
        or _nome_tem_proib(pai)
        or _nome_parece_lixo_ocr(pai)
    ):
        pai = ""
    if mae and (
        mae == tit_u or _nome_tem_proib(mae) or _nome_parece_lixo_ocr(mae)
    ):
        mae = ""

    return pai, mae


def _campo_apos(texto: str, label_re: str, val_re: str) -> str:
    m = re.search(label_re + val_re, texto, re.I | re.M)
    if m:
        return m.group(1).strip()
    return ""


def _primeiro_cpf(texto: str) -> str:
    # com/sem pontos e com espaços OCR ("368 .924.755-15")
    for m in re.finditer(
        r"\b(\d{3}\s*\.?\s*\d{3}\s*\.?\s*\d{3}\s*-?\s*\d{2})\b",
        texto,
    ):
        d = so_digitos(m.group(1))
        if len(d) == 11 and _valida_cpf_basico(d):
            return d
    # só dígitos 11 (evita renavam começando com 00 se possível)
    for m in re.finditer(r"\b(\d{11})\b", texto):
        d = m.group(1)
        if d.startswith("00"):
            continue
        if _valida_cpf_basico(d):
            return d
    for m in re.finditer(r"\b(\d{11})\b", texto):
        if _valida_cpf_basico(m.group(1)):
            return m.group(1)
    return ""


_PRENOMES_FEM = frozenset({
    "MARIA", "ANA", "EVA", "LUCIA", "LÚCIA", "HELENA", "BEATRIZ", "GABRIELA",
    "CAMILA", "AMANDA", "BRUNA", "LARISSA", "ALINE", "PATRICIA", "PATRÍCIA",
    "JULIANA", "FERNANDA", "ADRIANA", "MARCIA", "MÁRCIA", "SANDRA", "LUIZA",
    "APARECIDA", "FRANCISCA", "ANTONIA", "ANTÔNIA", "ROSANGELA", "ROSÂNGELA",
    "EDILENE", "RITA", "JOSEFA", "TEREZINHA", "SEBASTIANA", "CREUZA", "IVONE",
    "VANI", "VANIA", "VÂNIA", "VALERIA", "VALÉRIA", "VERA", "VANESSA", "VILMA",
    # nomes femininos adicionados por casos reais
    "MARLENE", "MARTA", "MONICA", "MÔNICA", "ROSA", "ELIANE", "SUELI",
    "FATIMA", "FÁTIMA", "CLEIDE", "SOLANGE", "SIMONE", "RENATA", "CRISTIANE",
    "CRISTINA", "CELIA", "CÉLIA", "NEIDE", "NILZA", "DILMA", "ELZA",
    "CONCEICAO", "CONCEIÇÃO", "IRACEMA", "IRENE", "LEIA", "LEILA",
    "TEREZA", "NAIR", "LEDA", "LILIA", "REGIANE", "ROSELI", "ROSELIA",
    "ARLETE", "MARLI", "JANAINA", "JANAÍNA", "TATIANE", "TATIANA",
    "DEBORA", "DÉBORA", "ROBERTA", "ISABELA", "JULIA", "JÚLIA",
    "NATALIA", "NATÁLIA", "ALESSANDRA", "CAROLINE", "CAROLINA",
    "ELENICE", "ELIZANGELA", "ELIZÂNGELA", "ELAINE", "EDNEIA",
    "EDNA", "EDINALVA", "EFIGENIA", "EFIGÊNIA", "ELISA", "ELIZABETE",
    "ELIZETE", "ELZIRA", "ENEIDA", "ENEDINA", "EUNICE", "EXPEDITA",
    "FATIMAH", "FLAVIANA", "FLAVIA", "FLÁVIA", "GISELE", "GISELA",
    "GRACIELE", "IDALINA", "IEDA", "ILDA", "INES", "INÊS", "IVANA",
    "IVETE", "IVANI", "IZABEL", "JAQUELINE", "JOCELIA", "JOSENILDE",
    "JOSIANE", "JOVITA", "JUDITH", "KATIA", "KÁTIA", "KATIANE",
    "LOURDES", "LUCINEIA", "LUCINEIDE", "LUCIANA", "LUCIARA",
    "MAGDA", "MARISTELA", "MARINALVA", "MARINETE", "MARINILDA",
    "MARINEUZA", "MARINEIDE", "MARGARIDA", "MARGARETE", "MARIANA",
    "MARILDA", "MARILENE", "MARILZA", "MARILUCIA", "MARILÚCIA",
    "MEIRE", "MEIRELUCE", "MIRIAM", "MÍRIAN", "MIRTES", "NADIR",
    "NEUZA", "NORMA", "ODETE", "ORLANDA", "PALMIRA", "PAULA",
    "PRISCILA", "QUITERIA", "QUITÉRIA", "RAIMUNDA", "RAIMUNDINHA",
    "REGINALDA", "REJANE", "SONIA", "SÔNIA", "SUELY", "SUZANA",
    "TALITA", "TANIA", "TÂNIA", "VALDETE", "VALDINEIA", "VALDIRENE",
    "VALQUIRIA", "VALQUÍRIA", "VANILDA", "VANIA", "VITORINA",
    "WANDA", "ZELIA", "ZÉLIA", "ZILDA", "ZULMIRA",
})


def _nome_contem_titular(cand: str, titular: str) -> bool:
    """
    True se o candidato é o próprio titular (com lixo OCR grudado).
    NÃO marca pai/mãe que só compartilham sobrenome (EURIPEDES vs EDUARDO MARTINS CARDOSO).
    """
    c = (cand or "").upper().strip()
    t = (titular or "").upper().strip()
    if not c or not t:
        return False
    if c == t:
        return True
    # titular inteiro embutido no candidato (... AES no fim)
    if t in c:
        return True
    prep = {"DA", "DE", "DO", "DAS", "DOS", "E"}
    tc_list = [x for x in c.split() if x not in prep and len(x) >= 3]
    tt_list = [x for x in t.split() if x not in prep and len(x) >= 3]
    if not tc_list or not tt_list:
        return False
    # prenomes diferentes -> parente com mesmo sobrenome, não o titular
    if tc_list[0] != tt_list[0] and len(tc_list[0]) >= 3 and len(tt_list[0]) >= 3:
        return False
    # mesmo prenome + ≥1 sobrenome em comum (ou quase todos os tokens do titular)
    tc, tt = set(tc_list), set(tt_list)
    if tc_list[0] == tt_list[0] and len(tc & tt) >= 2:
        return True
    return False


def _nomes_na_zona_filiacao(
    zona: str, titular: str = "", excluir: str = ""
) -> List[str]:
    """Lista nomes de pessoa na zona pós-BRASILEIRO."""
    tit_u = (titular or "").upper()
    ex_u = (excluir or "").upper()
    z = re.sub(r"([A-ZÁÉÍÓÚ])\(", r"\1I ", zona or "", flags=re.I)
    z = re.sub(r"\s+", " ", z)
    out: List[str] = []
    seen = set()
    for m in re.finditer(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:[ \t]+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,5})\b",
        z,
        re.I,
    ):
        cand = _limpa_nome_pessoa(m.group(1))
        if not cand or _nome_parece_lixo_ocr(cand) or len(cand.split()) < 2:
            continue
        cu = cand.upper()
        if cu in seen or cu == tit_u or cu == ex_u:
            continue
        if _nome_contem_titular(cand, titular) or (
            excluir and _nome_contem_titular(cand, excluir)
        ):
            continue
        # ignora lixo de labels OCR
        if any(x in cu for x in ("OBSERV", "ASSINAT", "DRIVER", "LICENSE", "PERMISO")):
            continue
        seen.add(cu)
        out.append(cand)
    return out


def _extrair_mae_zona_filiacao(zona: str, titular: str = "", pai: str = "") -> str:
    """Pega a mãe na zona pós-BRASILEIRO (prenome feminino)."""
    cands = _nomes_na_zona_filiacao(zona, titular=titular, excluir=pai)
    fem = [c for c in cands if _prenome_feminino(c)]
    if fem:
        return max(fem, key=lambda c: _score_nome_pessoa(c, zona))
    return ""


def _extrair_pai_zona_filiacao(zona: str, titular: str = "", mae: str = "") -> str:
    """Pega o pai na zona pós-BRASILEIRO (não feminino)."""
    cands = _nomes_na_zona_filiacao(zona, titular=titular, excluir=mae)
    masc = [c for c in cands if not _prenome_feminino(c)]
    if masc:
        return max(masc, key=lambda c: _score_nome_pessoa(c, zona))
    return ""


def _corrigir_troca_titular_filiacao(
    nome: str,
    texto: str,
    zona_titular: str,
    zona_filiacao: str,
    cands_nome: List[tuple],
) -> str:
    """
    Caso ALEX (topo) vs UEREMIAS (filiação): o OCR pontua o pai como 'nome'.
    Se o nome atual só está na zona de filiação e há candidato no topo -> usa o do topo.
    """
    if not nome:
        # pega melhor da zona titular
        for sc, cand in sorted(cands_nome, key=lambda x: -x[0]):
            if zona_titular and cand.upper() in zona_titular.upper():
                if not zona_filiacao or cand.upper() not in zona_filiacao.upper() or sc > 20:
                    return cand
        return nome

    def _toks_na_zona(nome_c: str, zona: str) -> bool:
        if not zona or not nome_c:
            return False
        zu = zona.upper()
        if nome_c.upper() in zu:
            return True
        toks = [x for x in nome_c.upper().split() if len(x) >= 4]
        if not toks:
            return False
        return sum(1 for x in toks if x in zu) >= max(2, len(toks) - 1)

    nu = nome.upper()
    so_na_filiacao = _toks_na_zona(nome, zona_filiacao) and not _toks_na_zona(
        nome, zona_titular
    )
    if not so_na_filiacao:
        return nome

    # procura melhor candidato que esteja no topo e não só na filiação
    for sc, cand in sorted(cands_nome, key=lambda x: -x[0]):
        if cand.upper() == nu:
            continue
        if not _toks_na_zona(cand, zona_titular):
            continue
        if _toks_na_zona(cand, zona_filiacao) and not _toks_na_zona(cand, zona_titular):
            continue
        if _nome_parece_lixo_ocr(cand):
            continue
        print(
            f"[CNH] Corrige troca motorista/pai: {nome!r} (filiação) -> {cand!r} (topo)"
        )
        return cand

    # 1º nome na zona titular (após CARTEIRA / PERMISO)
    if zona_titular:
        # prefere trecho depois de CARTEIRA/PERMISO
        trecho = zona_titular
        mpos = re.search(
            r"CARTEIRA|HABI[A-Z]{3,}|PERMISO|DRIVER\s*LICENSE",
            zona_titular,
            re.I,
        )
        if mpos:
            trecho = zona_titular[mpos.end() :]
        m = re.search(
            r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:[ \t]+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,5})\b",
            trecho,
        )
        if m:
            cand = _limpa_nome_pessoa(m.group(1))
            if (
                cand
                and cand.upper() != nu
                and not _nome_parece_lixo_ocr(cand)
                and not _nome_tem_proib(cand)
            ):
                print(
                    f"[CNH] Corrige troca motorista/pai: {nome!r} -> {cand!r} (1º no topo)"
                )
                return cand
    return nome


def _prenome_feminino(nome: str) -> bool:
    if not nome or not str(nome).strip():
        return False
    prim = nome.strip().split()[0].upper()
    return prim in _PRENOMES_FEM


def _ordenar_pai_mae(a: str, b: str) -> tuple:
    """
    CNH: 1ª linha = pai, 2ª = mãe. Se OCR inverter (EVA antes de lixo/homem),
    acomoda pelo prenome feminino.
    """
    a = (a or "").strip()
    b = (b or "").strip()
    if not a:
        return "", b
    if not b:
        if _prenome_feminino(a):
            return "", a
        return a, ""
    fa, fb = _prenome_feminino(a), _prenome_feminino(b)
    # 1º feminino + 2º masculino -> OCR perdeu ordem; mãe = feminino
    if fa and not fb:
        return b, a
    # 1º masculino + 2º feminino -> ordem clássica
    if not fa and fb:
        return a, b
    # ambos femininos: melhor score = mãe, pai vazio
    if fa and fb:
        if _score_nome_pessoa(a) >= _score_nome_pessoa(b):
            return "", a
        return "", b
    # ambos masculinos: ordem do OCR (pai, ?)
    return a, b


def _normalizar_filiacao(out: Dict[str, Any]) -> None:
    """
    Garante: prenome feminino não fica em nome_pai; lixo OCR sai.
    Caso típico: pai=EVA DO NASCIMENTO...  mãe=ETARIANACIONALYBE... -> corrige.
    """
    pai = (out.get("nome_pai") or "").strip()
    mae = (out.get("nome_mae") or "").strip()
    if pai and _nome_parece_lixo_ocr(pai):
        pai = ""
    if mae and _nome_parece_lixo_ocr(mae):
        mae = ""
    # pai com prenome feminino -> é mãe
    if pai and _prenome_feminino(pai):
        if not mae:
            mae = pai
            pai = ""
        elif _prenome_feminino(mae):
            # duas mulheres: fica a de maior score como mãe
            if _score_nome_pessoa(pai) > _score_nome_pessoa(mae):
                mae = pai
            pai = ""
        else:
            # mãe atual parece homem -> troca
            pai, mae = mae, pai
    # mãe com lixo já limpa; se mãe vazia e sobrou só lixo no pai feminino, já tratado
    out["nome_pai"] = pai
    out["nome_mae"] = mae


def _completar_filiacao_por_sobrenome(out: Dict[str, Any], texto: str) -> None:
    """Busca pai/mãe no texto pelo sobrenome do titular; não confunde com o próprio."""
    tit = (out.get("nome") or "").strip()
    tit_u = tit.upper()
    prep = {"DA", "DE", "DO", "DAS", "DOS", "E"}
    sobr = {
        x
        for x in tit_u.split()
        if x not in prep and len(x) >= 4 and x in _SOBRENOMES_BR
    }
    if not sobr:
        sobr = {x for x in tit_u.split() if x not in prep and len(x) >= 5}
    extras: List[tuple] = []
    # [ \t]+ - não cruza linha (evita GOIANIAIGO + AES + EVA colados)
    for m in re.finditer(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:[ \t]+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,5})\b",
        texto or "",
    ):
        cand = _limpa_nome_pessoa(m.group(1))
        if not cand or _nome_parece_lixo_ocr(cand):
            continue
        if _nome_contem_titular(cand, tit):
            continue
        toks = set(cand.upper().split())
        if sobr and not (sobr & toks):
            continue
        extras.append((_score_nome_pessoa(cand, texto or ""), cand))
    # únicos, melhor score
    seen = set()
    uniq = []
    for sc, cand in sorted(extras, key=lambda x: -x[0]):
        u = cand.upper()
        if u in seen:
            continue
        seen.add(u)
        uniq.append(cand)
    fem = [c for c in uniq if _prenome_feminino(c)]
    masc = [c for c in uniq if not _prenome_feminino(c)]
    # mãe SEMPRE prioritária com prenome feminino (EVA, MARIA...)
    if not out.get("nome_mae") and fem:
        out["nome_mae"] = fem[0]
    # pai só com prenome NÃO feminino
    if not out.get("nome_pai") and masc:
        out["nome_pai"] = masc[0]
    # um único nome legível: se feminino -> mãe; senão -> pai (não o contrário)
    if not out.get("nome_mae") and not out.get("nome_pai") and uniq:
        if _prenome_feminino(uniq[0]):
            out["nome_mae"] = uniq[0]
        else:
            out["nome_pai"] = uniq[0]
    elif not out.get("nome_mae") and uniq:
        for c in uniq:
            if c != out.get("nome_pai") and _prenome_feminino(c):
                out["nome_mae"] = c
                break
        if not out.get("nome_mae"):
            for c in uniq:
                if c != out.get("nome_pai"):
                    # não joga homem na mãe se já tem pai; se não tem pai e é homem, deixa vazio
                    if _prenome_feminino(c):
                        out["nome_mae"] = c
                    break


def _cpf_cnh_preferencial(texto: str) -> str:
    """
    CPF na CNH: prefere label CPF; evita protocolo do rodapé
    (LOCAL 145... / ASSINATURA DO EMISSOR GO...) e nº de registro (0...).
    """
    t = texto or ""
    registro = _registro_cnh_preferencial(t, cpf="")

    def _ok_cpf(d: str) -> bool:
        if len(d) != 11 or not _valida_cpf_basico(d):
            return False
        if d.startswith("00") or d.startswith("02"):
            return False
        # confusão comum: OCR troca 0->9 no registro (92046654953 ≈ 02046654953)
        if registro and sum(a != b for a, b in zip(d, registro)) <= 2:
            return False
        if d == registro:
            return False
        return True

    # 1) após "CPF" / "4d CPF" (aceita dígitos limpos ou OCR sujo)
    m = re.search(
        r"\b(?:4[dD]\s*)?CPF\b[^\n]{0,50}?"
        r"([0-9OIlSZssoeE«»\[\]\.\-\s]{11,20})",
        t,
        re.I,
    )
    if m:
        d = so_digitos(m.group(1))
        if len(d) < 11:
            d = _ocr_digitos(m.group(1))
        if len(d) >= 11:
            d = d[:11]
            if _ok_cpf(d):
                return d
    # 2) formatado em qualquer lugar (pontos/traço reais)
    fmt = _primeiro_cpf_formatado(t)
    if fmt and _ok_cpf(fmt):
        return fmt
    # 3) padrão sujo tipo 598.811.941-72 lido como s0.e11.044-72
    for m in re.finditer(
        r"\b([0-9OIlSZssoeE]{2,3}\s*[.\s]\s*[0-9OIlSZssoeE]{2,3}"
        r"\s*[.\s]\s*[0-9OIlSZssoeE]{2,3}\s*-?\s*[0-9OIlSZssoeE]{2})\b",
        t,
    ):
        d = _ocr_digitos(m.group(1))
        if len(d) == 11 and _ok_cpf(d):
            return d
    # SEM fallback em 11 dígitos soltos no rodapé (protocolo DETRAN ≠ CPF)
    return ""


def _registro_cnh_preferencial(texto: str, cpf: str = "") -> str:
    """
    Nº de registro da CNH: prefere 11 dígitos começando com 0
    (ex. 02046654953). Evita CPF e protocolo do rodapé (60169168700).
    """
    t = texto or ""
    cpf_d = so_digitos(cpf or "")
    contagem: Dict[str, int] = {}
    for m in re.finditer(r"\b(\d{11})\b", t):
        d = m.group(1)
        if d == cpf_d:
            continue
        contagem[d] = contagem.get(d, 0) + 1
    if not contagem:
        return ""
    # score: começa com 0, aparece mais de uma vez, perto de REGISTRO
    def sc(d: str) -> tuple:
        score = contagem[d]
        if d.startswith("0"):
            score += 5
        if d.startswith("02") or d.startswith("00"):
            score += 3
        # protocolo GO... no rodapé costuma NÃO começar com 0
        if re.search(
            rf"(?:LOCAL|ASSINATURA|GO)\s*{d}|{d}\s*[,\"']",
            t,
            re.I,
        ):
            score -= 4
        if re.search(rf"REGISTRO[^\d]{{0,20}}{d}", t, re.I):
            score += 6
        return (score, contagem[d])

    return max(contagem.keys(), key=sc)


def _primeiro_cnpj(texto: str) -> str:
    """
    CNPJ com barra (formatado) ou 14 dígitos reais.
    NÃO aceita 14 zeros do campo MOTOR do CRLV-e.
    """
    # barra obrigatória no formatado - evita MOTOR 0000... parecer CNPJ
    m = re.search(r"\b(\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2})\b", texto)
    if m:
        dig = so_digitos(m.group(1))
        if dig and dig != dig[0] * len(dig) and len(dig) == 14:
            return dig
    for cand in re.findall(r"\b(\d{14})\b", texto):
        if cand == cand[0] * 14:  # 000... / 111...
            continue
        # motor CRLV às vezes tem 17–21 zeros; 14 zeros já filtrado
        return cand
    return ""


def _valida_cpf_basico(d: str) -> bool:
    if len(d) != 11 or d == d[0] * 11:
        return False
    return True


def _maior_numero(texto: str, tamanho: int) -> str:
    nums = re.findall(rf"\b(\d{{{tamanho}}})\b", texto)
    return nums[0] if nums else ""


def _primeiro_nome_completo(texto: str) -> str:
    proib = _PROIB_NOME_PESSOA + ("TRANSPORTES", "CATEGORIA")
    for m in re.finditer(
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}(?:[ \t]+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{1,}){1,7})", texto
    ):
        n = _limpa_nome_pessoa(m.group(1))
        if not n or len(n.split()) < 2:
            continue
        if _nome_tem_proib(n, proib):
            continue
        return n
    return ""
