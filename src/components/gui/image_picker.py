"""image_picker.py — Galería de miniaturas para elegir un asset (estilo Playnite)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget,
    QGridLayout, QPushButton, QFrame,
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt as QtCore_Qt

from ..models import ImageCandidate

COLUMNS = 4
THUMB_MAX_SIZE = (180, 240)


class ImagePickerDialog(QDialog):
    def __init__(self, parent, label: str, candidates: list[ImageCandidate]):
        super().__init__(parent)
        self.setWindowTitle(f"Elegir imagen — {label}")
        self.resize(820, 620)
        self.setModal(True)

        self._candidates = candidates
        self._result: ImageCandidate | None = None

        layout = QVBoxLayout(self)

        title = QLabel(label)
        title.setStyleSheet("font-weight: bold; font-size: 11pt; padding: 6px;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(8)

        for i, cand in enumerate(candidates):
            row, col = divmod(i, COLUMNS)
            cell = QFrame()
            cell.setFrameShape(QFrame.Box)
            cell.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 4px; padding: 4px; }")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(4, 4, 4, 4)

            img_label = QLabel()
            img_label.setCursor(QtCore_Qt.PointingHandCursor)
            img_label.setAlignment(QtCore_Qt.AlignCenter)

            if cand.preview:
                pixmap = QPixmap()
                pixmap.loadFromData(cand.preview)
                pixmap = pixmap.scaled(
                    THUMB_MAX_SIZE[0], THUMB_MAX_SIZE[1],
                    QtCore_Qt.KeepAspectRatio, QtCore_Qt.SmoothTransformation,
                )
                img_label.setPixmap(pixmap)
                img_label.setFixedSize(pixmap.size())
            else:
                img_label.setText("(sin previsualización)")
                img_label.setFixedSize(180, 240)
                img_label.setStyleSheet("border: 1px dashed palette(mid);")

            img_label.mousePressEvent = lambda event, c=cand: self._on_choose(c)
            cell_layout.addWidget(img_label, alignment=QtCore_Qt.AlignCenter)

            dims = f"{cand.width}×{cand.height}" if cand.width and cand.height else "resolución n/d"
            info = f"score {cand.score:+d}  ·  {dims}\n{cand.author}"
            info_label = QLabel(info)
            info_label.setAlignment(QtCore_Qt.AlignCenter)
            info_label.setStyleSheet("font-size: 8pt; color: palette(text);")
            cell_layout.addWidget(info_label)

            grid.addWidget(cell, row, col)

        for col in range(COLUMNS):
            grid.setColumnStretch(col, 1)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        skip_btn = QPushButton("Saltar este asset")
        skip_btn.clicked.connect(self._on_skip)
        btn_layout.addWidget(skip_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _on_choose(self, candidate: ImageCandidate) -> None:
        self._result = candidate
        self.accept()

    def _on_skip(self) -> None:
        self._result = None
        self.reject()

    def exec(self) -> ImageCandidate | None:
        super().exec()
        return self._result