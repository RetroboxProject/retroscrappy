"""bridge.py — Implementación de UserInteraction basada en tkinter.

tkinter solo puede crear/tocar widgets desde el hilo principal, pero el
scraping ocurre en un hilo de fondo (para no congelar la ventana). Este
puente resuelve el cruce: cada método que necesita abrir un diálogo
programa su ejecución en el hilo principal con `root.after(0, ...)` y
espera el resultado en una `queue.Queue`, bloqueando solo el hilo de
fondo (el hilo de tkinter sigue respondiendo con normalidad).
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox
from typing import Callable

from ..models import GameCandidate, ImageCandidate
from .game_picker import GamePickerDialog
from .image_picker import ImagePickerDialog


class TkBridge:
    def __init__(self, root: tk.Tk, log_fn: Callable[[str], None], status_fn: Callable[[str], None]):
        self._root = root
        self._log_fn = log_fn
        self._status_fn = status_fn

    # ── UserInteraction ──────────────────────────────────────────────────

    def choose_game(self, query: str, candidates: list[GameCandidate]) -> int | None:
        return self._run_on_main(lambda: GamePickerDialog(self._root, query, candidates).show())

    def choose_image(self, label: str, candidates: list[ImageCandidate]) -> ImageCandidate | None:
        return self._run_on_main(lambda: ImagePickerDialog(self._root, label, candidates).show())

    def confirm_overwrite(self, filename: str) -> bool:
        return self._run_on_main(
            lambda: messagebox.askyesno("Archivo existente", f"Ya existe «{filename}». ¿Sobreescribir?")
        )

    def log(self, message: str) -> None:
        self._root.after(0, self._log_fn, message)

    def set_status(self, message: str) -> None:
        self._root.after(0, self._status_fn, message)

    # ── Interno ──────────────────────────────────────────────────────────

    def _run_on_main(self, factory: Callable[[], object]):
        """Ejecuta `factory` en el hilo principal y devuelve su resultado,
        bloqueando el hilo llamante (de fondo) hasta que esté disponible."""
        result_q: queue.Queue = queue.Queue(maxsize=1)

        def task():
            try:
                result_q.put(factory())
            except Exception:
                result_q.put(None)

        self._root.after(0, task)
        return result_q.get()
