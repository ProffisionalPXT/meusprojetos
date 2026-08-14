from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
PROCESSADOS_DIR = OUTPUT_DIR / "processados"
LOGS_DIR = ROOT / "logs"

# Foto, PDF e HEIC (iPhone) - no mesmo caso pode misturar tudo
EXTENSOES_FOTO = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".pdf",
    ".tif",
    ".tiff",
    ".bmp",
    ".heic",
    ".heif",
}


def garantir_pastas() -> None:
    for pasta in (INPUT_DIR, OUTPUT_DIR, PROCESSADOS_DIR, LOGS_DIR):
        pasta.mkdir(parents=True, exist_ok=True)
