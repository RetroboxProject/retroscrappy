"""main_window.py — Ventana principal en PySide6.

Ejecuta el scraping (artwork SGDB + metadatos textuales) en un hilo de fondo
(threading.Thread) para que la ventana nunca se congele. La comunicación entre
hilos se hace exclusivamente con señales Qt en modo Qt.QueuedConnection.

Las opciones se cargan y guardan en un .ini vía components.settings.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QGroupBox, QFormLayout,
    QTextEdit, QMessageBox, QTabWidget, QRadioButton, QComboBox, QButtonGroup,
)

from ..config import (
    SUPPORTED_SYSTEMS,
    METADATA_SOURCES, METADATA_SOURCE_LABELS,
    MODES, MODE_LABELS, MODE_SEMI,
    SOURCE_NONE, SOURCE_IGDB, SOURCE_SCREENSCRAPER,
)
from ..gamelist_io import generate_gamelist
from ..metadata_worker import MetadataScraper, MetadataScraperOptions
from ..settings import AppSettings, load_settings, save_settings
from ..worker import ScraperCancelled, ScraperOptions, Scraper
from .bridge import BridgeSignals, QtBridge
from .folder_picker import ask_roms_folder
from .game_picker import GamePickerDialog
from .image_picker import ImagePickerDialog
from .library_browser import LibraryBrowser


class MainWindow(QMainWindow):
    scrape_finished = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SteamGridDB Artwork Downloader")
        self.resize(860, 720)
        self.setMinimumSize(700, 560)

        self._worker_thread: threading.Thread | None = None
        self._cancel_requested = False

        self._bridge_signals = BridgeSignals()
        for sig, slot in (
            (self._bridge_signals.choose_game_requested, self._on_choose_game),
            (self._bridge_signals.choose_image_requested, self._on_choose_image),
            (self._bridge_signals.confirm_overwrite_requested, self._on_confirm_overwrite),
            (self._bridge_signals.log_signal, self._append_log),
            (self._bridge_signals.status_signal, self._set_status),
        ):
            sig.connect(slot, Qt.QueuedConnection)

        self.scrape_finished.connect(self._on_scrape_finished, Qt.QueuedConnection)

        self._build_ui()

        # Carga la configuración persistida y rellena el formulario.
        self._apply_settings(load_settings())

    # ── Construcción de la UI ────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        self._tabs = QTabWidget()
        main_layout.addWidget(self._tabs, 1)

        # ── Tab 1: Artwork (SteamGridDB) ────────────────────────────────
        art_tab = QWidget()
        art_layout = QVBoxLayout(art_tab)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self._roms_edit = QLineEdit()
        self._roms_edit.setPlaceholderText("/ruta/a/roms/")
        browse_btn = QPushButton("Examinar…")
        browse_btn.clicked.connect(self._on_browse)
        roms_layout = QHBoxLayout()
        roms_layout.setContentsMargins(0, 0, 0, 0)
        roms_layout.addWidget(self._roms_edit, 1)
        roms_layout.addWidget(browse_btn)
        form.addRow("Carpeta roms/:", roms_layout)

        self._apikey_edit = QLineEdit()
        self._apikey_edit.setPlaceholderText("Pega aquí tu API key de SteamGridDB")
        self._apikey_edit.setEchoMode(QLineEdit.Password)
        form.addRow("API key SteamGridDB:", self._apikey_edit)
        art_layout.addLayout(form)

        systems_group = QGroupBox("Sistemas a procesar")
        systems_layout = QHBoxLayout()
        self._system_checks: dict[str, QCheckBox] = {}
        for s in SUPPORTED_SYSTEMS:
            cb = QCheckBox(s)
            cb.setChecked(True)
            systems_layout.addWidget(cb)
            self._system_checks[s] = cb
        systems_layout.addStretch()
        systems_group.setLayout(systems_layout)
        art_layout.addWidget(systems_group)

        self._gen_gamelist_check = QCheckBox(
            "Generar gamelist.xml limpio si no existe (desde .steam/.heroic/.lynx)"
        )
        self._gen_gamelist_check.setChecked(True)
        art_layout.addWidget(self._gen_gamelist_check)

        mode_group = QGroupBox("Modo de interacción (artwork)")
        mode_layout = QVBoxLayout()
        self._mode_group = QButtonGroup(self)
        self._mode_radios: dict[str, QRadioButton] = {}
        for m in MODES:
            rb = QRadioButton(MODE_LABELS[m])
            self._mode_group.addButton(rb)
            self._mode_radios[m] = rb
            mode_layout.addWidget(rb)
        self._mode_radios[MODE_SEMI].setChecked(True)
        mode_group.setLayout(mode_layout)
        art_layout.addWidget(mode_group)

        self._force_check = QCheckBox("Forzar sobreescritura de imágenes existentes")
        art_layout.addWidget(self._force_check)

        art_layout.addStretch()
        self._tabs.addTab(art_tab, "Artwork (SteamGridDB)")

        # ── Tab 2: Metadatos textuales ──────────────────────────────────
        meta_tab = QWidget()
        meta_layout = QVBoxLayout(meta_tab)

        src_form = QFormLayout()
        src_form.setLabelAlignment(Qt.AlignRight)
        self._source_combo = QComboBox()
        for s in METADATA_SOURCES:
            self._source_combo.addItem(METADATA_SOURCE_LABELS[s], s)
        self._source_combo.setCurrentIndex(1)  # IGDB por defecto
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        src_form.addRow("Fuente de metadatos:", self._source_combo)
        meta_layout.addLayout(src_form)

        self._igdb_group = QGroupBox("Credenciales IGDB (dev.twitch.tv)")
        igdb_form = QFormLayout()
        self._igdb_id_edit = QLineEdit()
        self._igdb_secret_edit = QLineEdit()
        self._igdb_secret_edit.setEchoMode(QLineEdit.Password)
        igdb_form.addRow("Client ID:", self._igdb_id_edit)
        igdb_form.addRow("Client Secret:", self._igdb_secret_edit)
        self._igdb_group.setLayout(igdb_form)
        meta_layout.addWidget(self._igdb_group)

        self._ss_group = QGroupBox(
            "Credenciales ScreenScraper (devid/devpassword vía foro; ssid/sspassword de tu cuenta)"
        )
        ss_form = QFormLayout()
        self._ss_devid_edit = QLineEdit()
        self._ss_devpass_edit = QLineEdit()
        self._ss_devpass_edit.setEchoMode(QLineEdit.Password)
        self._ss_ssid_edit = QLineEdit()
        self._ss_sspass_edit = QLineEdit()
        self._ss_sspass_edit.setEchoMode(QLineEdit.Password)
        ss_form.addRow("Dev ID:", self._ss_devid_edit)
        ss_form.addRow("Dev password:", self._ss_devpass_edit)
        ss_form.addRow("Usuario (ssid):", self._ss_ssid_edit)
        ss_form.addRow("Password (sspassword):", self._ss_sspass_edit)
        self._ss_group.setLayout(ss_form)
        meta_layout.addWidget(self._ss_group)

        self._force_meta_check = QCheckBox("Forzar sobreescritura de campos de texto ya rellenos")
        meta_layout.addWidget(self._force_meta_check)

        meta_layout.addStretch()
        self._tabs.addTab(meta_tab, "Metadatos textuales")

        self._on_source_changed(self._source_combo.currentIndex())

        # ── Zona común: botones + estado + log ──────────────────────────
        btn_layout = QHBoxLayout()
        self._start_btn = QPushButton("Iniciar")
        self._start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self._start_btn)

        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._cancel_btn.setEnabled(False)
        btn_layout.addWidget(self._cancel_btn)

        self._library_btn = QPushButton("📚 Biblioteca (previsualizar)")
        self._library_btn.clicked.connect(self._on_library)
        btn_layout.addWidget(self._library_btn)

        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        self._status_label = QLabel("Listo.")
        main_layout.addWidget(self._status_label)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setLineWrapMode(QTextEdit.NoWrap)
        self._log_text.setFontFamily("Monospace")
        main_layout.addWidget(self._log_text, 1)

    # ── Persistencia de opciones ─────────────────────────────────────────

    def _collect_settings(self) -> AppSettings:
        return AppSettings(
            roms=self._roms_edit.text().strip(),
            systems=self._collect_systems(),
            gen_gamelist=self._gen_gamelist_check.isChecked(),
            apikey=self._apikey_edit.text().strip(),
            mode=next(m for m, rb in self._mode_radios.items() if rb.isChecked()),
            force_art=self._force_check.isChecked(),
            source=self._source_combo.currentData() or SOURCE_IGDB,
            force_meta=self._force_meta_check.isChecked(),
            igdb_client_id=self._igdb_id_edit.text().strip(),
            igdb_client_secret=self._igdb_secret_edit.text().strip(),
            ss_devid=self._ss_devid_edit.text().strip(),
            ss_devpassword=self._ss_devpass_edit.text().strip(),
            ss_ssid=self._ss_ssid_edit.text().strip(),
            ss_sspassword=self._ss_sspass_edit.text().strip(),
        )

    def _apply_settings(self, s: AppSettings) -> None:
        self._roms_edit.setText(s.roms)
        for sysname, cb in self._system_checks.items():
            cb.setChecked(sysname in s.systems)
        self._gen_gamelist_check.setChecked(s.gen_gamelist)
        self._apikey_edit.setText(s.apikey)
        if s.mode in self._mode_radios:
            self._mode_radios[s.mode].setChecked(True)
        self._force_check.setChecked(s.force_art)

        for i in range(self._source_combo.count()):
            if self._source_combo.itemData(i) == s.source:
                self._source_combo.setCurrentIndex(i)
                break
        self._force_meta_check.setChecked(s.force_meta)
        self._igdb_id_edit.setText(s.igdb_client_id)
        self._igdb_secret_edit.setText(s.igdb_client_secret)
        self._ss_devid_edit.setText(s.ss_devid)
        self._ss_devpass_edit.setText(s.ss_devpassword)
        self._ss_ssid_edit.setText(s.ss_ssid)
        self._ss_sspass_edit.setText(s.ss_sspassword)

    def _save_settings(self) -> None:
        try:
            save_settings(self._collect_settings())
        except Exception:
            pass  # nunca bloquear el cierre por un fallo de escritura

    def closeEvent(self, event) -> None:
        self._save_settings()
        super().closeEvent(event)

    # ── Acciones ─────────────────────────────────────────────────────────

    def _on_browse(self) -> None:
        folder = ask_roms_folder(self, initial=self._roms_edit.text() or None)
        if folder:
            self._roms_edit.setText(str(folder))

    def _on_source_changed(self, index: int) -> None:
        source = self._source_combo.itemData(index)
        self._igdb_group.setVisible(source == SOURCE_IGDB)
        self._ss_group.setVisible(source == SOURCE_SCREENSCRAPER)

    def _on_library(self) -> None:
        roms = self._roms_edit.text().strip()
        if not roms:
            QMessageBox.warning(self, "Biblioteca", "Selecciona primero la carpeta roms/.")
            return
        systems = [s for s, cb in self._system_checks.items() if cb.isChecked()] or list(SUPPORTED_SYSTEMS)
        LibraryBrowser(self, Path(roms), systems).show()

    def _collect_systems(self) -> list[str]:
        return [s for s, cb in self._system_checks.items() if cb.isChecked()]

    def _on_start(self) -> None:
        roms = self._roms_edit.text().strip()
        apikey = self._apikey_edit.text().strip()
        systems = self._collect_systems()

        if not roms:
            QMessageBox.warning(self, "Falta la carpeta roms/", "Selecciona primero la carpeta roms/.")
            return
        if not apikey:
            QMessageBox.warning(self, "Falta la API key", "Introduce tu API key de SteamGridDB.")
            return
        if not systems:
            QMessageBox.warning(self, "Sin sistemas", "Selecciona al menos un sistema a procesar.")
            return

        # Guarda la configuración actual antes de lanzar nada.
        self._save_settings()

        mode = next(m for m, rb in self._mode_radios.items() if rb.isChecked())
        source = self._source_combo.currentData()
        gen_gamelist = self._gen_gamelist_check.isChecked()

        art_options = ScraperOptions(
            roms=Path(roms),
            apikey=apikey,
            systems=systems,
            force=self._force_check.isChecked(),
            mode=mode,
        )
        meta_options = MetadataScraperOptions(
            roms=Path(roms),
            systems=systems,
            source=source,
            igdb_client_id=self._igdb_id_edit.text().strip(),
            igdb_client_secret=self._igdb_secret_edit.text().strip(),
            ss_devid=self._ss_devid_edit.text().strip(),
            ss_devpassword=self._ss_devpass_edit.text().strip(),
            ss_ssid=self._ss_ssid_edit.text().strip(),
            ss_sspassword=self._ss_sspass_edit.text().strip(),
            force=self._force_meta_check.isChecked(),
        )

        self._cancel_requested = False
        self._set_running(True)
        self._log_text.clear()

        bridge = QtBridge(self._bridge_signals)
        self._worker_thread = threading.Thread(
            target=self._run_scrapers,
            args=(art_options, meta_options, bridge, gen_gamelist),
            daemon=True,
        )
        self._worker_thread.start()

    def _on_cancel(self) -> None:
        self._cancel_requested = True
        self._set_status("Cancelando… (se detendrá tras el juego en curso)")

    # ── Hilo de fondo ────────────────────────────────────────────────────

    def _run_scrapers(
        self,
        art_options: ScraperOptions,
        meta_options: MetadataScraperOptions,
        bridge: QtBridge,
        gen_gamelist: bool,
    ) -> None:
        bridge.log(f"→ Modo artwork: {art_options.mode} | Fuente metadatos: {METADATA_SOURCE_LABELS[meta_options.source]}")

        # 1) gamelist.xml limpio si falta
        if gen_gamelist:
            for system in art_options.systems:
                if self._cancel_requested:
                    break
                sp = art_options.roms / system
                if sp.is_dir() and not (sp / "gamelist.xml").exists():
                    try:
                        out = generate_gamelist(sp, system)
                        if out:
                            bridge.log(f"[{system}] ✓ gamelist.xml generado ({out})")
                        else:
                            bridge.log(f"[{system}] ✗ sin ficheros launcher, no se generó gamelist.")
                    except Exception as e:
                        bridge.log(f"[{system}] ✗ Error generando gamelist.xml: {e}")

        # 2) artwork desde SteamGridDB — su fallo NO bloquea los metadatos
        try:
            Scraper(bridge, is_cancelled=lambda: self._cancel_requested).run(art_options)
        except ScraperCancelled:
            bridge.log("— Cancelado antes de los metadatos.")
            self.scrape_finished.emit()
            return
        except Exception as e:
            bridge.log(f"✗ Error inesperado en el artwork: {e}")

        # 3) metadatos textuales — siempre que no se haya cancelado
        if meta_options.source != SOURCE_NONE:
            try:
                MetadataScraper(bridge, is_cancelled=lambda: self._cancel_requested).run(meta_options)
            except ScraperCancelled:
                pass
            except Exception as e:
                bridge.log(f"✗ Error inesperado en los metadatos: {e}")
        else:
            bridge.log("— Metadatos textuales desactivados (pestaña «Metadatos textuales» → Fuente).")

        self.scrape_finished.emit()

    @Slot()
    def _on_scrape_finished(self) -> None:
        self._set_running(False)
        self._set_status("Listo.")

    def _set_running(self, running: bool) -> None:
        self._start_btn.setEnabled(not running)
        self._cancel_btn.setEnabled(running)

    # ── Slots invocados por el worker (en el hilo principal) ────────────

    @Slot(str)
    def _append_log(self, message: str) -> None:
        self._log_text.append(message)
        sb = self._log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    @Slot(str)
    def _set_status(self, message: str) -> None:
        self._status_label.setText(message)

    @Slot(str, list)
    def _on_choose_game(self, query: str, candidates: list) -> None:
        dialog = GamePickerDialog(self, query, candidates)
        result = dialog.exec()
        self._bridge_signals.game_chosen.emit(result)

    @Slot(str, list)
    def _on_choose_image(self, label: str, candidates: list) -> None:
        dialog = ImagePickerDialog(self, label, candidates)
        result = dialog.exec()
        self._bridge_signals.image_chosen.emit(result)

    @Slot(str)
    def _on_confirm_overwrite(self, filename: str) -> None:
        answer = QMessageBox.question(
            self,
            "Archivo existente",
            f"Ya existe «{filename}». ¿Sobreescribir?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        self._bridge_signals.overwrite_confirmed.emit(answer == QMessageBox.Yes)


def main() -> None:
    import sys

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Breeze")
    win = MainWindow()
    win.show()
    app.exec()