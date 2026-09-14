"""
Extração de dados de documentos via Google Gemini (Vision).

Lê: CNH, CRLV, TAC/ANTT, comprovante de endereço (imagem ou PDF).
Requer no .env: GEMINI_API_KEY=...
Opcional: GEMINI_API_KEY_BACKUP=... / GEMINI_API_KEY_BACKUP2=... (usa se a principal esgotar)
          GEMINI_MODEL_FALLBACKS=gemini-3.6-flash,gemini-3.5-flash (fallback de modelos)
Fallback:  OPENAI_API_KEY=sk-proj-... / GROQ_API_KEY=gsk_...

Chave grátis Google: https://aistudio.google.com/apikey
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ocr.tipos_documento import TipoDocumento, classificar_arquivo

import logging
import warnings
warnings.filterwarnings("ignore", message=".*automatic function calling.*")
logging.getLogger("google.genai.models").setLevel(logging.ERROR)
try:
    from google.genai.models import Models
    Models._logged_afc_warning = True
except Exception:
    pass

# Modelo principal (lido do .env)
MODELO_PADRAO = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Lista de modelos fallback (separados por vírgula no .env)
def _modelos_fallback() -> List[str]:
    raw = os.getenv("GEMINI_MODEL_FALLBACKS", "gemini-3.7-flash,gemini-3.8-flash,gemini-flash-latest")
    return [m.strip() for m in raw.split(",") if m.strip()]

# Chave ativa e controle de falhas
_chave_ativa: Optional[str] = None
_chaves_esgotadas: set = set()          # chaves com quota permanentemente esgotada
_modelos_sobrecarregados: set = set()   # modelos com erro 503 temporário (reseta entre docs)


PROMPT_BASE = """
Você é um extrator de dados de documentos brasileiros de transporte/logística.
Analise a(s) imagem(ns)/documento e devolva APENAS um JSON válido (sem markdown).
Se um campo não existir ou estiver ilegível, use string vazia "".
Datas no formato DD/MM/AAAA. CPF/CNPJ só dígitos. Placa sem hífen, maiúscula.
NÃO invente dados. Se não tiver certeza, deixe "".

NOMES (pessoa ou empresa):
- Só nomes REAIS legíveis no documento (ex: JEREMIAS SILVA, TRANSPORTES OLIVEIRA LTDA).
- PROIBIDO devolver lixo OCR ou sílabas sem sentido: AXR, CPEY, WIT AES, AES EMT,
  UEREMIAS (se for inventado), ALEX genérico, letras soltas, abreviações estranhas.
