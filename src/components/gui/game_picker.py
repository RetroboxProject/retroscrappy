"""game_picker.py — Diálogo modal para desambiguar resultados de búsqueda de juego."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QAbstractItemView,
)
from PySide6.QtCore import Qt

from ..models import GameCandidate


class GamePickerDialog(QDialog):
    def __init__(self, parent, query: str, candidates: list[GameCandidate]):
        super().__init__(parent)
        self.setWindowTitle(f"Elegir juego — {query}")
        self.resize(520, 420)
        self.setModal(True)

        self._candidates = candidates
        self._result: int | None = None

        layout = QVBoxLayout(self)

        label = QLabel(f"Varios resultados para «{query}». Elige el correcto:")
        label.setWordWrap(True)
        layout.addWidget(label)

        self._list_widget = QListWidget()
        self._list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        for c in candidates:
            year = c.year if c.year else "?"
            item = QListWidgetItem(f"{c.name}   ({year})   [id={c.id}]")
            self._list_widget.addItem(item)
        if candidates:
            self._list_widget.setCurrentRow(0)
        self._list_widget.itemDoubleClicked.connect(self._on_choose)
        layout.addWidget(self._list_widget)

        btn_layout = QHBoxLayout()
        skip_btn = QPushButton("Saltar este juego")
        skip_btn.clicked.connect(self._on_skip)
        btn_layout.addWidget(skip_btn)
        btn_layout.addStretch()
        choose_btn = QPushButton("Elegir")
        choose_btn.setDefault(True)
        choose_btn.clicked.connect(self._on_choose)
        btn_layout.addWidget(choose_btn)
        layout.addLayout(btn_layout)

    def _on_choose(self) -> None:
        items = self._list_widget.selectedItems()
        if items:
            idx = self._list_widget.row(items[0])
            self._result = self._candidates[idx].id
        self.accept()

    def _on_skip(self) -> None:
        self._result = None
        self.reject()

    def exec(self) -> int | None:
        super().exec()
        return self._result