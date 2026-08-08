"""folder_picker.py — Diálogo nativo para elegir la carpeta roms/."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog


def ask_roms_folder(parent, initial: str | None = None) -> Path | None:
    chosen = QFileDialog.getExistingDirectory(
        parent,
        "Selecciona la carpeta roms/",
        initial or str(Path.home()),
    )
    return Path(chosen) if chosen else None