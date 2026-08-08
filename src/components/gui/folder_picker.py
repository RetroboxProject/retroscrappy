"""folder_picker.py — Diálogo nativo para elegir la carpeta roms/."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog


def ask_roms_folder(parent: tk.Misc, initial: str | None = None) -> Path | None:
    chosen = filedialog.askdirectory(
        parent=parent,
        title="Selecciona la carpeta roms/",
        initialdir=initial or str(Path.home()),
        mustexist=True,
    )
    return Path(chosen) if chosen else None
