"""Small reusable widgets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QWidget,
)

from retroscrappy.core.items import Field, MediaKind
from retroscrappy.gui.labels import field_label, media_label


class PathPicker(QWidget):
    """Line edit plus a *Browse…* button for a folder or a file."""

    def __init__(self, select_dir: bool, placeholder: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._select_dir = select_dir
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        browse = QPushButton(self.tr("Browse…"))
        browse.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(browse)

    def text(self) -> str:
        """Current path text."""
        return self.edit.text().strip()

    def set_text(self, value: str) -> None:
        """Set the path text."""
        self.edit.setText(value)

    def _browse(self) -> None:
        start = self.text() or str(Path.home())
        if self._select_dir:
            chosen = QFileDialog.getExistingDirectory(self, self.tr("Choose a folder"), start)
        else:
            chosen, _ = QFileDialog.getOpenFileName(
                self, self.tr("Choose a file"), start, self.tr("ES systems (*.cfg *.xml);;All (*)")
            )
        if chosen:
            self.edit.setText(chosen)


class OrderedCheckList(QListWidget):
    """Drag-to-reorder list whose items can be ticked on or off."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def set_items(self, ordered_on: list[str], all_keys: list[str], labels: dict[str, str]) -> None:
        """Show ``ordered_on`` first (ticked) then the remaining keys (unticked)."""
        self.clear()
        rest = [k for k in all_keys if k not in ordered_on]
        for key in [*ordered_on, *rest]:
            item = QListWidgetItem(labels.get(key, key))
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            on = key in ordered_on
            item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.addItem(item)

    def checked_keys(self) -> list[str]:
        """Ticked keys in display order."""
        return [
            self.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.count())
            if self.item(i).checkState() == Qt.CheckState.Checked
        ]


class ItemChecklist(QWidget):
    """Grid of check boxes for text fields or media kinds."""

    COLUMNS = 2

    def __init__(self, items: list[Field] | list[MediaKind], parent: QWidget | None = None):
        super().__init__(parent)
        self._boxes: dict[Field | MediaKind, QCheckBox] = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        for index, item in enumerate(items):
            label = field_label(item) if isinstance(item, Field) else media_label(item)
            box = QCheckBox(label)
            self._boxes[item] = box
            grid.addWidget(box, index // self.COLUMNS, index % self.COLUMNS)

    def set_checked(self, selected: set) -> None:
        """Tick exactly the items in ``selected``."""
        for item, box in self._boxes.items():
            box.setChecked(item in selected)

    def checked(self) -> set:
        """Ticked items."""
        return {item for item, box in self._boxes.items() if box.isChecked()}


class ImageView(QLabel):
    """Fixed-size image preview with a placeholder text."""

    def __init__(self, size: QSize, placeholder: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._size = size
        self._placeholder = placeholder
        self.setFixedSize(size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { border: 1px dashed palette(mid); border-radius: 4px; }")
        self.show_file(None)

    def show_file(self, path: Path | None) -> None:
        """Display ``path`` scaled to fit, or the placeholder."""
        pixmap = QPixmap(str(path)) if path and path.is_file() else QPixmap()
        if pixmap.isNull():
            self.setPixmap(QPixmap())
            self.setText(self._placeholder)
            return
        self.setPixmap(
            pixmap.scaled(
                self._size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
