"""The three areas of the main window: systems, games and activity."""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, QItemSelectionModel, Qt, Signal, Slot
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from retroscrappy.core.library import SystemDir
from retroscrappy.core.logs import SUCCESS
from retroscrappy.gui.library_view import GameRow, GamesFilter, GamesModel

_LOG_COLOURS = {logging.WARNING: "#b26a00", logging.ERROR: "#c62828", SUCCESS: "#2e7d32"}


class EmptyState(QWidget):
    """Shown instead of the library when there is nothing to browse."""

    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._text = QLabel()
        self._text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text.setWordWrap(True)
        button = QPushButton(self.tr("Open library settings…"))
        button.clicked.connect(self.settings_requested)
        column = QVBoxLayout(self)
        column.addStretch(1)
        column.addWidget(self._text)
        column.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(2)

    def set_text(self, text: str) -> None:
        """Explain why the library is empty."""
        self._text.setText(text)


class SystemsPanel(QWidget):
    """List of detected systems; ticked ones form the default scrape scope."""

    current_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._systems: list[SystemDir] = []
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self.current_changed)
        all_button = QPushButton(self.tr("All"))
        none_button = QPushButton(self.tr("None"))
        all_button.clicked.connect(lambda: self._tick_all(True))
        none_button.clicked.connect(lambda: self._tick_all(False))

        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>{self.tr('Systems')}</b>"), 1)
        header.addWidget(all_button)
        header.addWidget(none_button)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addLayout(header)
        column.addWidget(self._list, 1)

    def set_systems(self, systems: list[SystemDir]) -> None:
        """Replace the list and select the first system."""
        self._systems = systems
        self._list.clear()
        for system in systems:
            item = QListWidgetItem(system.label)
            tooltip = f"{system.folder}\n{system.path}"
            if not system.known:
                tooltip += "\n" + self.tr("Unknown platform: name search only")
            item.setToolTip(tooltip)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._list.addItem(item)
        if systems:
            self._list.setCurrentRow(0)

    def _tick_all(self, on: bool) -> None:
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(state)

    def current(self) -> SystemDir | None:
        """System whose games are displayed."""
        row = self._list.currentRow()
        return self._systems[row] if 0 <= row < len(self._systems) else None

    def ticked(self) -> list[SystemDir]:
        """Systems with their box ticked."""
        return [
            self._systems[i]
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        ]


