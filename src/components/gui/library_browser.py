"""library_browser.py — Navegador de biblioteca: previsualiza por juego los
recursos scrapeados en disco (thumb/marquee/screenshot) y el texto del gamelist."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QMessageBox,
    QPushButton, QScrollArea, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from ..config import ASSET_DEFS, SYSTEM_LAUNCHER_EXTENSIONS
from ..gamelist_io import generate_gamelist, parse_gamelist_details, _pretty_name
from ..models import GameDetails

THUMB_SIZE = QSize(200, 300)
SHOT_SIZE = QSize(420, 236)
MARQUEE_SIZE = QSize(420, 120)


class LibraryBrowser(QDialog):
    def __init__(self, parent, roms: Path, systems: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Biblioteca — previsualización de scrapeos")
        self.resize(1050, 720)

        self._roms = roms
        self._systems = systems
        self._details: list[GameDetails] = []

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Sistema:"))
        self._system_combo = QComboBox()
        self._system_combo.addItems(systems)
        self._system_combo.currentTextChanged.connect(self._load_system)
        top.addWidget(self._system_combo, 1)
        self._gen_btn = QPushButton("Generar gamelist.xml")
        self._gen_btn.clicked.connect(self._on_generate)
        top.addWidget(self._gen_btn)
        refresh_btn = QPushButton("Recargar")
        refresh_btn.clicked.connect(lambda: self._load_system(self._system_combo.currentText()))
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        self._game_list = QListWidget()
        self._game_list.currentRowChanged.connect(self._show_game)
        splitter.addWidget(self._game_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        self._title_label = QLabel()
        self._title_label.setStyleSheet("font-weight: bold; font-size: 13pt;")
        self._title_label.setWordWrap(True)
        right_layout.addWidget(self._title_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setAlignment(Qt.AlignTop)

        self._thumb_label = QLabel("(sin thumbnail)")
        self._thumb_label.setAlignment(Qt.AlignCenter)
        self._marquee_label = QLabel("(sin marquee)")
        self._marquee_label.setAlignment(Qt.AlignCenter)
        self._shot_label = QLabel("(sin screenshot)")
        self._shot_label.setAlignment(Qt.AlignCenter)

        imgs = QHBoxLayout()
        imgs.addWidget(self._thumb_label)
        col = QVBoxLayout()
        col.addWidget(self._marquee_label)
        col.addWidget(self._shot_label)
        imgs.addLayout(col)
        self._content_layout.addLayout(imgs)

        self._meta_text = QTextEdit()
        self._meta_text.setReadOnly(True)
        self._content_layout.addWidget(self._meta_text)

        scroll.setWidget(content)
        right_layout.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

        if systems:
            self._load_system(systems[0])

    # ── Carga ────────────────────────────────────────────────────────────

    def _system_path(self, system: str) -> Path:
        return self._roms / system

    def _load_system(self, system: str) -> None:
        if not system:
            return
        self._game_list.clear()
        self._details = []
        sp = self._system_path(system)
        gamelist = sp / "gamelist.xml"

        if gamelist.exists():
            self._details = parse_gamelist_details(gamelist)
            self._gen_btn.setEnabled(False)
        else:
            # Sin gamelist: lista los launchers y adivina imágenes en disco
            ext = SYSTEM_LAUNCHER_EXTENSIONS.get(system, "")
            for f in sorted(p for p in sp.glob(f"*{ext}") if p.is_file()):
                stem = f.stem
                self._details.append(GameDetails(
                    name=_pretty_name(stem), file_stem=stem, metadata={},
                    images={adef["xml_tag"]: f"./images/{stem}{adef['suffix']}" for adef in ASSET_DEFS.values()},
                ))
            self._gen_btn.setEnabled(True)

        for d in self._details:
            self._game_list.addItem(d.name)
        if self._details:
            self._game_list.setCurrentRow(0)

    def _on_generate(self) -> None:
        system = self._system_combo.currentText()
        out = generate_gamelist(self._system_path(system), system)
        if out:
            QMessageBox.information(self, "gamelist.xml", f"Generado: {out}")
            self._load_system(system)
        else:
            QMessageBox.warning(self, "gamelist.xml", "No se encontraron ficheros launcher que listar.")

    # ── Previsualización de un juego ─────────────────────────────────────

    def _show_game(self, row: int) -> None:
        if row < 0 or row >= len(self._details):
            return
        details = self._details[row]
        sp = self._system_path(self._system_combo.currentText())
        self._title_label.setText(details.name)

        self._set_image(self._thumb_label, sp, details.images.get("thumbnail"), THUMB_SIZE)
        self._set_image(self._marquee_label, sp, details.images.get("marquee"), MARQUEE_SIZE)
        self._set_image(self._shot_label, sp, details.images.get("image"), SHOT_SIZE)

        if details.metadata:
            order = ["desc", "genre", "family", "developer", "publisher", "players", "releasedate", "rating"]
            html_parts = []
            for key in order + [k for k in details.metadata if k not in order]:
                if key in details.metadata:
                    html_parts.append(f"<p><b>{key}:</b> {details.metadata[key]}</p>")
            self._meta_text.setHtml("".join(html_parts))
        else:
            self._meta_text.setHtml("<p><i>Sin metadatos textuales todavía.</i></p>")

    @staticmethod
    def _set_image(label: QLabel, system_path: Path, rel: str | None, size: QSize) -> None:
        pixmap = None
        if rel:
            full = system_path / rel
            if full.exists():
                pixmap = QPixmap(str(full))
                if pixmap.isNull():
                    pixmap = None
        if pixmap is not None:
            label.setPixmap(pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            label.setPixmap(QPixmap())
            label.setText("(falta en disco)")
            label.setFixedSize(size)