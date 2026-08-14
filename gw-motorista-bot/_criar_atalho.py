"""Copia o iniciador para a Área de Trabalho (clique para abrir o robô)."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BAT = ROOT / "INICIAR_ROBO.bat"


def _desktop() -> Path:
    for p in (
        Path.home() / "Desktop",
        Path.home() / "OneDrive" / "Desktop",
        Path.home() / "Área de Trabalho",
    ):
        if p.is_dir():
            return p
    return Path.home() / "Desktop"


def main() -> None:
    if not BAT.exists():
        print("Não achei INICIAR_ROBO.bat")
        return
    dest = _desktop() / "Robo GW Motorista.bat"
    # .bat na área de trabalho que chama o real (mantém pasta certa)
    dest.write_text(
        f'@echo off\r\n'
        f'cd /d "{ROOT}"\r\n'
        f'call "{BAT}"\r\n',
        encoding="utf-8",
    )
    print(f"Atalho criado na Área de Trabalho:\n  {dest}")
    print("\nComo usar:")
    print("  1) Coloque docs em: input\\nome_do_motorista\\")
    print("  2) Duplo clique em: Robo GW Motorista")
    print("  3) Confira/corrija os dados e aperte ENTER")


if __name__ == "__main__":
    main()