class GamesPanel(QWidget):
    """Games of the current system with a filter bar."""

    game_selected = Signal(object)  # GameRow | None
    visibility_requested = Signal(object, bool)  # set of rel paths, hidden

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._model = GamesModel(self)
        self._filter = GamesFilter(self)
        self._filter.setSourceModel(self._model)

        self._view = QTableView()
        self._view.setModel(self._filter)
        self._view.setSortingEnabled(True)
        self._view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._view.verticalHeader().hide()
        header = self._view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        header.setMinimumSectionSize(40)
        header.resizeSection(0, 260)
        for column in range(1, self._model.columnCount()):
            self._view.resizeColumnToContents(column)
        self._view.selectionModel().currentRowChanged.connect(self._emit_current)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._context_menu)

        search = QLineEdit()
        search.setPlaceholderText(self.tr("Filter games…"))
        search.setClearButtonEnabled(True)
        search.textChanged.connect(self._filter.setFilterFixedString)
        incomplete = QCheckBox(self.tr("Only incomplete"))
        incomplete.toggled.connect(self._filter.set_incomplete_only)
        self._count = QLabel()

        filter_row = QHBoxLayout()
        filter_row.addWidget(search, 1)
        filter_row.addWidget(incomplete)
        filter_row.addWidget(self._count)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addLayout(filter_row)
        column.addWidget(self._view, 1)

    def set_rows(self, rows: list[GameRow], keep: str = "") -> None:
        """Show ``rows`` and select the one at ``keep`` (or the first visible one)."""
        self._model.set_rows(rows)
        visible = [r for r in rows if not r.hidden]
        done = sum(1 for r in visible if r.complete)
        self._count.setText(
            self.tr("{done}/{total} complete").format(done=done, total=len(visible))
        )
        target = 0
        for proxy_row in range(self._filter.rowCount()):
            source = self._filter.mapToSource(self._filter.index(proxy_row, 0)).row()
            if keep and self._model.row_at(source).rel_path == keep:
                target = proxy_row
                break
        if self._filter.rowCount():
            index = self._filter.index(target, 0)
            self._view.selectionModel().setCurrentIndex(
                index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )
            self._view.scrollTo(index)
        else:
            self.game_selected.emit(None)

    def header_state(self) -> bytes:
        """Column widths, order and sort, for :meth:`restore_header`."""
        return bytes(self._view.horizontalHeader().saveState().data())

    def restore_header(self, state: bytes) -> None:
        """Restore what :meth:`header_state` returned (ignored if invalid)."""
        if state:
            self._view.horizontalHeader().restoreState(QByteArray(state))

    def selected_rel_paths(self) -> set[str]:
        """ROM paths of the selected rows."""
        return {
            self._model.row_at(self._filter.mapToSource(index).row()).rel_path
            for index in self._view.selectionModel().selectedRows()
        }

    @Slot()
    def _context_menu(self) -> None:
        paths = self.selected_rel_paths()
        if not paths:
            return
        menu = QMenu(self)
        hide = menu.addAction(self.tr("Hide in EmulationStation (%n)", "", len(paths)))
        show = menu.addAction(self.tr("Show in EmulationStation (%n)", "", len(paths)))
        hide.triggered.connect(lambda: self.visibility_requested.emit(paths, True))
        show.triggered.connect(lambda: self.visibility_requested.emit(paths, False))
        menu.exec(QCursor.pos())

    @Slot()
    def _emit_current(self) -> None:
        index = self._view.selectionModel().currentIndex()
        row = self._model.row_at(self._filter.mapToSource(index).row()) if index.isValid() else None
        self.game_selected.emit(row)


class ActivityPanel(QWidget):
    """Progress of the running scrape and its log."""

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._progress = QProgressBar()
        self._status = QLabel(self.tr("Ready"))
        self._cancel = QPushButton(self.tr("Cancel"))
        self._cancel.setEnabled(False)
        self._cancel.clicked.connect(self._on_cancel)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        self._log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._log.setStyleSheet("font-family: monospace;")

        row = QHBoxLayout()
        row.addWidget(self._status, 1)
        row.addWidget(self._progress, 1)
        row.addWidget(self._cancel)
        column = QVBoxLayout(self)
        column.addLayout(row)
        column.addWidget(self._log, 1)

    def set_running(self, running: bool) -> None:
        """Toggle between running and idle state."""
        self._cancel.setEnabled(running)
        if running:
            self._log.clear()
        else:
            self._progress.setRange(0, 1)
            self._progress.setValue(0)
            self._progress.setFormat("")

    def set_status(self, text: str) -> None:
        """Show a one-line status."""
        self._status.setText(text)

    @Slot()
    def _on_cancel(self) -> None:
        self._cancel.setEnabled(False)
        self._status.setText(self.tr("Cancelling…"))
        self.cancel_requested.emit()

    @Slot(str, int)
    def system_started(self, label: str, total: int) -> None:
        """A new system began."""
        self._progress.setRange(0, max(total, 1))
        self._progress.setValue(0)
        self._progress.setFormat(f"%v / {total}")
        self._status.setText(label)

    @Slot(int, int, str)
    def game_started(self, index: int, _total: int, name: str) -> None:
        """A game began."""
        self._progress.setValue(index - 1)
        self._status.setText(name)

    @Slot(object)
    def game_finished(self, _outcome: object) -> None:
        """A game ended."""
        self._progress.setValue(self._progress.value() + 1)

    @Slot(int, str)
    def append_log(self, level: int, text: str) -> None:
        """Add a log line, coloured by level."""
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        colour = _LOG_COLOURS.get(level)
        style = f' style="color:{colour}"' if colour else ""
        self._log.appendHtml(f"<span{style}>{safe}</span>")
