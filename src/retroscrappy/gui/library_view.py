"""Library browsing widgets: games table and game detail panel."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSize,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.library import SystemDir, find_roms, resolve_media_path
from retroscrappy.core.names import title_from_filename
from retroscrappy.gui.labels import field_label, media_label
from retroscrappy.gui.widgets import ImageView

#: Indicator columns shown after the name.
INDICATORS: tuple[Field | MediaKind, ...] = (
    Field.DESC,
    MediaKind.IMAGE,
    MediaKind.THUMBNAIL,
    MediaKind.MARQUEE,
    MediaKind.VIDEO,
)
_DETAIL_FIELDS = (
    Field.GENRE,
    Field.DEVELOPER,
    Field.PUBLISHER,
    Field.RELEASEDATE,
    Field.PLAYERS,
    Field.RATING,
    Field.FAMILY,
)
_ModelIndex = QModelIndex | QPersistentModelIndex


@dataclass
class GameRow:
    """One ROM as shown in the table."""

    rel_path: str
    name: str
    in_gamelist: bool
    tags: dict[str, str] = field(default_factory=dict)
    media: dict[MediaKind, Path] = field(default_factory=dict)

    def has(self, item: Field | MediaKind) -> bool:
        """Whether the field is filled or the media file exists."""
        if isinstance(item, MediaKind):
            return item in self.media
        return bool(self.tags.get(item.value))

    @property
    def complete(self) -> bool:
        """All indicator items present."""
        return all(self.has(i) for i in INDICATORS)


def load_rows(system: SystemDir) -> list[GameRow]:
    """Gamelist entries plus ROMs on disk that are not listed yet."""
    rows: list[GameRow] = []
    gamelist = system.gamelist()
    for entry in gamelist.games:
        if not entry.path:
            continue
        media = {}
        for kind in MediaKind:
            path = resolve_media_path(system.path, entry.get(kind.value))
            if path and path.exists():
                media[kind] = path
        rows.append(GameRow(entry.path, entry.name or entry.stem, True, entry.tags(), media))
    for rel in find_roms(system):
        if gamelist.find(rel) is None:
            rows.append(GameRow(rel, title_from_filename(Path(rel).stem), False))
    rows.sort(key=lambda r: r.name.lower())
    return rows


class GamesModel(QAbstractTableModel):
    """Table model over :class:`GameRow` objects."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows: list[GameRow] = []

    def set_rows(self, rows: list[GameRow]) -> None:
        """Replace all rows."""
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_at(self, row: int) -> GameRow:
        """Row object at source row ``row``."""
        return self._rows[row]

    def rowCount(self, parent: _ModelIndex = QModelIndex()) -> int:  # pylint: disable=invalid-name
        """Qt override."""
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(
        self, parent: _ModelIndex = QModelIndex()
    ) -> int:  # pylint: disable=invalid-name
        """Qt override."""
        return 0 if parent.isValid() else 1 + len(INDICATORS)

    def headerData(  # pylint: disable=invalid-name
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """Qt override."""
        if orientation != Qt.Orientation.Horizontal or role != Qt.ItemDataRole.DisplayRole:
            return None
        if section == 0:
            return self.tr("Game")
        item = INDICATORS[section - 1]
        return field_label(item) if isinstance(item, Field) else media_label(item)

    def data(self, index: _ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Qt override."""
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = index.column()
        if column == 0:
            return self._name_data(row, role)
        present = row.has(INDICATORS[column - 1])
        if role == Qt.ItemDataRole.DisplayRole:
            return "✔" if present else "·"
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        if role == Qt.ItemDataRole.UserRole:
            return int(present)
        return None

    def _name_data(self, row: GameRow, role: int) -> Any:
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.UserRole):
            return row.name
        if role == Qt.ItemDataRole.ToolTipRole:
            note = "" if row.in_gamelist else "\n" + self.tr("Not in gamelist.xml yet")
            return row.rel_path + note
        if role == Qt.ItemDataRole.FontRole and not row.in_gamelist:
            font = QFont()
            font.setItalic(True)
            return font
        return None


class GamesFilter(QSortFilterProxyModel):
    """Filters by name text and optionally hides complete games."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._incomplete_only = False
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(0)
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def set_incomplete_only(self, value: bool) -> None:
        """Toggle hiding of complete games."""
        self._incomplete_only = value
        self.invalidateFilter()

    def filterAcceptsRow(  # pylint: disable=invalid-name
        self, source_row: int, source_parent: _ModelIndex
    ) -> bool:
        """Qt override."""
        if not super().filterAcceptsRow(source_row, source_parent):
            return False
        model = self.sourceModel()
        if self._incomplete_only and isinstance(model, GamesModel):
            return not model.row_at(source_row).complete
        return True


class GameDetail(QScrollArea):
    """Media previews and metadata of the selected game."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        column = QVBoxLayout(body)
        column.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-size: 14pt; font-weight: 600;")
        self._path = QLabel()
        self._path.setStyleSheet("color: palette(placeholder-text);")
        self._path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(self._title)
        column.addWidget(self._path)

        self._thumb = ImageView(QSize(150, 210), self.tr("No box art"))
        self._marquee = ImageView(QSize(220, 80), self.tr("No logo"))
        self._image = ImageView(QSize(220, 124), self.tr("No screenshot"))
        pictures = QHBoxLayout()
        pictures.addWidget(self._thumb)
        right = QVBoxLayout()
        right.addWidget(self._marquee)
        right.addWidget(self._image)
        pictures.addLayout(right)
        pictures.addStretch(1)
        column.addLayout(pictures)

        self._meta = QFormLayout()
        self._meta_labels: dict[Field, QLabel] = {}
        for fld in _DETAIL_FIELDS:
            label = QLabel()
            label.setWordWrap(True)
            self._meta_labels[fld] = label
            self._meta.addRow(field_label(fld) + ":", label)
        column.addLayout(self._meta)
        self._desc = QTextBrowser()
        self._desc.setMinimumHeight(120)
        column.addWidget(self._desc, 1)
        self.setWidget(body)
        self.show_row(None)

    def show_row(self, row: GameRow | None) -> None:
        """Display ``row`` or an empty state."""
        if row is None:
            self._title.setText(self.tr("Select a game"))
            self._path.clear()
        else:
            self._title.setText(row.name)
            self._path.setText(row.rel_path)
        media = row.media if row else {}
        self._thumb.show_file(media.get(MediaKind.THUMBNAIL))
        self._marquee.show_file(media.get(MediaKind.MARQUEE))
        self._image.show_file(media.get(MediaKind.IMAGE))
        tags = row.tags if row else {}
        for fld, label in self._meta_labels.items():
            value = tags.get(fld.value, "")
            if fld is Field.RELEASEDATE and len(value) >= 8:
                value = f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
            label.setText(value or "—")
        self._desc.setPlainText(tags.get(Field.DESC.value, ""))