- Se o nome estiver borrado/ilegível, use "" - NUNCA complete com chute.
- Nome de pai/mãe: só se estiverem escritos com clareza; senão "".
- ATENÇÃO A REFLEXOS: O OCR muitas vezes confunde 'O' com 'A' e 'S' com '5' em fotos com baixa resolução ou reflexo. Analise cuidadosamente a imagem. Para nomes próprios, guie-se por nomes reais brasileiros (ex: nomes terminados em ALINO geralmente são com A e não OLINO), mas mantenha-se estritamente fiel à imagem.
"""

PROMPT_CNH = PROMPT_BASE + """
Documento: CNH (Carteira Nacional de Habilitação).
JSON:
{
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
  "nacionalidade": "",
  "naturalidade": "",
  "uf_naturalidade": ""
}
sexo: Masculino ou Feminino se der para inferir.
nome: Nome COMPLETO do Motorista (campo NOME no TOPO da CNH). CUIDADO: NUNCA coloque o nome da MÃE ou do PAI (que ficam na parte inferior em FILIAÇÃO) no campo 'nome'. Se o motorista for homem (sexo Masculino), o 'nome' DEVE ser o nome masculino do motorista (e nunca o nome feminino da mãe).
nome_pai: Nome completo do Pai (1ª linha da filiação, se houver).
nome_mae: Nome completo da Mãe (2ª linha da filiação, ou única linha se só houver mãe).
rg: campo 4c DOC. IDENTIDADE (número antes de SSP/SDS/DGPC + UF). Só dígitos.
data_emissao_cnh: campo 4a DATA EMISSÃO (NÃO confundir com 1ª habilitação nem validade).
data_primeira_habilitacao: campo 1ª HABILITAÇÃO (canto superior direito, data antiga).
validade_cnh: campo 4b VALIDADE (data futura).
local_emissao_cnh: LOCAL no rodapé (ex: JEQUIE/BA) se legível.
"""

PROMPT_CRLV = PROMPT_BASE + """
Documento: CRLV / CRV (veículo).
JSON:
{
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
  "eh_semi_reboque": false,
  "eh_caminhao_trator": false,
  "eh_caminhao": false
}
marca_modelo_versao: texto completo do campo "MARCA / MODELO / VERSÃO" do CRLV
(ex: "M BENZ LS 1935" ou "VW GOL 1.0"). Esse texto será usado em 3 campos no sistema.
tipo_veiculo_doc: texto do documento (ex: SEMI-REBOQUE, CAMINHAO TRATOR).
eh_semi_reboque true se carreta/semi-reboque.
eh_caminhao_trator true se cavalo mecânico / caminhão trator.
proprietario_nome: nome da pessoa ou razão social do PROPRIETÁRIO no CRLV
(campo NOME perto do CPF/CNPJ). Aceita iniciais (ex: L.S.OLIVEIRA).
NÃO use marca/modelo (VW/, SCANIA, DIESEL, GASOLINA) no lugar do nome.
NÃO use frases de marketing da CDT/DPVAT ("serviços de trânsito", "sem nenhum custo",
"carteira digital", "você sabia").
Se ilegível, "".
placa: exata do documento. Se for formato antigo (3 letras + 4 dígitos, ex PJO9971),
mantenha os 4 dígitos - NÃO transforme em Mercosul.
"""

PROMPT_TAC = PROMPT_BASE + """
Documento: TAC / ETC / CTC / ANTT / RNTRC (cartão ou certificado de transportador).
JSON:
{
  "nome": "",
  "cpf": "",
  "cnpj": "",
  "rntrc": "",
  "categoria": "",
  "cadastrado_desde": ""
}
rntrc: número grande do RNTRC (geralmente 8–9 dígitos). Pode aparecer como
  "ETC 055407188", "TAC 049285533", "CTC ..." ou "RNTRC: ...". Extraia SÓ os dígitos.
categoria: TAC, ETC ou CTC conforme o cartão (não invente).
nome: razão social ou nome no cartão (ex: L. S. OLIVEIRA). NÃO use textos de
  marketing (serviços de trânsito, carteira digital, etc.).
