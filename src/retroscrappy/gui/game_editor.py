"""Editable panel for one game: media slots and text fields.

- Clicking a media slot opens a menu: fetch from a source, choose a file
  from the computer, open or remove it. Media changes are written at once.
- Every text field can be typed in or filled from a source with the small
  button beside it. Text changes are written when *Save* is pressed.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QCursor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.library import SystemDir
from retroscrappy.core.settings import Settings
from retroscrappy.gui.bridge import BackgroundTask, PendingQuestion, QtInteraction
from retroscrappy.gui.dialogs.pickers import pick_match, pick_media
from retroscrappy.gui.labels import field_label, item_label
from retroscrappy.gui.library_view import GameRow
from retroscrappy.gui.widgets import MediaSlot
from retroscrappy.pipeline.media import import_media_file, remove_media
from retroscrappy.pipeline.single import NO_PREVIEW, ItemFetcher, edit_entry
from retroscrappy.providers.base import GameQuery, MediaCandidate
from retroscrappy.providers.registry import PROVIDER_LABELS, available_providers_for

#: Preview size of every media slot.
_SLOT_SIZES: dict[MediaKind, QSize] = {
    MediaKind.THUMBNAIL: QSize(110, 154),
    MediaKind.BOXBACK: QSize(110, 154),
    MediaKind.MARQUEE: QSize(170, 56),
    MediaKind.IMAGE: QSize(170, 96),
    MediaKind.TITLESHOT: QSize(110, 82),
    MediaKind.FANART: QSize(110, 82),
    MediaKind.VIDEO: QSize(170, 30),
    MediaKind.MANUAL: QSize(170, 30),
}
#: Grid layout: one entry per cell, several kinds stack vertically in a cell.
_SLOT_GRID: tuple[tuple[tuple[MediaKind, ...], ...], ...] = (
    ((MediaKind.THUMBNAIL,), (MediaKind.BOXBACK,), (MediaKind.MARQUEE, MediaKind.IMAGE)),
    ((MediaKind.TITLESHOT,), (MediaKind.FANART,), (MediaKind.VIDEO, MediaKind.MANUAL)),
)
_FILE_FILTERS = {
    MediaKind.VIDEO: "Videos (*.mp4 *.mkv *.webm *.avi)",
    MediaKind.MANUAL: "Manuals (*.pdf *.cbz)",
}
_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.gif)"
_TEXT_FIELDS = (
    Field.GENRE,
    Field.DEVELOPER,
    Field.PUBLISHER,
    Field.RELEASEDATE,
    Field.PLAYERS,
    Field.RATING,
    Field.FAMILY,
)


def date_to_display(value: str) -> str:
    """``19921121T000000`` → ``1992-11-21``."""
    digits = value[:8]
    if len(digits) == 8 and digits.isdigit():
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return value


def date_from_display(value: str) -> str:
    """``1992``, ``1992-11`` or ``1992-11-21`` → ``19921121T000000``; else unchanged."""
    parts = value.strip().split("-")
    if not parts[0].isdigit() or len(parts[0]) != 4 or len(parts) > 3:
        return value.strip()
    if not all(p.isdigit() for p in parts[1:]):
        return value.strip()
    year, month, day = (parts + ["01", "01"])[:3]
    return f"{year}{month.zfill(2)}{day.zfill(2)}T000000"


def _set_text(edit: QLineEdit | QPlainTextEdit, value: str) -> None:
    if isinstance(edit, QPlainTextEdit):
        edit.setPlainText(value)
    else:
        edit.setText(value)


class TextFields(QWidget):
    """Name, metadata fields and description with fetch buttons and Save/Revert."""

    fetch_requested = Signal(str, object)  # provider key, set[Field]
    save_requested = Signal()
    revert_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._edits: dict[Field, QLineEdit | QPlainTextEdit] = {}
        self._buttons: dict[Field, QToolButton] = {}
        self._dirty = False
        self._loading = False

        name = QLineEdit()
        bold = QFont()
        bold.setPointSizeF(bold.pointSizeF() * 1.3)
        bold.setBold(True)
        name.setFont(bold)
        name_row = self._register(Field.NAME, name)

        form = QFormLayout()
        for fld in _TEXT_FIELDS:
            edit = QLineEdit()
            if fld is Field.RELEASEDATE:
                edit.setPlaceholderText("YYYY-MM-DD")
            elif fld is Field.RATING:
                edit.setPlaceholderText("0.0 – 1.0")
            form.addRow(field_label(fld) + ":", self._register(fld, edit))
        desc = QPlainTextEdit()
        desc.setMinimumHeight(90)
        desc_row = self._register(Field.DESC, desc)

        self._fetch_all = QToolButton()
        self._fetch_all.setText(self.tr("Fetch all text"))
        self._fetch_all.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._save = QPushButton(self.tr("Save"))
        self._save.clicked.connect(self.save_requested)
        revert = QPushButton(self.tr("Revert"))
        revert.clicked.connect(self.revert_requested)
        self._save.setEnabled(False)
        buttons = QHBoxLayout()
        buttons.addWidget(self._fetch_all)
        buttons.addStretch(1)
        buttons.addWidget(revert)
        buttons.addWidget(self._save)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addLayout(name_row)
        column.addLayout(form)
        column.addWidget(QLabel(field_label(Field.DESC) + ":"))
        column.addLayout(desc_row)
        column.addLayout(buttons)

    def _register(self, fld: Field, edit: QLineEdit | QPlainTextEdit) -> QHBoxLayout:
        """Track ``edit`` and return it in a row with its fetch button."""
        self._edits[fld] = edit
        edit.textChanged.connect(self._on_edited)
        button = QToolButton()
        button.setText("⟳")
        button.setAutoRaise(True)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._buttons[fld] = button
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit, 1)
        row.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        return row

    @Slot()
    def _on_edited(self) -> None:
        if not self._loading:
            self._dirty = True
            self._save.setEnabled(True)

    @property
    def dirty(self) -> bool:
        """True if there are unsaved edits."""
        return self._dirty

    def set_sources(self, settings: Settings) -> None:
        """Rebuild the fetch menus from the configured providers."""
        everything: dict[str, set[Field]] = {}
        for fld, button in self._buttons.items():
            menu = QMenu(button)
            keys = available_providers_for(fld, settings)
            for key in keys:
                everything.setdefault(key, set()).add(fld)
                action = menu.addAction(
                    self.tr("From {source}").format(source=PROVIDER_LABELS[key])
                )
                action.triggered.connect(partial(self.fetch_requested.emit, key, {fld}))
            button.setMenu(menu)
            button.setEnabled(bool(keys))
            button.setToolTip(
                self.tr("Fetch {field} from a source").format(field=field_label(fld))
                if keys
                else self.tr("No configured source offers this")
            )
        menu = QMenu(self._fetch_all)
        for key, fields in everything.items():
            action = menu.addAction(self.tr("From {source}").format(source=PROVIDER_LABELS[key]))
            action.triggered.connect(partial(self.fetch_requested.emit, key, set(fields)))
        self._fetch_all.setMenu(menu)
        self._fetch_all.setEnabled(bool(everything))

    def load(self, tags: dict[str, str], fallback_name: str) -> None:
        """Show stored values and clear the dirty flag."""
        self._loading = True
        for fld, edit in self._edits.items():
            value = tags.get(fld.value, "")
            if fld is Field.NAME and not value:
                value = fallback_name
            if fld is Field.RELEASEDATE:
                value = date_to_display(value)
            _set_text(edit, value)
        self._loading = False
        self._dirty = False
        self._save.setEnabled(False)

    def put(self, values: dict[Field, str]) -> None:
        """Fill fields with fetched values (marks the form dirty)."""
        for fld, value in values.items():
            edit = self._edits.get(fld)
            if edit is None:
                continue
            if fld is Field.RELEASEDATE:
                value = date_to_display(value)
            _set_text(edit, value)

    def values(self) -> dict[Field, str]:
        """Current values in gamelist format."""
        result = {}
        for fld, edit in self._edits.items():
            text = edit.toPlainText() if isinstance(edit, QPlainTextEdit) else edit.text()
            text = text.strip()
            result[fld] = date_from_display(text) if fld is Field.RELEASEDATE else text
        return result

    def name(self) -> str:
        """Current name text."""
        return self.values()[Field.NAME]


class GameEditor(QScrollArea):
    """Media and metadata editor for the selected game."""

    changed = Signal(str)  # rel_path whose gamelist entry or media changed

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._settings = Settings()
        self._target: tuple[SystemDir, GameRow] | None = None
        self._tasks: set[BackgroundTask] = set()
        cancel = threading.Event()
        self._interaction = QtInteraction(cancel, self)
        self._interaction.match_requested.connect(self._ask_match)
        self._fetcher = ItemFetcher(self._settings, self._interaction)

        self._path = QLabel()
        self._path.setStyleSheet("color: palette(placeholder-text);")
        self._path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._slots = {
            kind: MediaSlot(item_label(kind), size, preview=kind not in NO_PREVIEW)
            for kind, size in _SLOT_SIZES.items()
        }
        self._text = TextFields()
        self._text.fetch_requested.connect(self._fetch_text)
        self._text.save_requested.connect(self._save_text)
        self._text.revert_requested.connect(self._revert_text)

        grid = QGridLayout()
        for row, cells in enumerate(_SLOT_GRID):
            for column, kinds in enumerate(cells):
                cell = QVBoxLayout()
                for kind in kinds:
                    self._slots[kind].clicked.connect(partial(self._media_menu, kind))
                    cell.addWidget(self._slots[kind])
                cell.addStretch(1)
                grid.addLayout(cell, row, column)
        grid.setColumnStretch(len(_SLOT_GRID[0]), 1)

        body = QWidget()
        column_layout = QVBoxLayout(body)
        column_layout.addWidget(self._path)
        column_layout.addLayout(grid)
        column_layout.addWidget(self._status)
        column_layout.addWidget(self._text)
        column_layout.addStretch(1)
        self.setWidget(body)
        self.set_game(None, None)

    # ── Context ──────────────────────────────────────────────────────────

    def set_settings(self, settings: Settings) -> None:
        """Use new settings (sources and credentials)."""
        self._settings = settings
        self._fetcher = ItemFetcher(settings, self._interaction)
        self._text.set_sources(settings)

    def set_game(self, system: SystemDir | None, row: GameRow | None) -> None:
        """Show ``row``; unsaved text edits of the same game are kept."""
        same = bool(self._target and row and self._target[1].rel_path == row.rel_path and system)
        if self._text.dirty and not same and self._target is not None:
            self._offer_save()
        self._target = (system, row) if system and row else None
        self.widget().setEnabled(self._target is not None)
        self._path.setText(row.rel_path if row else self.tr("Select a game"))
        media = row.media if row else {}
        for kind, slot in self._slots.items():
            slot.show_file(media.get(kind))
        if not same or not self._text.dirty:
            self._text.load(row.tags if row else {}, row.name if row else "")
        if not same:
            self._status.clear()

    def _offer_save(self) -> None:
        answer = QMessageBox.question(
            self,
            self.tr("Unsaved changes"),
            self.tr("Save the text changes made to the previous game?"),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            self._save_text()

    def _query(self) -> GameQuery | None:
        if self._target is None:
            return None
        system, row = self._target
        return GameQuery(
            platform=system.platform,
            system_dir=system.path,
            rel_path=row.rel_path,
            name=self._text.name() or row.name,
        )

    # ── Background work ──────────────────────────────────────────────────

    def _run(self, message: str, work: Callable[[], Any], on_done: Callable[[Any], None]) -> None:
        task = BackgroundTask(work, self)
        self._tasks.add(task)
        self.widget().setEnabled(False)
        self._status.setText(message)

        def finish() -> None:
            self._tasks.discard(task)
            self.widget().setEnabled(self._target is not None)

        task.succeeded.connect(lambda result: (finish(), on_done(result)))
        task.failed.connect(lambda error: (finish(), self._status.setText(f"⚠ {error}")))
        task.start()

    @Slot(object)
    def _ask_match(self, question: PendingQuestion) -> None:
        question.reply(pick_match(self, question.query, question.provider, question.options))

    # ── Text ─────────────────────────────────────────────────────────────

    def _fetch_text(self, key: str, fields: set[Field]) -> None:
        query = self._query()
        if query is None:
            return
        source = PROVIDER_LABELS[key]
        fetcher = self._fetcher

        def done(values: dict[Field, str]) -> None:
            if not values:
                self._status.setText(
                    self.tr("{source} has nothing for this.").format(source=source)
                )
                return
            self._text.put(values)
            labels = ", ".join(field_label(f) for f in values)
            self._status.setText(
                self.tr("Filled from {source}: {fields}. Press Save to keep them.").format(
                    source=source, fields=labels
                )
            )

        self._run(
            self.tr("Asking {source}…").format(source=source),
            lambda: fetcher.fetch_fields(key, query, fields),
            done,
        )

    @Slot()
    def _save_text(self) -> None:
        if self._target is None:
            return
        system, row = self._target
        values = self._text.values()

        def apply(entry: Any) -> None:
            for fld, value in values.items():
                if value:
                    entry.set(fld.value, value)
                elif fld is not Field.NAME:
                    entry.remove(fld.value)

        try:
            edit_entry(system, row.rel_path, apply)
        except OSError as exc:
            self._status.setText(f"⚠ {exc}")
            return
        self._text.load({f.value: v for f, v in values.items()}, row.name)
        self._status.setText(self.tr("Saved."))
        self.changed.emit(row.rel_path)

    @Slot()
    def _revert_text(self) -> None:
        if self._target is not None:
            self._text.load(self._target[1].tags, self._target[1].name)

    # ── Media ────────────────────────────────────────────────────────────

    def _media_menu(self, kind: MediaKind) -> None:
        if self._target is None:
            return
        present = kind in self._target[1].media
        menu = QMenu(self)
        sources = available_providers_for(kind, self._settings)
        for key in sources:
            action = menu.addAction(
                self.tr("Fetch from {source}").format(source=PROVIDER_LABELS[key])
            )
            action.triggered.connect(partial(self._fetch_media, key, kind))
        if not sources:
            menu.addAction(self.tr("No configured source offers this")).setEnabled(False)
        menu.addSeparator()
        menu.addAction(self.tr("Choose file…")).triggered.connect(partial(self._import_media, kind))
        if present:
            menu.addAction(self.tr("Open")).triggered.connect(partial(self._open_media, kind))
            menu.addAction(self.tr("Remove")).triggered.connect(partial(self._remove_media, kind))
        menu.exec(QCursor.pos())

    def _fetch_media(self, key: str, kind: MediaKind) -> None:
        query = self._query()
        if query is None or self._target is None:
            return
        system, row = self._target
        source = PROVIDER_LABELS[key]
        fetcher = self._fetcher

        def store(candidate: MediaCandidate) -> None:
            self._run(
                self.tr("Downloading…"),
                lambda: fetcher.store_media(system, row.rel_path, kind, candidate),
                lambda _path: self._media_changed(row.rel_path, kind),
            )

        def chosen(candidates: list[MediaCandidate]) -> None:
            if not candidates:
                self._status.setText(
                    self.tr("{source} has no {item} for this game.").format(
                        source=source, item=item_label(kind)
                    )
                )
                return
            if kind in NO_PREVIEW or len(candidates) == 1:
                store(candidates[0])
                return
            self._status.clear()
            picked = pick_media(self, query, kind, source, candidates)
            if picked is not None:
                store(picked)

        self._run(
            self.tr("Asking {source}…").format(source=source),
            lambda: fetcher.fetch_media(key, query, kind),
            chosen,
        )

    def _import_media(self, kind: MediaKind) -> None:
        if self._target is None:
            return
        system, row = self._target
        chosen, _ = QFileDialog.getOpenFileName(
            self, item_label(kind), str(Path.home()), _FILE_FILTERS.get(kind, _IMAGE_FILTER)
        )
        if not chosen:
            return
        source = Path(chosen)
        self._run(
            self.tr("Copying…"),
            lambda: edit_entry(
                system, row.rel_path, lambda e: import_media_file(system.path, e, kind, source)
            ),
            lambda _path: self._media_changed(row.rel_path, kind),
        )

    def _open_media(self, kind: MediaKind) -> None:
        if self._target is not None and kind in self._target[1].media:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._target[1].media[kind])))

    def _remove_media(self, kind: MediaKind) -> None:
        if self._target is None:
            return
        system, row = self._target
        answer = QMessageBox.question(
            self,
            self.tr("Remove"),
            self.tr("Delete the {item} of this game?").format(item=item_label(kind)),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            edit_entry(system, row.rel_path, lambda e: remove_media(system.path, e, kind))
        except OSError as exc:
            self._status.setText(f"⚠ {exc}")
            return
        self._media_changed(row.rel_path, kind)

    def _media_changed(self, rel_path: str, kind: MediaKind) -> None:
        self._status.setText(self.tr("{item} updated.").format(item=item_label(kind)))
        self.changed.emit(rel_path)
