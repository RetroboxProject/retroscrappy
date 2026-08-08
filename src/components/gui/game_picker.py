"""game_picker.py — Diálogo modal para desambiguar resultados de búsqueda de juego."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..models import GameCandidate


class GamePickerDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, query: str, candidates: list[GameCandidate]):
        super().__init__(parent)
        self.title(f"Elegir juego — {query}")
        self.geometry("520x420")
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)

        self._result: int | None = None
        self._candidates = candidates

        ttk.Label(
            self, text=f"Varios resultados para «{query}». Elige el correcto:",
            wraplength=480, padding=(10, 10),
        ).pack(fill="x")

        list_frame = ttk.Frame(self, padding=(10, 0))
        list_frame.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        self._listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set, activestyle="dotbox", font=("TkDefaultFont", 10),
        )
        scrollbar.config(command=self._listbox.yview)
        self._listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for c in candidates:
            year = c.year if c.year else "?"
            self._listbox.insert("end", f"{c.name}   ({year})   [id={c.id}]")
        if candidates:
            self._listbox.selection_set(0)
        self._listbox.bind("<Double-Button-1>", lambda _e: self._on_choose())

        btns = ttk.Frame(self, padding=10)
        btns.pack(fill="x")
        ttk.Button(btns, text="Saltar este juego", command=self._on_skip).pack(side="left")
        ttk.Button(btns, text="Elegir", command=self._on_choose).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_skip)

    def _on_choose(self) -> None:
        sel = self._listbox.curselection()
        if sel:
            self._result = self._candidates[sel[0]].id
        self.destroy()

    def _on_skip(self) -> None:
        self._result = None
        self.destroy()

    def show(self) -> int | None:
        self.wait_window(self)
        return self._result