cnpj/cpf: documento do transportador no cartão.
"""

PROMPT_COMPROVANTE = PROMPT_BASE + """
Documento: comprovante de endereço (conta de luz, água, etc.).
JSON:
{
  "nome_titular": "",
  "endereco": "",
  "numero": "",
  "complemento": "",
  "bairro": "",
  "cidade": "",
  "uf": "",
  "cep": ""
}
"""

PROMPT_GENERICO = PROMPT_BASE + """
Identifique o tipo de documento e extraia o máximo possível.
JSON:
{
  "tipo_detectado": "cnh|crlv|tac|comprovante|outro",
  "nome": "",
  "cpf": "",
  "cnpj": "",
  "data_nascimento": "",
  "nome_pai": "",
  "nome_mae": "",
  "rg": "",
  "cnh": "",
  "categoria_cnh": "",
  "validade_cnh": "",
  "data_primeira_habilitacao": "",
  "data_emissao_cnh": "",
  "placa": "",
  "renavam": "",
  "chassi": "",
  "rntrc": "",
  "endereco": "",
  "cidade": "",
  "uf": "",
  "cep": "",
  "texto_relevante": ""
}
"""


def _chaves_configuradas() -> List[str]:
    """Lista de chaves: principal -> backup -> backup2 -> GOOGLE_API_KEY."""
    candidatas = [
        os.getenv("GEMINI_API_KEY", ""),
        os.getenv("GEMINI_API_KEY_BACKUP", ""),
        os.getenv("GEMINI_API_KEY_BACKUP2", ""),
        os.getenv("GOOGLE_API_KEY", ""),
    ]
    vistas: set[str] = set()
    saida: List[str] = []
    for k in candidatas:
        k = (k or "").strip()
        if not k or k.startswith("sua_") or k in vistas:
            continue
        vistas.add(k)
        saida.append(k)
    return saida


def gemini_disponivel() -> bool:
    return bool(_chaves_configuradas())


def _eh_erro_cota(exc: BaseException) -> bool:
    """Cota/rate-limit - vale trocar de chave. Invalid key também. Inclui 503/500 de instabilidade."""
    msg = str(exc).lower()
    return any(
        x in msg
        for x in (
            "429",
            "503",
            "504",
            "500",
            "unavailable",
            "deadline",
            "timed out",
            "timeout",
            "resource exhausted",
            "quota",
            "rate limit",
            "rate-limit",
            "exceeded your current quota",
            "api key not valid",
            "invalid api key",
            "api_key_invalid",
        )
    )


def _obter_chave() -> str:
    global _chave_ativa
    chaves = _chaves_configuradas()
    if not chaves:
        raise RuntimeError(
            "Nenhuma chave Gemini no .env (GEMINI_API_KEY / GEMINI_API_KEY_BACKUP)"
        )
    if _chave_ativa and _chave_ativa not in _chaves_esgotadas:
        return _chave_ativa
    for k in chaves:
        if k not in _chaves_esgotadas:
            _chave_ativa = k
            return k
    # todas marcadas - tenta a primeira de novo
    _chave_ativa = chaves[0]
    return _chave_ativa


def _rotular_chave(key: str) -> str:
    chaves = _chaves_configuradas()
    if not chaves:
        return "?"
    if key == chaves[0]:
        return "principal"
    if len(chaves) > 1 and key == chaves[1]:
        return "backup"
    return f"chave#{chaves.index(key)+1}" if key in chaves else "outra"


def _trocar_para_backup(chave_ruim: str, motivo: str) -> bool:
    """Marca chave atual como esgotada e tenta a próxima. True se há outra."""
    global _chave_ativa
    _chaves_esgotadas.add(chave_ruim)
    print(
        f"[Gemini] Chave {_rotular_chave(chave_ruim)} falhou ({motivo[:80]}). "
        f"Tentando backup..."
    )
    for k in _chaves_configuradas():
        if k not in _chaves_esgotadas:
            _chave_ativa = k
            print(f"[Gemini] Usando chave {_rotular_chave(k)}.")
            return True
    print("[Gemini] Todas as chaves esgotaram ou falharam.")
    return False


def _get_model(api_key: Optional[str] = None):
    from google import genai

    key = api_key or _obter_chave()
    client = genai.Client(api_key=key)
    return client, key


def _arquivo_para_partes(path: Path) -> List[Any]:
    """
    Converte imagem/PDF em partes enviáveis ao Gemini.

    PDF: envia bytes inline (mime application/pdf) - não usa Files API
    (upload_file falha com várias chaves AQ.*).
    Fallback: páginas como PNG via PyMuPDF (sem Poppler).
    """
    from PIL import Image

    suf = path.suffix.lower()

    # Limite de páginas por tipo de documento:
    # CRLV: 3 (pode ter dados do proprietário na pág 3)
    # Outros: 2
    max_pags = 3 if path.name.lower().endswith((".pdf",)) else 2
    # Detecta CRLV pelo nome do arquivo para usar 3 páginas
    nome_lower = path.stem.lower()
    if any(x in nome_lower for x in ("crlv", "certificado", "licenciamento")):
        max_pags = 3

    if suf == ".pdf":
        # 1) PyMuPDF: se tiver páginas renderizáveis -> PNG (evita PDF vazio/protegido)
        try:
            import fitz  # pymupdf

            doc = fitz.open(path)
            if doc.page_count > 0:
                partes_img = []
                for i, page in enumerate(doc):
                    if i >= max_pags:
                        break
                    # Upload Jato: zoom 2x e formato JPEG para não travar o envio na API do Gemini (reduz o peso da rede)
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    if pix.width > 0 and pix.height > 0:
                        tmp = Path(tempfile.gettempdir()) / f"gw_gemini_{path.stem}_{i}.jpg"
                        pix.save(str(tmp))
                        partes_img.append(
                            {
                                "mime_type": "image/jpeg",
                                "data": tmp.read_bytes(),
                            }
                        )
                doc.close()
                if partes_img:
                    return partes_img
            else:
                doc.close()
        except Exception as e:
            print(f"[Gemini] PDF->imagem (pymupdf) falhou ({path.name}): {e}")

        # 2) PDF inline (quando o arquivo é PDF “de verdade”)
        try:
            data = path.read_bytes()
            if len(data) > 100:
                return [{"mime_type": "application/pdf", "data": data}]
        except Exception as e:
            print(f"[Gemini] Leitura PDF falhou ({path.name}): {e}")

        # 3) pdf2image + Poppler
        try:
            from pdf2image import convert_from_path

            pages = convert_from_path(str(path), first_page=1, last_page=2, dpi=150)
            out = []
            for i, img in enumerate(pages):
                tmp = Path(tempfile.gettempdir()) / f"gw_gemini_pop_{path.stem}_{i}.png"
                img.save(tmp, "PNG")
                out.append({"mime_type": "image/png", "data": tmp.read_bytes()})
            if out:
                return out
        except Exception as e:
            print(f"[Gemini] PDF->imagem (poppler) falhou ({path.name}): {e}")
            raise RuntimeError(f"Não foi possível ler o PDF: {path.name}") from e

    # Imagens
    if suf in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        try:
            from PIL import Image, ImageEnhance
            import io
            
            img = Image.open(path)
            # Filtros de realce (nitidez e contraste) para melhorar OCR no Gemini
            img = ImageEnhance.Sharpness(img).enhance(1.5)
            img = ImageEnhance.Contrast(img).enhance(1.2)
            
            # Remove transparência caso exista (Gemini lida melhor com JPEG)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            data = buf.getvalue()
            mime = "image/jpeg"
            return [{"mime_type": mime, "data": data}]
        except Exception as e:
            print(f"[Gemini] Falha ao aplicar filtro de realce na imagem {path.name}: {e}. Enviando original.")
            data = path.read_bytes()
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".bmp": "image/bmp",
                ".tif": "image/tiff",
                ".tiff": "image/tiff",
            }.get(suf, "image/jpeg")
            return [{"mime_type": mime, "data": data}]

    # Outros: tenta como bytes genéricos
    return [{"mime_type": "application/octet-stream", "data": path.read_bytes()}]


def _prompt_para_tipo(tipo: TipoDocumento) -> str:
    return {
        TipoDocumento.CNH: PROMPT_CNH,
        TipoDocumento.CRLV: PROMPT_CRLV,
        TipoDocumento.TAC: PROMPT_TAC,
        TipoDocumento.COMPROVANTE: PROMPT_COMPROVANTE,
    }.get(tipo, PROMPT_GENERICO)


def _schema_para_tipo(tipo: TipoDocumento) -> Optional[Dict[str, Any]]:
    """
    Retorna o JSON Schema dos campos esperados por tipo de documento.
    Garante que o Gemini retorne exatamente esses campos (sem inventar extras).
    """
    str_field: Dict[str, Any] = {"type": "string"}
    bool_field: Dict[str, Any] = {"type": "boolean"}

    if tipo == TipoDocumento.CNH:
        return {
            "type": "object",
            "properties": {
                "nome":                     str_field,
                "cpf":                      str_field,
                "data_nascimento":          str_field,
                "naturalidade":             str_field,
                "nome_mae":                 str_field,
                "nome_pai":                 str_field,
                "rg":                       str_field,
                "cnh":                      str_field,
                "categoria_cnh":            str_field,
                "validade_cnh":             str_field,
                "data_primeira_habilitacao": str_field,
                "data_emissao_cnh":         str_field,
                "local_emissao_cnh":        str_field,
                "sexo":                     str_field,
                "orgao_emissor":            str_field,
            },
        }
    if tipo == TipoDocumento.CRLV:
        return {
            "type": "object",
            "properties": {
                "placa":                    str_field,
                "renavam":                  str_field,
                "chassi":                   str_field,
                "marca":                    str_field,
                "modelo":                   str_field,
                "versao":                   str_field,
                "marca_modelo_versao":      str_field,
                "ano_fab":                  str_field,
                "ano_mod":                  str_field,
                "cor":                      str_field,
                "tipo_veiculo_doc":         str_field,
                "especie":                  str_field,
                "cidade":                   str_field,
                "uf":                       str_field,
                "cap_carga":                str_field,
                "tara":                     str_field,
                "proprietario_nome":        str_field,
                "proprietario_cpf_cnpj":    str_field,
                "eh_semi_reboque":          bool_field,
                "eh_caminhao_trator":       bool_field,
                "eh_caminhao":              bool_field,
            },
        }
    if tipo == TipoDocumento.TAC:
        return {
            "type": "object",
            "properties": {
                "rntrc":                    str_field,
                "nome_empresa":             str_field,
                "cnpj_empresa":             str_field,
                "nome_proprietario":        str_field,
                "cpf_cnpj_proprietario":    str_field,
                "validade_rntrc":           str_field,
                "tipo_transportador":       str_field,
            },
        }
    if tipo == TipoDocumento.COMPROVANTE:
        return {
            "type": "object",
            "properties": {
                "nome":         str_field,
                "cpf":          str_field,
                "cep":          str_field,
                "logradouro":   str_field,
                "numero":       str_field,
                "complemento":  str_field,
                "bairro":       str_field,
                "cidade":       str_field,
                "uf":           str_field,
            },
        }
    # OUTRO/genérico — sem schema fixo (pode ter qualquer campo)
    return None


def _parse_json(texto: str) -> Dict[str, Any]:
    if not texto:
        return {}
    texto = texto.strip()
    # remove ```json ... ```
    if "```" in texto:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", texto)
        if m:
            texto = m.group(1).strip()
    # pega primeiro { ... }
    ini, fim = texto.find("{"), texto.rfind("}")
    if ini >= 0 and fim > ini:
        texto = texto[ini : fim + 1]
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        print(f"[Gemini] JSON inválido: {texto[:300]}...")
        return {}


def _cache_path(path: Path) -> Path:
    import hashlib
    from utils.paths import OUTPUT_DIR

    pasta = OUTPUT_DIR / "cache_gemini"
    pasta.mkdir(parents=True, exist_ok=True)
    st = path.stat()
    key = f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}|{MODELO_PADRAO}"
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^\w.\-]+", "_", path.name)[:40]
    return pasta / f"{safe}_{h}.json"


def _ler_cache(path: Path) -> Optional[Dict[str, Any]]:
    # Cache desativado a pedido do usuário
    return None


def _gravar_cache(path: Path, dados: Dict[str, Any]) -> None:
    # Cache desativado a pedido do usuário
    pass


def extrair_arquivo(path: Path, tipo: Optional[TipoDocumento] = None) -> Dict[str, Any]:
    """Lê um arquivo com Gemini e devolve dict de campos.
    Usa cache em output/cache_gemini/ (evita gastar cota em reteste).
    """
    path = Path(path)
    if not path.exists():
        print(f"[Gemini] Arquivo não existe: {path}")
        return {}

    tipo = tipo or classificar_arquivo(path)

    cached = _ler_cache(path)
    if cached:
        if _cache_incompleto_para_tipo(cached, tipo):
            print(
                f"[Gemini] CACHE incompleto {path.name} (tipo={tipo.value}) "
                f"- re-lendo com prompt correto"
            )
        else:
            print(f"[Gemini] CACHE {path.name} como {tipo.value}: "
                  f"{list(k for k in cached if not k.startswith('_'))}")
            cached["_tipo"] = tipo.value
            return cached

    print(f"[Gemini] Lendo {path.name} como {tipo.value}...")

    # Monta lista completa de modelos para tentar: [principal, fallback1, fallback2]
    modelo_principal = MODELO_PADRAO
    todos_modelos = [modelo_principal] + [
        m for m in _modelos_fallback() if m != modelo_principal
    ]

    # Reseta modelos sobrecarregados a cada novo documento
    global _modelos_sobrecarregados
    _modelos_sobrecarregados = set()

    ultimo_erro: Optional[BaseException] = None
    from google.genai import types
    import concurrent.futures

    partes_raw = _arquivo_para_partes(path)
    partes = []
    for p in partes_raw:
        if isinstance(p, dict) and "data" in p and "mime_type" in p:
            partes.append(types.Part.from_bytes(data=p["data"], mime_type=p["mime_type"]))
        else:
            partes.append(p)

    prompt = _prompt_para_tipo(tipo)
    schema = _schema_para_tipo(tipo)

    # Loop: para cada modelo disponível, tenta com cada chave disponível
    for modelo in todos_modelos:
        if modelo in _modelos_sobrecarregados:
            continue

        # Reseta chaves para tentar todas com o novo modelo
        chaves_para_modelo = [
            c for c in _chaves_configuradas() if c not in _chaves_esgotadas
        ]
        if not chaves_para_modelo:
            print(f"[Gemini] Sem chaves disponíveis para {modelo}")
            continue

        for chave in chaves_para_modelo:
            try:
                client, _ = _get_model(chave)

                cfg_kwargs: Dict[str, Any] = {
                    "response_mime_type": "application/json",
                    "http_options": types.HttpOptions(timeout=35000),
                }

                _client_ref = client
                _modelo_ref = modelo

                def _chamar():
                    return _client_ref.models.generate_content(
                        model=_modelo_ref,
                        contents=[prompt, *partes],
                        config=types.GenerateContentConfig(**cfg_kwargs),
                    )

                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                fut = executor.submit(_chamar)
                try:
                    resp = fut.result(timeout=40)
                except concurrent.futures.TimeoutError:
                    print(
                        f"[Gemini] Timeout (40s) em {path.name} chave={_rotular_chave(chave)}. "
                        f"Tentando próxima opção..."
                    )
                    ultimo_erro = TimeoutError("timeout 40s")
                    executor.shutdown(wait=False, cancel_futures=True)
                    continue
                else:
                    executor.shutdown(wait=False)

                bruto = getattr(resp, "text", None) or ""
                dados = _parse_json(bruto)
                dados["_arquivo"] = str(path)
                dados["_tipo"] = tipo.value
                dados["_chave"] = _rotular_chave(chave)
                dados["_modelo"] = modelo
                print(
                    f"[Gemini] OK {path.name} (modelo={modelo}, chave={_rotular_chave(chave)}): "
                    f"{list(k for k in dados if not k.startswith('_'))}"
                )
                _gravar_cache(path, dados)
                return dados

            except Exception as e:
                ultimo_erro = e
                msg = str(e).lower()

                # Erro de quota/chave inválida → marca chave como permanentemente esgotada
                if _eh_erro_cota(e):
                    # 503/504/unavailable/deadline → chave/modelo temporariamente lento, tenta próxima chave
                    if any(x in msg for x in ("503", "504", "unavailable", "deadline", "timed out", "500")):
                        print(
                            f"[Gemini] Chave {_rotular_chave(chave)} no modelo {modelo} instável (503/504). "
                            f"Tentando próxima chave..."
                        )
                        continue
                    else:
                        # Quota esgotada para esta chave → marca permanentemente
                        _trocar_para_backup(chave, str(e))
                        continue
                else:
                    print(f"[Gemini] Erro em {path.name} modelo={modelo}: {e}")
                    continue

    print(f"[Gemini] Falhou em todos os modelos/chaves: {path.name} -> {ultimo_erro}")

    # --- Fallback 1: OpenAI GPT-4o-mini (visão excelente) ---
    resultado_oai = _tentar_openai(path, tipo)
    if resultado_oai is not None:
        return resultado_oai

    # --- Fallback 2: Groq (gratuito) ---
    resultado_groq = _tentar_groq(path, tipo)
    if resultado_groq is not None:
        return resultado_groq

    return {
        "_arquivo": str(path),
        "_tipo": tipo.value,
        "_erro": str(ultimo_erro) if ultimo_erro else "sem chave",
    }


def _tentar_openai(path: Path, tipo: "TipoDocumento") -> Optional[Dict[str, Any]]:
    """
    Fallback via OpenAI (GPT-4o-mini) quando todas as chaves Google esgotaram.
    Usa OPENAI_API_KEY do .env. Retorna None se não configurado.
    GPT-4o-mini tem visão excelente para documentos brasileiros.
    """
    import base64

    oai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not oai_key or oai_key.startswith("sua_"):
        return None

    oai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    print(f"[OpenAI] Tentando {path.name} com {oai_model}...")

    try:
        import httpx

        partes_raw = _arquivo_para_partes(path)
        if not partes_raw:
            print(f"[OpenAI] Sem partes para {path.name}")
            return None

        prompt_str = _prompt_para_tipo(tipo)
        content: list = [{"type": "text", "text": prompt_str}]

        for p in partes_raw:
            if isinstance(p, dict) and "data" in p and "mime_type" in p:
                b64 = base64.b64encode(p["data"]).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{p['mime_type']};base64,{b64}",
                        "detail": "high",
                    },
                })

        payload = {
            "model": oai_model,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 2000,
        }

        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {oai_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        bruto = resp.json()["choices"][0]["message"]["content"]
        dados = _parse_json(bruto)
        dados["_arquivo"] = str(path)
        dados["_tipo"] = tipo.value
        dados["_chave"] = "openai"
        dados["_fonte"] = "openai"
        print(f"[OpenAI] OK {path.name}: {list(k for k in dados if not k.startswith('_'))}")
        _gravar_cache(path, dados)
        return dados

    except Exception as e:
        print(f"[OpenAI] Erro em {path.name}: {e}")
        return None


def _tentar_groq(path: Path, tipo: "TipoDocumento") -> Optional[Dict[str, Any]]:
    """
    Fallback via Groq (Llama 4 Vision) quando todas as chaves Google esgotaram.
    Usa GROQ_API_KEY do .env. Retorna None se não configurado.
    API Groq é compatível com OpenAI e tem plano gratuito generoso.
    """
    import base64

    gr_key = os.getenv("GROQ_API_KEY", "").strip()
    if not gr_key or gr_key.startswith("sua_"):
        return None

    gr_model = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    print(f"[Groq] Tentando {path.name} com {gr_model}...")

    try:
        import httpx

        partes_raw = _arquivo_para_partes(path)
        if not partes_raw:
            print(f"[Groq] Sem partes para {path.name}")
            return None

        prompt_str = _prompt_para_tipo(tipo)
        content: list = [{"type": "text", "text": prompt_str}]

        for p in partes_raw:
            if isinstance(p, dict) and "data" in p and "mime_type" in p:
                b64 = base64.b64encode(p["data"]).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{p['mime_type']};base64,{b64}"
                    },
                })

        payload = {
            "model": gr_model,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {gr_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        bruto = resp.json()["choices"][0]["message"]["content"]
        dados = _parse_json(bruto)
        dados["_arquivo"] = str(path)
        dados["_tipo"] = tipo.value
        dados["_chave"] = "groq"
        dados["_fonte"] = "groq"
        print(f"[Groq] OK {path.name}: {list(k for k in dados if not k.startswith('_'))}")
        _gravar_cache(path, dados)
        return dados

    except Exception as e:
        print(f"[Groq] Erro em {path.name}: {e}")
        return None


def extrair_varios(
    arquivos: List[Path],
    tipos_por_nome: Optional[Dict[str, str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extrai todos os arquivos e agrupa por tipo de documento.

    tipos_por_nome: opcional {nome_arquivo: "cnh"|"crlv"|...} vindo do OCR local.
    Evita PROMPT_GENERICO em fotos WhatsApp já classificadas pelo Tesseract.
    """
    resultado: Dict[str, List[Dict[str, Any]]] = {
        t.value: [] for t in TipoDocumento
    }
    if not gemini_disponivel():
        print("[Gemini] GEMINI_API_KEY ausente - pulando leitura por IA.")
        return resultado

    from ocr.tipos_documento import documento_irrelevante

    tipos_por_nome = tipos_por_nome or {}

    for arq in arquivos:
        arq = Path(arq)
        # não gasta cota com omnilink/rastreador
        if documento_irrelevante(arq):
            print(f"[Gemini] IGNORADO (não é doc de carro): {arq.name}")
            continue
        tipo = classificar_arquivo(arq)
        # se nome genérico (WhatsApp) -> usa tipo do OCR local
        hint = (tipos_por_nome.get(arq.name) or "").strip().lower()
        if hint and hint not in ("outro", "ignorar", ""):
            try:
                tipo_hint = TipoDocumento(hint)
                if tipo in (TipoDocumento.OUTRO,) or tipo.value != hint:
                    if tipo == TipoDocumento.OUTRO or hint in (
                        "cnh", "crlv", "tac", "comprovante",
                    ):
                        print(
                            f"[Gemini] tipo pelo local: {arq.name} "
                            f"{tipo.value} -> {hint}"
                        )
                        tipo = tipo_hint
            except ValueError:
                pass
        if tipo == TipoDocumento.IGNORAR:
            print(f"[Gemini] IGNORADO: {arq.name}")
            continue
        print(f"[Gemini] Enviando {arq.name} ({tipo.value})...")
        dados = extrair_arquivo(arq, tipo)
        dados["_fonte"] = dados.get("_fonte") or "gemini"
        # agrupa pelo tipo efetivo (hint/local), não pelo nome do arquivo
        chave = (dados.get("_tipo") or tipo.value)
        if chave not in resultado:
            chave = tipo.value
        resultado[chave].append(dados)
    return resultado


def _cache_incompleto_para_tipo(cached: Dict[str, Any], tipo: TipoDocumento) -> bool:
    """
    True se o cache foi gravado com prompt genérico (WhatsApp/OUTRO) e
    não tem os campos estruturados do tipo - só texto_relevante.
    """
    if not cached:
        return True
    t = tipo.value if hasattr(tipo, "value") else str(tipo)
    if t == "cnh":
        criticos = ("cnh", "categoria_cnh", "validade_cnh", "nome_mae", "data_nascimento")
        if any(cached.get(k) for k in criticos):
            return False
        # tem texto_relevante rico mas campos vazios -> incompleto
        return bool((cached.get("texto_relevante") or "").strip()) or not cached.get("nome")
    if t == "crlv":
        if cached.get("placa") and (
            cached.get("renavam")
            or cached.get("chassi")
            or cached.get("proprietario_nome")
            or cached.get("marca_modelo_versao")
            or cached.get("marca")
        ):
            return False
        return bool((cached.get("texto_relevante") or "").strip())
    if t == "tac":
        return not bool(cached.get("rntrc"))
    return False


def so_digitos(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def limpar_placa(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (s or "")).upper()
