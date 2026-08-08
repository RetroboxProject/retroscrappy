"""image_picker.py — Galería de miniaturas para elegir un asset (al estilo
Playnite: varias portadas/logos en una cuadrícula, se hace click en la que
se quiere usar).
"""

from __future__ import annotations

import io
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from ..models import ImageCandidate

THUMB_MAX_SIZE = (180, 240)  # tamaño máximo de la miniatura dentro de la celda
COLUMNS = 4


class ImagePickerDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, label: str, candidates: list[ImageCandidate]):
        super().__init__(parent)
        self.withdraw()  # oculto hasta que la galería esté montada, evita el "flash" de ventana vacía
        self.title(f"Elegir imagen — {label}")
        self.geometry("820x620")
        self.transient(parent)
        self.resizable(True, True)

        self._result: ImageCandidate | None = None
        self._photo_refs: list[ImageTk.PhotoImage] = []  # evita que el GC borre las imágenes

        ttk.Label(self, text=label, font=("TkDefaultFont", 11, "bold"), padding=(10, 10)).pack(fill="x")

        canvas = tk.Canvas(self, highlightthickness=0)
        vbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 10))
        vbar.pack(side="right", fill="y")

        grid = ttk.Frame(canvas)
        grid_window = canvas.create_window((0, 0), window=grid, anchor="nw")

        def _on_grid_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_resize(event):
            canvas.itemconfig(grid_window, width=event.width)

        grid.bind("<Configure>", _on_grid_configure)
        canvas.bind("<Configure>", _on_canvas_resize)

        self._build_gallery(grid, candidates)

        btns = ttk.Frame(self, padding=10)
        btns.pack(fill="x")
        ttk.Button(btns, text="Saltar este asset", command=self._on_skip).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._on_skip)

        self.deiconify()  # ya está todo montado: ahora sí se muestra
        self.grab_set()
        self.lift()

    def _build_gallery(self, grid: ttk.Frame, candidates: list[ImageCandidate]) -> None:
        for i, cand in enumerate(candidates):
            row, col = divmod(i, COLUMNS)
            cell = ttk.Frame(grid, padding=8, relief="groove", borderwidth=1)
            cell.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)

            photo = self._load_thumbnail(cand.preview)
            if photo is not None:
                self._photo_refs.append(photo)
                img_label = tk.Label(cell, image=photo, cursor="hand2")
            else:
                img_label = tk.Label(cell, text="(sin previsualización)", width=22, height=10, cursor="hand2")
            img_label.pack()

            info = f"score {cand.score:+d}  ·  {cand.width}×{cand.height}\n{cand.author}"
            ttk.Label(cell, text=info, justify="center", font=("TkDefaultFont", 8)).pack(pady=(4, 0))

            def _choose(_event=None, c=cand):
                self._on_choose(c)

            img_label.bind("<Button-1>", _choose)
            cell.bind("<Button-1>", _choose)

        for col in range(COLUMNS):
            grid.columnconfigure(col, weight=1)

    @staticmethod
    def _load_thumbnail(raw: bytes | None) -> ImageTk.PhotoImage | None:
        if not raw:
            return None
        try:
            img = Image.open(io.BytesIO(raw))
            img.thumbnail(THUMB_MAX_SIZE)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _on_choose(self, candidate: ImageCandidate) -> None:
        self._result = candidate
        self.destroy()

    def _on_skip(self) -> None:
        self._result = None
        self.destroy()

    def show(self) -> ImageCandidate | None:
        self.wait_window(self)
        return self._result
