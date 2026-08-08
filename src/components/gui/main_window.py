"""main_window.py — Ventana principal: formulario de opciones + registro de actividad.

Lanza el scraping en un hilo de fondo (worker.Scraper) para que la ventana
nunca se congele, incluso mientras se descargan imágenes o se espera a que
el usuario elija algo en un diálogo modal.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..config import SUPPORTED_SYSTEMS
from ..worker import ScraperCancelled, ScraperOptions, Scraper
from .bridge import TkBridge
from .folder_picker import ask_roms_folder


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SteamGridDB Artwork Downloader")
        self.geometry("720x560")
        self.minsize(600, 480)

        self._roms_var = tk.StringVar()
        self._apikey_var = tk.StringVar()
        self._force_var = tk.BooleanVar(value=False)
        self._interactive_var = tk.BooleanVar(value=True)
        self._system_vars = {s: tk.BooleanVar(value=True) for s in SUPPORTED_SYSTEMS}

        self._worker_thread: threading.Thread | None = None
        self._cancel_requested = False

        self._build_ui()

    # ── Construcción de la UI ────────────────────────────────────────────

    def _build_ui(self) -> None:
        form = ttk.Frame(self, padding=12)
        form.pack(fill="x")

        # Carpeta roms/
        ttk.Label(form, text="Carpeta roms/:").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self._roms_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(form, text="Examinar…", command=self._on_browse).grid(row=0, column=2)

        # API key
        ttk.Label(form, text="API key SteamGridDB:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self._apikey_var, show="•").grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=(8, 0)
        )

        form.columnconfigure(1, weight=1)

        # Sistemas
        systems_frame = ttk.LabelFrame(self, text="Sistemas a procesar", padding=10)
        systems_frame.pack(fill="x", padx=12, pady=(4, 0))
        for s in SUPPORTED_SYSTEMS:
            ttk.Checkbutton(systems_frame, text=s, variable=self._system_vars[s]).pack(side="left", padx=6)

        # Opciones
        opts_frame = ttk.LabelFrame(self, text="Opciones", padding=10)
        opts_frame.pack(fill="x", padx=12, pady=8)
        ttk.Checkbutton(
            opts_frame, text="Forzar sobreescritura de archivos existentes", variable=self._force_var
        ).pack(anchor="w")
        ttk.Checkbutton(
            opts_frame,
            text="Elegir imágenes manualmente (galería estilo Playnite). Si no, se coge automáticamente la mejor.",
            variable=self._interactive_var,
        ).pack(anchor="w")

        # Botones de acción
        actions = ttk.Frame(self, padding=(12, 0))
        actions.pack(fill="x")
        self._start_btn = ttk.Button(actions, text="Iniciar", command=self._on_start)
        self._start_btn.pack(side="left")
        self._cancel_btn = ttk.Button(actions, text="Cancelar", command=self._on_cancel, state="disabled")
        self._cancel_btn.pack(side="left", padx=6)

        # Estado + log
        self._status_var = tk.StringVar(value="Listo.")
        ttk.Label(self, textvariable=self._status_var, padding=(12, 6)).pack(fill="x")

        log_frame = ttk.Frame(self, padding=(12, 0, 12, 12))
        log_frame.pack(fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical")
        self._log_text = tk.Text(
            log_frame, height=16, yscrollcommand=log_scroll.set, state="disabled", wrap="word"
        )
        log_scroll.config(command=self._log_text.yview)
        self._log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        self._bridge = TkBridge(self, log_fn=self._append_log, status_fn=self._set_status)

    # ── Acciones ─────────────────────────────────────────────────────────

    def _on_browse(self) -> None:
        folder = ask_roms_folder(self, initial=self._roms_var.get() or None)
        if folder:
            self._roms_var.set(str(folder))

    def _on_start(self) -> None:
        roms = self._roms_var.get().strip()
        apikey = self._apikey_var.get().strip()
        systems = [s for s, v in self._system_vars.items() if v.get()]

        if not roms:
            messagebox.showwarning("Falta la carpeta roms/", "Selecciona primero la carpeta roms/.")
            return
        if not apikey:
            messagebox.showwarning("Falta la API key", "Introduce tu API key de SteamGridDB.")
            return
        if not systems:
            messagebox.showwarning("Sin sistemas", "Selecciona al menos un sistema a procesar.")
            return

        options = ScraperOptions(
            roms=Path(roms),
            apikey=apikey,
            systems=systems,
            force=self._force_var.get(),
            interactive=self._interactive_var.get(),
        )

        self._cancel_requested = False
        self._set_running(True)
        self._clear_log()

        self._worker_thread = threading.Thread(target=self._run_scraper, args=(options,), daemon=True)
        self._worker_thread.start()

    def _on_cancel(self) -> None:
        self._cancel_requested = True
        self._set_status("Cancelando… (se detendrá tras el juego en curso)")

    def _run_scraper(self, options: ScraperOptions) -> None:
        scraper = Scraper(self._bridge, is_cancelled=lambda: self._cancel_requested)
        try:
            scraper.run(options)
        except ScraperCancelled:
            pass
        except Exception as e:
            self._bridge.log(f"✗ Error inesperado: {e}")
        finally:
            self.after(0, self._set_running, False)

    # ── Helpers de UI (siempre llamados en el hilo principal) ───────────

    def _set_running(self, running: bool) -> None:
        self._start_btn.config(state="disabled" if running else "normal")
        self._cancel_btn.config(state="normal" if running else "disabled")

    def _append_log(self, message: str) -> None:
        self._log_text.config(state="normal")
        self._log_text.insert("end", message + "\n")
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    def _clear_log(self) -> None:
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.config(state="disabled")

    def _set_status(self, message: str) -> None:
        self._status_var.set(message)


def main() -> None:
    app = MainWindow()
    app.mainloop()
