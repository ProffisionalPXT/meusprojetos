"""
Recebe fotos/documentos da pasta input/ e organiza em "casos" de cadastro.

Estruturas aceitas:
  input/<nome_motorista>/*.{jpg,png,pdf,...}
  input/*.{jpg,png,pdf,...}   -> um único caso "lote_solto"

Após cadastro OK: pasta vai para output/processados/ (não precisa excluir na mão).
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ocr.tipos_documento import TipoDocumento, agrupar_por_tipo, classificar_arquivo
from utils.paths import EXTENSOES_FOTO, INPUT_DIR, PROCESSADOS_DIR, garantir_pastas


@dataclass
class CasoCadastro:
    """Um motorista/lote a ser cadastrado, com suas fotos."""
    nome: str
    pasta: Path
    arquivos: List[Path] = field(default_factory=list)

    def por_tipo(self, *palavras: str) -> List[Path]:
        """Filtra arquivos cujo nome contenha alguma das palavras (ex: 'cnh', 'rg')."""
        achados = []
        for arq in self.arquivos:
            nome = arq.stem.lower()
            if any(p.lower() in nome for p in palavras):
                achados.append(arq)
        return achados

    def por_tipo_doc(self, tipo: TipoDocumento) -> List[Path]:
        return [a for a in self.arquivos if classificar_arquivo(a) == tipo]

    def resumo_tipos(self) -> str:
        g = agrupar_por_tipo(self.arquivos)
        partes = []
        for t in (
            TipoDocumento.TAC,
            TipoDocumento.CNH,
            TipoDocumento.CRLV,
            TipoDocumento.COMPROVANTE,
            TipoDocumento.OUTRO,
        ):
            n = len(g[t])
            if n:
                partes.append(f"{t.value}={n}")
        return ", ".join(partes) if partes else "sem classificação"


def _eh_arquivo_valido(path: Path) -> bool:
    name = path.name.lower()
    if path.suffix.lower() in (".bat", ".lnk", ".url", ".exe", ".cmd"):
        return False
    if any(x in name for x in ("iniciar", "robo", "robô", "shortcut")):
        return False
    return path.is_file() and path.suffix.lower() in EXTENSOES_FOTO


def listar_casos(input_dir: Path | None = None) -> List[CasoCadastro]:
    """
    Varre input/ e devolve a lista de casos com fotos.
    Pastas ocultas e COMO_USAR.txt são ignorados.
    """
    garantir_pastas()
    base = input_dir or INPUT_DIR
    
    try:
        from utils.pdf_misto import verificar_e_separar_pdfs_mistos
        verificar_e_separar_pdfs_mistos(base)
    except Exception as e:
        print(f"[AVISO] Falha ao verificar PDFs mistos: {e}")

    casos: List[CasoCadastro] = []

    for item in sorted(base.iterdir()):
        if item.is_dir() and not item.name.startswith(".") and not item.name.startswith("_"):
            arquivos = sorted(
                p for p in item.rglob("*") 
                if _eh_arquivo_valido(p) and "_originais" not in p.parts
            )
            if arquivos:
                casos.append(CasoCadastro(nome=item.name, pasta=item, arquivos=arquivos))

    soltos = sorted(p for p in base.iterdir() if _eh_arquivo_valido(p))
    if soltos:
        casos.append(CasoCadastro(nome="lote_solto", pasta=base, arquivos=soltos))

    return casos


def resumo_casos(casos: List[CasoCadastro]) -> str:
    if not casos:
        return "Nenhuma foto encontrada em input/."
    linhas = [f"Encontrados {len(casos)} caso(s) em input/:"]
    for c in casos:
        linhas.append(f"  * {c.nome}: {len(c.arquivos)} arquivo(s) [{c.resumo_tipos()}]")
        for a in c.arquivos:
            linhas.append(f"      - {a.name} -> {classificar_arquivo(a).value}")
    return "\n".join(linhas)


def arquivar_ativo() -> bool:
    """ARQUIVAR_APOS=1 (padrão) - move pasta para processados após sucesso."""
    v = (os.getenv("ARQUIVAR_APOS", "1") or "1").strip().lower()
    return v not in ("0", "false", "nao", "não", "no", "off")


def arquivar_caso(caso: CasoCadastro, *, motivo: str = "ok") -> Optional[Path]:
    """
    Move a pasta do motorista de input/ para output/processados/.
    Assim o próximo run não reprocessa e você não precisa excluir na mão.

    - pasta input/joao/ -> processados/20260709_1430_joao/
    - arquivos soltos (lote_solto) -> processados/20260709_1430_lote_solto/*.pdf
    """
    if not arquivar_ativo():
        print("[Arquivar] ARQUIVAR_APOS=0 - pasta permanece em input/")
        return None

    garantir_pastas()
    PROCESSADOS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_nome = f"{ts}_{caso.nome}"
    dest = PROCESSADOS_DIR / dest_nome

    try:
        dest.mkdir(parents=True, exist_ok=True)
        movidos = 0
        for arq in caso.arquivos:
            arq = Path(arq)
            if not arq.exists():
                continue
            name = arq.name.lower()
            if arq.suffix.lower() in (".bat", ".lnk", ".url", ".exe", ".cmd"):
                continue
            if any(x in name for x in ("iniciar", "robo", "robô", "shortcut")):
                continue
            shutil.move(str(arq), str(dest / arq.name))
            movidos += 1
        if movidos:
            print(f"[Arquivar] {movidos} arquivo(s) movido(s) para -> {dest}")
            print("           (arquivos removidos da pasta de entrada - pasta vazia mantida)")
            return dest
        print("[Arquivar] Nada a mover.")
        return None
    except Exception as e:
        print(f"[Arquivar] [!] Não moveu pasta (pode excluir/mover na mão): {e}")
        return None
