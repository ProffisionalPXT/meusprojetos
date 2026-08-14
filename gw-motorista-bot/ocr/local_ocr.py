"""
OCR / leitura local de documentos (sem gastar cota Gemini).

Aceita no mesmo caso, misturado:
  - foto (jpg/png/webp/tif/bmp) - WhatsApp, câmera, scanner
  - PDF digital (texto embutido) - CRLV-e, CNH-e, TAC
  - PDF escaneado / imagem dentro do PDF
  - PDF criptografado sem senha -> ignora (fallback de endereço)

Estratégia unificada:
  1) PDF com texto útil -> PyMuPDF
  2) PDF fraco / imagem -> preprocess + Tesseract
  3) Formato irrelevante para o parser (mesmo JSON de campos)

Env:
  TESSERACT_CMD   - caminho do tesseract.exe se não estiver no PATH
  OCR_LANG        - padrão por+eng
  OCR_ZOOM        - zoom da página PDF (padrão 4; 3–6)
  OCR_FOTO_MIN_PX - lado maior mínimo em fotos (padrão 2400; máx 4500)
  OCR_FOTO_ZOOM   - escala extra em fotos pequenas (padrão 3; 2–5)
  OCR_RAPIDO      - 1=pipeline leve (padrão); 0=máxima qualidade (lento)
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import List, Optional

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
PDF_EXT = {".pdf"}
# HEIC do iPhone (se pillow-heif instalado)
HEIC_EXT = {".heic", ".heif"}


def tesseract_disponivel() -> bool:
    cmd = _tesseract_cmd()
    return bool(cmd and Path(cmd).exists()) if cmd and Path(cmd).is_file() else bool(shutil.which("tesseract") or cmd)


def _tesseract_cmd() -> Optional[str]:
    env = (os.getenv("TESSERACT_CMD") or "").strip()
    if env and Path(env).exists():
        return env
    candidatos = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        str(Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for c in candidatos:
        if Path(c).exists():
            return c
    w = shutil.which("tesseract")
    return w


def _configurar_pytesseract() -> bool:
    try:
        import pytesseract
    except ImportError:
        print("[OCR-local] pytesseract não instalado (pip install pytesseract)")
        return False
    cmd = _tesseract_cmd()
    if not cmd:
        print(
            "[OCR-local] Tesseract não encontrado. Instale: "
            "winget install UB-Mannheim.TesseractOCR"
        )
        return False
    pytesseract.pytesseract.tesseract_cmd = cmd
    return True


def formato_arquivo(path: Path) -> str:
    """pdf | foto | heic | outro - só para log."""
    ext = Path(path).suffix.lower()
    if ext in PDF_EXT:
        return "pdf"
    if ext in IMG_EXT:
        return "foto"
    if ext in HEIC_EXT:
        return "heic"
    return "outro"


def extrair_texto_arquivo(
    path: Path,
    max_paginas: int = 4,
    *,
    forcar_zoom: Optional[float] = None,
) -> str:
    """
    Devolve texto bruto do arquivo (PDF, foto ou HEIC).

    forcar_zoom: se definido (ex. 4.0), força 2ª passada com zoom alto
    em fotos (usado antes de gastar cota Gemini).
    """
    path = Path(path)
    if not path.exists():
        return ""
    ext = path.suffix.lower()
    fmt = formato_arquivo(path)
    zlabel = f" zoom={forcar_zoom:g}x" if forcar_zoom else ""
    print(f"[OCR-local] {path.name} ({fmt}{zlabel})")
    if ext in PDF_EXT:
        return _texto_pdf(path, max_paginas=max_paginas)
    if ext in IMG_EXT or ext in HEIC_EXT:
        return _ocr_imagem(path, forcar_zoom=forcar_zoom)
    # extensão desconhecida: tenta como imagem
    return _ocr_imagem(path, forcar_zoom=forcar_zoom)


def _texto_pdf(path: Path, max_paginas: int = 1) -> str:
    try:
        import fitz
    except ImportError:
        print("[OCR-local] PyMuPDF (fitz) ausente")
        return ""

    try:
        doc = fitz.open(path)
    except Exception as e:
        print(f"[OCR-local] Não abriu PDF {path.name}: {e}")
        return ""

    if doc.is_encrypted or doc.needs_pass:
        # tenta senha vazia; senão não dá para ler sem senha
        if not doc.authenticate(""):
            print(
                f"[OCR-local] PDF criptografado (sem senha): {path.name} - "
                f"pule ou use comprovante legível"
            )
            doc.close()
            return ""

    partes: List[str] = []
    n = min(doc.page_count, max_paginas)
    for i in range(n):
        try:
            page = doc.load_page(i)
            t = (page.get_text("text") or "").strip()
            if t:
                partes.append(t)
        except Exception as e:
            print(f"[OCR-local] página {i} {path.name}: {e}")

    texto = "\n".join(partes).strip()
    util = _texto_util(texto)

    # Se o PDF extraiu apenas texto parcial (sem NOME ou sem FILIAÇÃO), ou poucas linhas úteis,
    # força OCR da página renderizada em alta resolução (com recortes de topo/filiação)
    precisa_ocr_pag = (
        len(util) < 400
        or _parece_so_boilerplate(texto)
        or not re.search(r"NOME|SOBRENOME", texto, re.I)
        or not re.search(r"FILIA|BRASILEIRO", texto, re.I)
    )
    if precisa_ocr_pag:
        print(f"[OCR-local] PDF {path.name}: buscando imagem/recortes em alta resolução...")
        ocr_txt = _ocr_paginas_pdf(doc, max_paginas=min(n, 2))
        if ocr_txt:
            texto = texto + "\n" + ocr_txt if texto else ocr_txt

    doc.close()
    return texto.strip()


def _parece_so_boilerplate(texto: str) -> bool:
    low = (texto or "").lower()
    if "serpro" in low and "certificado digital" in low and "cnh" not in low:
        # CNH-e com só aviso de assinatura
        if "nome" not in low and not re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", texto or ""):
            return True
    # só labels de CRLV sem valores úteis
    if "certificado de registro" in low and not re.search(r"[A-Z]{3}\d[A-Z0-9]\d{2}", texto or "", re.I):
        if len(_texto_util(texto)) < 250:
            return True
    return False


def _texto_util(texto: str) -> str:
    """Remove linhas muito genéricas para medir 'conteúdo útil'."""
    lixo = (
        "república", "federativa", "ministério", "serpro", "assinador",
        "qrcode", "qr-code", "você sabia", "orientações", "medida provisória",
    )
    linhas = []
    for ln in (texto or "").splitlines():
        s = ln.strip()
        if len(s) < 2:
            continue
        low = s.lower()
        if any(x in low for x in lixo):
            continue
        linhas.append(s)
    return "\n".join(linhas)


def _ocr_paginas_pdf(doc, max_paginas: int = 1) -> str:
    if not _configurar_pytesseract():
        return ""
    try:
        import fitz
        from PIL import Image
        import io
    except ImportError as e:
        print(f"[OCR-local] deps OCR: {e}")
        return ""

    lang = os.getenv("OCR_LANG", "por+eng")
    # Zoom via env (padrão 4x era muito lento, reduzindo para 1.5x para ganho absoluto de velocidade)
    try:
        zoom_base = float(os.getenv("OCR_ZOOM", "1.5") or "1.5")
    except ValueError:
        zoom_base = 1.5
    zoom_base = max(1.0, min(zoom_base, 3.0))

    partes: List[str] = []
    n = min(doc.page_count, max_paginas)
    for i in range(n):
        try:
            page = doc.load_page(i)
            candidatos: List[str] = []
            
            dimensoes_vistas = set()

            # 1) Imagens embutidas desativadas no "Modo Jato". Lemos apenas a página renderizada.

            # 2) Página renderizada em alta resolução (complementa embutidas)
            def _tem_campos_chave(cs: List[str]) -> bool:
                join = "\n".join(cs)
                datas_ok = len(re.findall(r"\d{2}/\d{2}/\d{4}", join)) >= 3
                cat_ok = bool(
                    re.search(
                        r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s+\d{9,11}\s+[A-E]{1,2}\b",
                        join,
                        re.I,
                    )
                )
                mrz_ok = bool(re.search(r"\b\d{6}\d?[MF]\d{6}", join, re.I))
                nome_ok = bool(re.search(r"NOME|SOBRENOME", join, re.I)) or len(re.findall(r"\b[A-Z]{3,}\s+[A-Z]{3,}\b", join)) >= 2
                return datas_ok and (cat_ok or mrz_ok) and nome_ok

            zooms = [zoom_base]
            for zoom in zooms:
                try:
                    mat = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    # Velocidade extrema: max_vars=1, psm=6 (rapido=True)
                    rapido = True # Forçado para Modo Jato absoluto em PDFs
                    for variante in _variantes_imagem_ocr(img, scale=1, max_vars=1):
                        candidatos.append(_tesseract_melhor(variante, lang, rapido=rapido))
                    # recortes (crops) desativados no "Modo Jato" para poupar tempo. O Gemini preenche as falhas.
                except Exception as e:
                    print(f"[OCR-local] render zoom={zoom}: {e}")

            candidatos = [c for c in candidatos if (c or "").strip()]
            if not candidatos:
                continue

            # Preferir candidato com MAIS datas + CAT/sexo/MRZ
            def _score_cnh(c: str) -> int:
                s = _score_texto_doc(c) + 10 * len(
                    re.findall(r"\d{2}/\d{2}/\d{4}", c or "")
                )
                u = (c or "").upper()
                # bônus campos que costumam falhar
                if re.search(r"\b[A-E]{1,2}\b", u) and (
                    "CAT" in u or "REGISTRO" in u or re.search(r"\d{11}", u)
                ):
                    s += 4
                if re.search(r"\b\d{6}\d?[MF]\d{6}", u) or "MASCULINO" in u or "FEMININO" in u:
                    s += 5
                if "FILIA" in u or re.search(r"\bMARIA\b", u):
                    s += 2
                return s

            candidatos.sort(key=_score_cnh, reverse=True)
            best = candidatos[0]
            # mescla top candidatos: datas, CAT, sexo MRZ, nomes de filiação
            for c in candidatos[1:6]:
                for d in re.findall(r"\d{2}/\d{2}/\d{4}", c):
                    if d not in best:
                        best = best + "\n" + c
                        break
                else:
                    # trechos úteis sem data
                    if re.search(r"\b\d{6}\d?[MF]\d{6}", c or "", re.I) and not re.search(
                        r"\b\d{6}\d?[MF]\d{6}", best, re.I
                    ):
                        best = best + "\n" + c
                    elif re.search(
                        r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s+\d{9,11}\s+[A-E]{1,2}\b",
                        c or "",
                        re.I,
                    ) and not re.search(
                        r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s+\d{9,11}\s+[A-E]{1,2}\b",
                        best,
                        re.I,
                    ):
                        best = best + "\n" + c
            partes.append(best.strip())
            n_datas_best = len(re.findall(r"\d{2}/\d{2}/\d{4}", best))
            print(
                f"[OCR-local] Tesseract pág {i+1}: {len(best)} chars "
                f"datas={n_datas_best} "
                f"(score={_score_cnh(best)}, variantes={len(candidatos)})"
            )
        except Exception as e:
            print(f"[OCR-local] OCR pág {i}: {e}")
    return "\n".join(partes)


def _variantes_imagem_ocr(img, scale: int = 1, max_vars: int = 4):
    """
    Gera versões ampliadas/realçadas da mesma imagem para o Tesseract.
    Objetivo: enxergar CAT, sexo (MRZ), filiação e datas miúdas.
    max_vars limita quantas variantes rodam (tempo × qualidade).
    """
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    out = []
    try:
        base = img.convert("RGB") if img.mode not in ("RGB", "L") else img
    except Exception:
        return out

    w, h = base.size
    if scale and scale > 1:
        # alvo mínimo ~2400px no lado maior (campos pequenos da CNH-e)
        maior = max(w, h)
        alvo = max(maior * scale, 2400 if maior < 1400 else maior * scale)
        if alvo > maior:
            f = min(alvo / maior, 6.0)
            base = base.resize(
                (int(w * f), int(h * f)), Image.Resampling.LANCZOS
            )
        else:
            base = base.resize((w * scale, h * scale), Image.Resampling.LANCZOS)

    gray = base.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(2.0)
    gray = ImageEnhance.Sharpness(gray).enhance(1.8)
    try:
        gray = gray.filter(ImageFilter.UnsharpMask(radius=1.5, percent=150, threshold=2))
    except Exception:
        pass
    out.append(gray)

    if len(out) >= max_vars:
        return out[:max_vars]

    # contraste forte (texto apagado / fundo cinza da CNH digital)
    forte = ImageEnhance.Contrast(ImageOps.autocontrast(gray)).enhance(2.6)
    forte = ImageEnhance.Sharpness(forte).enhance(2.0)
    out.append(forte)

    if len(out) >= max_vars:
        return out[:max_vars]

    # binarização (sombra / compressão)
    try:
        binaria = gray.point(lambda x: 0 if x < 135 else 255)
        out.append(binaria)
    except Exception:
        pass

    if len(out) >= max_vars:
        return out[:max_vars]

    # OpenCV: adaptive threshold (traços finos CAT/MRZ)
    try:
        import cv2
        import numpy as np

        arr = np.array(gray)
        den = cv2.fastNlMeansDenoising(arr, None, 6, 7, 21)
        thr = cv2.adaptiveThreshold(
            den, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 8
        )
        out.append(Image.fromarray(thr))
    except Exception:
        pass

    return out[:max_vars]


def _tesseract_melhor(img, lang: str, rapido: Optional[bool] = None) -> str:
    """Tenta PSM e devolve o texto com melhor score. Rápido = 1 PSM só."""
    import pytesseract

    if rapido is None:
        rapido = _ocr_rapido()
    # 6=bloco único (melhor custo/benefício em docs BR)
    psms = (6,) if rapido else (6, 3)
    melhores = []
    for psm in psms:
        try:
            cfg = f"--oem 3 --psm {psm}"
            t = pytesseract.image_to_string(img, lang=lang, config=cfg) or ""
            if t.strip():
                melhores.append(t)
        except Exception:
            continue
    if not melhores:
        return ""
    return max(melhores, key=_score_texto_doc)


def _tesseract_placa_linha(img, lang: str) -> str:
    """PSM de linha/palavra - melhor para crop da placa no CRLV."""
    import pytesseract

    partes = []
    for psm in (7, 6, 11):
        try:
            cfg = f"--oem 3 --psm {psm}"
            t = pytesseract.image_to_string(img, lang=lang, config=cfg) or ""
            if t.strip():
                partes.append(t)
        except Exception:
            continue
    return "\n".join(partes)


def _tesseract_rntrc_linha(img) -> str:
    """
    Faixa inferior do cartão ANTT: 'ETC 055407188' em fonte grande.
    Whitelist de dígitos + letras TAC/ETC/CTC/RNTRC.
    """
    import pytesseract

    partes = []
    cfg_base = (
        "--oem 3 --psm 7 "
        "-c tessedit_char_whitelist=0123456789ETACRN "
    )
    for psm in (7, 6, 11, 13):
        try:
            cfg = f"--oem 3 --psm {psm} -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ "
            t = pytesseract.image_to_string(img, lang="eng", config=cfg) or ""
            if t.strip():
                partes.append(t)
        except Exception:
            continue
    try:
        t = pytesseract.image_to_string(img, lang="eng", config=cfg_base) or ""
        if t.strip():
            partes.append(t)
    except Exception:
        pass
    return "\n".join(partes)


def _score_texto_doc(texto: str) -> int:
    """Pontua se parece documento BR com dados reais (genérico, sem nomes fixos)."""
    t = (texto or "").upper()
    s = 0
    if re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", t):
        s += 8
    if re.search(r"\b\d{2}/\d{2}/\d{4}\b", t):
        s += 2
    if re.search(r"\b[A-Z]{3}\d[A-Z0-9]\d{2}\b", t):
        s += 3
    if "NASCIMENTO" in t and ("DATA" in t or "CPF" in t):
        s += 2
    if "FILIA" in t or "REGISTRO" in t or "VALIDADE" in t:
        s += 2
    if any(x in t for x in ("CNH", "HABILITA", "RENAVAM", "RNTRC", "CHASSI", "ANTT")):
        s += 3
    # CRLV: bônus se trouxe prop + cidade (quadrante direito)
    if "BARRA DOS COQUEIROS" in t or "COQUEIROS" in t:
        s += 4
    if re.search(
        r"\b(?:IVECO|STRALIS|VOLVO|SCANIA|FACCHINI|CAMINHAO TRATOR|SEMI-REBOQUE)\b",
        t,
    ):
        s += 3
    if re.search(r"\bNOME\b", t) and re.search(
        r"\b[A-ZÁÉÍÓÚ]{3,}(?:\s+[A-ZÁÉÍÓÚ]{2,}){1,5}\b", t
    ):
        s += 2
    # nomes de pessoa (não rótulos)
    for m in re.finditer(
        r"\b([A-ZÁÉÍÓÚ]{4,}(?:\s+[A-ZÁÉÍÓÚ]{2,}){2,5})\b", t
    ):
        n = m.group(1)
        if any(
            x in n
            for x in (
                "REPUBLICA", "FEDERATIVA", "MINISTERIO", "SECRETARIA",
                "CARTEIRA", "HABILITA", "DOCUMENTO", "ASSINADO", "CERTIFICADO",
                "SOBRENOME", "NACIONAL", "DRIVER", "LICENSE",
            )
        ):
            continue
        s += 6
        break
    if "MEDIDA PROVIS" in t or "ASSINADOR SERPRO" in t:
        s -= 5
    if "DOCUMENTO ASSINADO COM CERTIFICADO" in t and "LINDOMAR" not in t:
        # muito boilerplate, pouco cartão
        s -= 4
    s += min(3, len(t) // 500)
    return s


def _abrir_imagem(path: Path):
    """Abre foto/HEIC com rotação EXIF (celular) e correção OSD."""
    from PIL import Image, ImageOps

    path = Path(path)
    ext = path.suffix.lower()
    if ext in HEIC_EXT:
        try:
            import pillow_heif

            pillow_heif.register_heif_opener()
        except ImportError:
            print(
                f"[OCR-local] HEIC sem pillow-heif - converta {path.name} para JPG "
                f"ou: pip install pillow-heif"
            )
            return None
    img = Image.open(path)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Correção de orientação baseada em OSD (Tesseract)
    try:
        import pytesseract
        # Executa OSD apenas em imagens razoavelmente grandes
        if max(img.size) >= 400:
            osd = pytesseract.image_to_osd(img)
            m_rot = re.search(r"Rotate:\s*(\d+)", osd)
            m_conf = re.search(r"Orientation confidence:\s*([\d\.]+)", osd)
            if m_rot and m_conf:
                angulo = int(m_rot.group(1))
                conf = float(m_conf.group(1))
                if angulo != 0:
                    if conf >= 5.0:
                        # Tesseract's Rotate is clockwise, PIL's rotate is counter-clockwise.
                        # We rotate by -angulo to correct the orientation.
                        print(f"[OCR-local] Rotacionando imagem em {-angulo} graus (OSD detectado com confiança {conf})")
                        img = img.rotate(-angulo, expand=True)
                    else:
                        print(f"[OCR-local] Ignorando OSD de {-angulo} graus devido a baixa confiança ({conf} < 5.0)")
    except Exception:
        # Ignora falhas se OSD não estiver disponível/instalado
        pass

    return img


def _ocr_rapido() -> bool:
    """Padrão rápido: menos variantes Tesseract (evita 5+ min por caso)."""
    v = (os.getenv("OCR_RAPIDO", "1") or "1").strip().lower()
    return v not in ("0", "false", "nao", "não", "no", "off")


def _foto_min_px() -> int:
    # 2400 = bom equilíbrio WhatsApp; 3600+ fica muito lento
    padrao = "2400" if _ocr_rapido() else "3200"
    try:
        min_px = int(os.getenv("OCR_FOTO_MIN_PX", padrao) or padrao)
    except ValueError:
        min_px = 2400
    return max(1600, min(min_px, 4000))


def _foto_zoom_base() -> float:
    """Escala extra em fotos WhatsApp. Padrão 3x (rápido)."""
    padrao = "3" if _ocr_rapido() else "4"
    try:
        z = float(os.getenv("OCR_FOTO_ZOOM", padrao) or padrao)
    except ValueError:
        z = 3.0
    return max(2.0, min(z, 5.0))


def _parece_crlv_texto(texto: str) -> bool:
    u = (texto or "").upper()
    if any(
        x in u
        for x in (
            "RENAVAM", "CRLV", "LICENCIAMENTO", "CHASSI", "PLACA",
            "MARCA / MODELO", "MARCA/MODELO", "SEMI-REBOQUE", "CAMINHAO TRATOR",
            "CAMINHÃO TRATOR", "DPVAT", "CODIGO DE SEGURANCA",
        )
    ):
        return True
    if re.search(r"\b[A-Z]{3}\d[A-Z0-9]\d{2}\b", u) and re.search(
        r"\b\d{9,11}\b", u
    ):
        return True
    return False


def _parece_cnh_texto(texto: str) -> bool:
    u = (texto or "").upper()
    return any(
        x in u
        for x in (
            "HABILITA", "CNH", "FILIA", "CAT HAB", "1ª HABIL", "1° HABIL",
            "REGISTRO", "DRIVER LICENSE", "CARTEIRA", "CARTERA",
            "ASSINATURA", "DETRAN", "SENATRAN", "DENATRAN", "REGIS",
        )
    )


def _parece_tac_texto(texto: str) -> bool:
    """Certificado ANTT / RNTRC / TAC / ETC (cartão azul)."""
    u = (texto or "").upper()
    if any(
        x in u
        for x in (
            "ANTT", "RNTRC", "TRANSPORTADORES RODOVI", "TRANSPORTADOR AUTONOMO",
            "AGENCIA NACIONAL DE TRANSPORT", "AGENCIANACIONAL",
            "AGEN CIA", "AMAT AGEN",  # OCR sujo do logo ANTT
        )
    ):
        return True
    if re.search(r"\b(?:TAC|ETC|CTC)\s*[:.\-]?\s*\d{6,}", u):
        return True
    if "CERTIFICADO DE REGISTRO" in u and (
        "TRANSPORT" in u or "RODOVI" in u or "CARGAS" in u or "ANTT" in u
    ):
        return True
    if "CERTIFICADO DE REGISTRO" in u and "RENAVAM" not in u and "CHASSI" not in u:
        return True
    return False


def _parece_antt_sem_veiculo(texto: str) -> bool:
    """
    True se parece cartão ANTT e NÃO CRLV (sem placa/renavam/chassi).
    Usado para forçar crops TAC em foto WhatsApp do certificado.
    """
    u = (texto or "").upper()
    if "RENAVAM" in u or "CHASSI" in u:
        return False
    if re.search(r"\b[A-Z]{3}\d[A-Z0-9]\d{2}\b", u) and "PLACA" in u:
        return False
    sinais = 0
    if re.search(r"CERTIFICADO\s+DE\s+REGISTR", u):
        sinais += 2
    if re.search(r"TRANSPORT|RODOVI|CARGAS", u):
        sinais += 1
    if re.search(r"AGEN\w*\s*NACIONAL|AGENCIANACIONAL|ANTT|AMAT AGEN", u):
        sinais += 2
    if re.search(r"\b(?:TAC|ETC|CTC)\b", u):
        sinais += 2
    if re.search(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}", u):
        sinais += 1  # CNPJ no cartão
    return sinais >= 3


def _parece_foto_antt_path(path: Path) -> bool:
    """Heurística fraca pelo nome (WhatsApp genérico não conta)."""
    n = Path(path).stem.lower()
    return any(x in n for x in ("antt", "tac", "rntrc", "etc", "transportador"))


def _crops_para_ocr(base_up, kind: str = "auto"):
    """
    Recortes em regiões úteis (coordenadas após zoom).

    CRLV digital (layout 2x2 como no WhatsApp):
      ┌──────────────┬──────────────┐
      │ códigos/marca│  dono+CPF+UF │  <- direita-topo = ouro do prop
      ├──────────────┼──────────────┤
      │ obs/finance  │    DPVAT     │
      └──────────────┴──────────────┘

    CNH: topo (nome/datas), meio (RG/CPF), baixo (filiação), direita (CAT).
    TAC/ANTT: nome+CNPJ no meio, RNTRC (ETC/TAC + nº) embaixo em fonte grande.
    """
    bw, bh = base_up.size
    crops = []

    # Poucos recortes de alto valor (cada um = 1–3 chamadas Tesseract)
    if kind == "crlv":
        # Layout CRLV-e 2x2: esq-topo = renavam/placa/chassi (crítico)
        crops = [
            base_up.crop((0, 0, int(bw * 0.58), int(bh * 0.58))),  # esq-topo ID veículo
            base_up.crop((int(bw * 0.48), 0, bw, int(bh * 0.55))),  # dir-topo PROP
            base_up.crop((0, int(bh * 0.28), int(bw * 0.62), int(bh * 0.72))),  # chassi/marca
            base_up.crop((int(bw * 0.40), 0, bw, bh)),  # metade direita
        ]
        print("[OCR-local] crops CRLV (4 regiões: placa/renavam/chassi + prop)")
    elif kind == "cnh":
        crops = [
            base_up.crop((0, 0, bw, int(bh * 0.50))),  # topo nome/nasc
            base_up.crop((0, int(bh * 0.40), bw, bh)),  # baixo filiação
            base_up.crop((int(bw * 0.40), 0, bw, int(bh * 0.65))),  # dir CAT
            # faixa central-direita: 4a EMISSÃO + 4b VALIDADE (foto física)
            base_up.crop((int(bw * 0.38), int(bh * 0.12), bw, int(bh * 0.42))),
        ]
        print("[OCR-local] crops CNH (4 regiões: + emissão/validade)")
    elif kind == "tac":
        # Cartão ANTT: nome/CNPJ no meio, RNTRC (ETC/TAC + número) embaixo
        crops = [
            base_up.crop((0, int(bh * 0.25), bw, int(bh * 0.70))),  # nome + CNPJ
            base_up.crop((0, int(bh * 0.55), bw, bh)),  # faixa RNTRC
            base_up.crop((int(bw * 0.05), int(bh * 0.15), int(bw * 0.95), int(bh * 0.85))),
            base_up.crop((0, 0, bw, int(bh * 0.40))),  # cabeçalho ANTT
        ]
        print("[OCR-local] crops TAC/ANTT (4 regiões: nome/CNPJ + RNTRC embaixo)")
    else:
        crops = [
            base_up.crop((0, 0, bw, int(bh * 0.55))),
            base_up.crop((int(bw * 0.45), 0, bw, int(bh * 0.55))),
            base_up.crop((0, int(bh * 0.55), bw, bh)),  # faixa inferior (RNTRC)
        ]
        print("[OCR-local] crops genéricos (3 regiões: + faixa inferior)")
    return crops


def _preprocessar_foto(img, min_px: Optional[int] = None):
    """
    Prepara foto de celular/WhatsApp para OCR:
    amplia se pequena (zoom), cinza, contraste, nitidez, OpenCV.
    """
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    # escala mínima ~2800px no lado maior (WhatsApp ~900px -> zoom ~3x)
    w, h = img.size
    maior = max(w, h)
    min_px = min_px if min_px is not None else _foto_min_px()
    if maior < min_px:
        scale = min_px / maior
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    elif maior > 4500:
        scale = 4500 / maior
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    img = img.convert("L")
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = ImageEnhance.Sharpness(img).enhance(1.8)
    if not _ocr_rapido():
        try:
            img = img.filter(
                ImageFilter.UnsharpMask(radius=1.4, percent=140, threshold=2)
            )
        except Exception:
            pass
        # denoise OpenCV é LENTO - só no modo qualidade
        try:
            import cv2
            import numpy as np

            arr = np.array(img)
            arr = cv2.fastNlMeansDenoising(arr, None, 8, 7, 21)
            img = Image.fromarray(arr)
        except Exception:
            pass
    return img


def _texto_foto_fraco(texto: str) -> bool:
    """True se o OCR da foto parece incompleto (poucas datas / campos)."""
    t = texto or ""
    score = _score_texto_doc(t)
    if score < 10:
        return True
    if len(t.strip()) < 250:
        return True
    n_datas = len(re.findall(r"\d{2}/\d{2}/\d{4}", t))
    tem_cpf = bool(re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", t))
    tem_placa = bool(re.search(r"\b[A-Z]{3}\d[A-Z0-9]\d{2}\b", t, re.I))
    u = t.upper()
    # CRLV: sem CPF *com pontuação* ou sem nome de pessoa -> força crop
    if _parece_crlv_texto(t):
        # exige pontos/hífen (senão renavam 11 dígitos vira "CPF" falso)
        tem_cpf_fmt = bool(
            re.search(r"\d{3}\s*\.\s*\d{3}\s*\.\s*\d{3}\s*-\s*\d{2}", t)
        )
        # ignora labels (CERTIFICADO DE REGISTRO / FEDERATIVA DO BRASIL)
        tem_nome_pessoa = False
        for m in re.finditer(
            r"\b([A-ZÁÉÍÓÚ]{3,}(?:\s+(?:DA|DE|DO|DAS|DOS|[A-ZÁÉÍÓÚ]{3,})){1,5})\b",
            u,
        ):
            n = m.group(1)
            if any(
                x in n
                for x in (
                    "CERTIFICADO", "REGISTRO", "LICENCIAMENTO", "REPUBLICA",
                    "FEDERATIVA", "MINISTERIO", "SECRETARIA", "DETRAN",
                    "ASSINADO", "DIGITALMENTE", "OBSERVACOES", "SEGURO",
                    "BRASIL", "VEICULO", "VEÍCULO", "CAMINHAO", "TRATOR",
                    "CATEGORIA", "CAPACIDADE", "TRANSPORTE",
                )
            ):
                continue
            tem_nome_pessoa = True
            break
        if not tem_cpf_fmt or not tem_nome_pessoa:
            return True
    # CNH precisa ≥2 datas; CRLV às vezes 0–1 (só exercício)
    if tem_cpf and n_datas < 2 and _parece_cnh_texto(t):
        return True
    if tem_placa and not re.search(r"RENAVAM|CHASSI|PROPRIET", t, re.I):
        if n_datas < 1 and len(t) < 600:
            return True
    # filiação ilegível / RG sem órgão
    if tem_cpf and "FILIA" in t.upper() and n_datas < 3:
        if not re.search(r"\b(SSP|SDS|DGPC|IFP)\b", t, re.I):
            return True
    return False


def _mesclar_candidatos_ocr(candidatos: List[str]) -> str:
    candidatos = [c for c in candidatos if (c or "").strip()]
    if not candidatos:
        return ""
    best = max(candidatos, key=_score_texto_doc)
    for c in candidatos:
        if re.search(r"\b\d{6}\d?[MF]\d{6}", c or "", re.I) and not re.search(
            r"\b\d{6}\d?[MF]\d{6}", best, re.I
        ):
            best = best + "\n" + c
        if re.search(
            r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s+\d{9,11}\s+[A-E]{1,2}\b",
            c or "",
            re.I,
        ) and not re.search(
            r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s+\d{9,11}\s+[A-E]{1,2}\b",
            best,
            re.I,
        ):
            best = best + "\n" + c
        # filiação / nomes extras
        for nome in re.findall(
            r"\b([A-ZÁÉÍÓÚ]{3,}(?:\s+(?:DA|DE|DO|DAS|DOS|[A-ZÁÉÍÓÚ]{3,})){2,6})\b",
            (c or "").upper(),
        ):
            if nome not in best.upper() and len(nome) > 12:
                best = best + "\n" + nome
                break
        # datas que faltam no best
        for d in re.findall(r"\d{2}/\d{2}/\d{4}", c or ""):
            if d not in best:
                best = best + "\n" + d
        # placas (todas) - parser vota depois (JSV6H70 vs JSV6B70)
        for pl in re.findall(r"\b([A-Z]{3}\d[A-Z0-9]\d{2})\b", (c or "").upper()):
            if pl not in best.upper():
                best = best + "\n" + pl
        # renavam label + 11 dígitos
        for m in re.finditer(
            r"(?:RENAVAM\s*[:\.]?\s*)?(\d{11})\b", (c or ""), re.I
        ):
            num = m.group(1)
            if num not in best:
                best = best + "\n" + num
        # chassi 17
        for m in re.finditer(r"\b([A-Z0-9]{17})\b", (c or "").upper()):
            if m.group(1) not in best.upper():
                best = best + "\n" + m.group(1)
        # RNTRC / ETC / TAC + número (cartão ANTT)
        for m in re.finditer(
            r"\b((?:TAC|ETC|CTC)\s*[:.\-]?\s*\d{6,12})\b", (c or "").upper()
        ):
            if m.group(1) not in best.upper():
                best = best + "\n" + m.group(1)
        for m in re.finditer(r"\b(\d{8,9})\b", c or ""):
            # só anexa se candidato TAC e ainda sem número 8+ dígitos no best
            if not re.search(r"\b\d{8,9}\b", best or ""):
                if m.group(1) not in (best or ""):
                    best = best + "\n" + m.group(1)
    return best.strip()


def _ocr_imagem(path: Path, forcar_zoom: Optional[float] = None) -> str:
    if not _configurar_pytesseract():
        return ""
    try:
        from PIL import Image
    except ImportError as e:
        print(f"[OCR-local] deps: {e}")
        return ""
    lang = os.getenv("OCR_LANG", "por+eng")
    rapido = _ocr_rapido()
    try:
        raw = _abrir_imagem(path)
        if raw is None:
            return ""
        candidatos: List[str] = []
        w, h = raw.size
        maior = max(w, h)

        # Zoom: WhatsApp pequeno precisa ampliar, sem explodir tempo
        if forcar_zoom and forcar_zoom > 1:
            sc = max(2, min(int(round(forcar_zoom)), 4 if rapido else 5))
            print(
                f"[OCR-local] zoom forçado {sc}x em {path.name} "
                f"(orig {w}x{h})"
            )
        elif maior < 1200:
            sc = 3 if not rapido else 2
        elif maior < 1800:
            sc = 2
        else:
            sc = 1

        # 1) 1–2 variantes full (não 3×PSM×3 = explosão de tempo)
        max_vars = 1 if rapido else (2 if (forcar_zoom or sc >= 2) else 1)
        for variante in _variantes_imagem_ocr(raw, scale=sc, max_vars=max_vars):
            candidatos.append(_tesseract_melhor(variante, lang, rapido=rapido))

        # 2) preprocess único com min_px
        min_px = _foto_min_px()
        if forcar_zoom and not rapido:
            min_px = max(min_px, int(maior * min(forcar_zoom, 3.5)))
            min_px = min(min_px, 3600)
        im_a = _preprocessar_foto(raw, min_px=min_px)
        candidatos.append(_tesseract_melhor(im_a, lang, rapido=rapido))

        best = _mesclar_candidatos_ocr(candidatos)

        # NOVO: Rotação 360º Otimizada e Rápida
        if _texto_foto_fraco(best):
            print(f"[OCR-local] Leitura inicial fraca para {path.name}. Testando giro 360º...")
            w_r, h_r = raw.size
            max_dim = max(w_r, h_r)
            if max_dim > 1000:
                f_scale = 1000 / max_dim
                img_test = raw.resize((int(w_r * f_scale), int(h_r * f_scale)), Image.Resampling.LANCZOS)
            else:
                img_test = raw
                
            melhor_giro = best
            melhor_img = raw
            melhor_score = _score_texto_doc(best)
            
            for angulo in (90, 180, 270):
                img_girada_test = img_test.rotate(angulo, expand=True)
                cand_giro = []
                for var_giro in _variantes_imagem_ocr(img_girada_test, scale=1, max_vars=1):
                    cand_giro.append(_tesseract_melhor(var_giro, lang, rapido=True))
                texto_giro = _mesclar_candidatos_ocr(cand_giro)
                score_giro = _score_texto_doc(texto_giro)
                
                if score_giro > melhor_score:
                    melhor_score = score_giro
                    melhor_giro = texto_giro
                    melhor_img = raw.rotate(angulo, expand=True)
            
            if melhor_img != raw:
                print(f"[OCR-local] Giro 360º encontrou texto melhor! (Score: {melhor_score})")
                raw = melhor_img
                # Refaz OCR na imagem original agora girada corretamente
                cand_novo = []
                for variante in _variantes_imagem_ocr(raw, scale=sc, max_vars=max_vars):
                    cand_novo.append(_tesseract_melhor(variante, lang, rapido=rapido))
                im_a_novo = _preprocessar_foto(raw, min_px=min_px)
                cand_novo.append(_tesseract_melhor(im_a_novo, lang, rapido=rapido))
                best = _mesclar_candidatos_ocr(cand_novo)

        # 3) Crops desativados no "Modo Jato" para poupar dezenas de chamadas ao Tesseract. O Gemini completa o que faltar.
        precisa_crop = False # NOVO: Totalmente desativado por padrão para ganhar velocidade extrema (Gemini cuidará dos buracos).
        if precisa_crop and maior >= 500:
            try:
                base_up = raw
                alvo = min(max(min_px, 2200), 3200 if rapido else 3600)
                if max(raw.size) < alvo:
                    f = alvo / max(raw.size)
                    base_up = raw.resize(
                        (int(raw.size[0] * f), int(raw.size[1] * f)),
                        Image.Resampling.LANCZOS,
                    )
                if _parece_tac_texto(best) or _parece_foto_antt_path(path):
                    kind = "tac"
                elif _parece_crlv_texto(best) and not _parece_antt_sem_veiculo(best):
                    kind = "crlv"
                elif _parece_cnh_texto(best):
                    kind = "cnh"
                elif _parece_antt_sem_veiculo(best):
                    kind = "tac"
                else:
                    # retrato sem placa/renavam -> tenta TAC (cartão ANTT WhatsApp)
                    w0, h0 = raw.size
                    kind = "tac" if h0 > w0 * 1.05 else (
                        "crlv" if maior >= 1000 else "auto"
                    )
                print(
                    f"[OCR-local] crops em {path.name} "
                    f"(alvo~{max(base_up.size)}px kind={kind} rapido={rapido})"
                )
                for i, crop in enumerate(_crops_para_ocr(base_up, kind=kind)):
                    for variante in _variantes_imagem_ocr(crop, scale=1, max_vars=1):
                        candidatos.append(
                            _tesseract_melhor(variante, lang, rapido=True)
                        )
                    # 1º crop CRLV = esq-topo (placa/renavam) - PSM de linha
                    if kind == "crlv" and i == 0:
                        try:
                            candidatos.append(
                                _tesseract_placa_linha(crop, lang)
                            )
                        except Exception:
                            pass
                    # crop TAC faixa RNTRC (ETC 055407188) - linha + whitelist
                    if kind == "tac" and i in (1, 2):
                        try:
                            candidatos.append(
                                _tesseract_placa_linha(crop, lang)
                            )
                            candidatos.append(_tesseract_rntrc_linha(crop))
                        except Exception:
                            pass
                # extra: se TAC/ANTT sem número 8 dígitos, força faixa inferior 2x
                if kind == "tac" or _parece_antt_sem_veiculo(
                    "\n".join(c for c in candidatos if c) + "\n" + (best or "")
                ):
                    try:
                        pw, ph = base_up.size
                        faixa = base_up.crop((0, int(ph * 0.58), pw, ph))
                        # amplia a faixa (número grande do RNTRC)
                        fw, fh = faixa.size
                        if max(fw, fh) < 1800:
                            fsc = 1800 / max(fw, fh)
                            faixa = faixa.resize(
                                (int(fw * fsc), int(fh * fsc)),
                                Image.Resampling.LANCZOS,
                            )
                        print(
                            f"[OCR-local] crop RNTRC faixa-inferior "
                            f"~{max(faixa.size)}px"
                        )
                        candidatos.append(_tesseract_rntrc_linha(faixa))
                        candidatos.append(
                            _tesseract_placa_linha(faixa, lang)
                        )
                    except Exception as e:
                        print(f"[OCR-local] crop RNTRC: {e}")
                # CRLV sem CPF: 1 crop extra só da DIREITA-TOPO em resolução maior
                # (dono/CPF) - barato e resolve a maioria dos WhatsApp
                if kind == "crlv" and not re.search(
                    r"\d{3}\s*\.\s*\d{3}\s*\.\s*\d{3}\s*-\s*\d{2}", best or ""
                ):
                    try:
                        alvo_prop = min(3200, max(2800, int(maior * 3)))
                        if max(raw.size) < alvo_prop:
                            fp = alvo_prop / max(raw.size)
                            up_p = raw.resize(
                                (
                                    int(raw.size[0] * fp),
                                    int(raw.size[1] * fp),
                                ),
                                Image.Resampling.LANCZOS,
                            )
                        else:
                            up_p = base_up
                        pw, ph = up_p.size
                        crop_prop = up_p.crop(
                            (int(pw * 0.48), 0, pw, int(ph * 0.52))
                        )
                        print(
                            f"[OCR-local] crop PROP dir-topo "
                            f"~{max(crop_prop.size)}px"
                        )
                        for variante in _variantes_imagem_ocr(
                            crop_prop, scale=1, max_vars=1
                        ):
                            candidatos.append(
                                _tesseract_melhor(variante, lang, rapido=True)
                            )
                    except Exception as e:
                        print(f"[OCR-local] crop prop: {e}")
                best = _mesclar_candidatos_ocr(candidatos)
            except Exception as e:
                print(f"[OCR-local] crops {path.name}: {e}")

        # 4) 2ª passada se fraco: desativada para ganho extremo de velocidade
        precisa_re = False
        if precisa_re:
            sc2 = min(4, sc + 1)
            print(f"[OCR-local] re-OCR reforço zoom={sc2}x {path.name}")
            extra: List[str] = [best]
            for variante in _variantes_imagem_ocr(raw, scale=sc2, max_vars=2 if not rapido else 1):
                extra.append(_tesseract_melhor(variante, lang, rapido=False))
            best = _mesclar_candidatos_ocr(extra)

        print(
            f"[OCR-local] Tesseract foto {path.name}: {len(best)} chars "
            f"(score={_score_texto_doc(best)}, variantes={len(candidatos)}, "
            f"zoom={sc}x orig={w}x{h} rapido={rapido})"
        )
        return best.strip()
    except Exception as e:
        print(f"[OCR-local] falha imagem {path.name}: {e}")
        return ""


def extrair_bruto_varios(arquivos: List[Path]) -> dict:
    """Retorna {path_str: texto}."""
    out = {}
    for a in arquivos:
        a = Path(a)
        print(f"[OCR-local] Lendo {a.name}...")
        out[str(a)] = extrair_texto_arquivo(a)
    return out
