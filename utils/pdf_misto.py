import os
import shutil
from pathlib import Path
from typing import List
import fitz

from ocr.tipos_documento import classificar_por_conteudo, TipoDocumento

def separar_pdf_misto(pdf_path: Path) -> int:
    """
    Abre um PDF que supostamente contém vários documentos misturados (ex: Ficha Cadastral).
    Analisa página por página e salva como PDFs individuais os que forem reconhecidos (CNH, CRLV, TAC).
    Move o arquivo original para uma pasta _originais.
    Retorna a quantidade de arquivos extraídos úteis.
    """
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        print(f"[PDF_MISTO] Erro ao abrir {pdf_path.name}: {e}")
        return 0

    if len(doc) <= 1:
        # Não precisa separar se só tem 1 página
        return 0

    pasta_origem = pdf_path.parent
    nome_base = pdf_path.stem
    uteis_extraidos = 0

    for i in range(len(doc)):
        page = doc.load_page(i)
        texto = page.get_text("text")
        
        # O OCR do PyMuPDF nativo pode falhar se for imagem pura, 
        # mas "Fichas" geradas por sistema costumam ter texto selecionável (como vimos no do HEBER).
        tipo = classificar_por_conteudo(texto)
        
        novo_nome = ""
        if tipo and tipo not in (TipoDocumento.IGNORAR, TipoDocumento.OUTRO):
            novo_nome = f"{nome_base}_{tipo.value}_pag{i+1}.pdf"
        elif len(page.get_images()) > 0 and len(texto.strip()) < 500:
            # Página com imagem e pouco/nenhum texto. 
            # Em vez de extrair "às cegas", fazemos um OCR rápido para confirmar.
            try:
                import pytesseract
                from PIL import Image
                import io
                from ocr.local_ocr import _configurar_pytesseract
                
                _configurar_pytesseract()
                
                # Renderiza a página (zoom 2x para legibilidade)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                
                # Usando lang="eng" porque "por" não está instalado no Tesseract dessa máquina.
                # Para classificação de palavras-chave, "eng" é suficiente.
                texto_ocr = pytesseract.image_to_string(img, lang="eng", config="--psm 3") or ""
                tipo_ocr = classificar_por_conteudo(texto_ocr)
                
                if tipo_ocr and tipo_ocr not in (TipoDocumento.IGNORAR, TipoDocumento.OUTRO):
                    novo_nome = f"{nome_base}_{tipo_ocr.value}_pag{i+1}.pdf"
                    print(f"[PDF_MISTO] OCR Rápido confirmou {tipo_ocr.value} na página {i+1}")
            except Exception as e:
                print(f"[PDF_MISTO] Erro no OCR rápido da página {i+1}: {e}")
            
        if novo_nome:
            novo_caminho = pasta_origem / novo_nome
            novo_doc = fitz.open()
            novo_doc.insert_pdf(doc, from_page=i, to_page=i)
            novo_doc.save(str(novo_caminho))
            novo_doc.close()
            uteis_extraidos += 1
            print(f"[PDF_MISTO] Extraído: {novo_nome}")

    doc.close()

    # Move o arquivo original para uma subpasta para que não seja processado no pipeline normal
    if uteis_extraidos > 0:
        pasta_originais = pasta_origem / "_originais"
        pasta_originais.mkdir(exist_ok=True)
        destino_original = pasta_originais / pdf_path.name
        
        try:
            shutil.move(str(pdf_path), str(destino_original))
            print(f"[PDF_MISTO] PDF original movido para {destino_original}")
        except Exception as e:
            print(f"[PDF_MISTO] Erro ao mover PDF original: {e}")

    return uteis_extraidos


def verificar_e_separar_pdfs_mistos(diretorio: Path) -> None:
    """
    Varre o diretório e suas subpastas (ignorando pastas ocultas)
    atrás de PDFs que parecem pacotes (Ficha Cadastral) ou que sejam grandes.
    """
    if not diretorio.exists():
        return

    for pdf_path in diretorio.rglob("*.pdf"):
        # Pula as pastas ocultas (como _originais)
        if any(p.startswith("_") or p.startswith(".") for p in pdf_path.parts):
            continue
            
        nome_lower = pdf_path.stem.lower()
        # Regra heurística para tentar separar:
        # Se tem a palavra FICHA, CADASTRAL, PACOTE, DOCUMENTOS, ou se tem mais de 3 páginas
        
        deve_verificar = False
        if any(x in nome_lower for x in ("ficha", "cadastral", "pacote", "documentos")):
            deve_verificar = True
        else:
            # Verifica o número de páginas só se não bateu o nome, pra não onerar tanto
            try:
                doc = fitz.open(str(pdf_path))
                if len(doc) >= 4:
                    deve_verificar = True
                doc.close()
            except:
                pass
                
        if deve_verificar:
            print(f"[PDF_MISTO] Analisando possível PDF misto: {pdf_path.name}")
            separar_pdf_misto(pdf_path)
