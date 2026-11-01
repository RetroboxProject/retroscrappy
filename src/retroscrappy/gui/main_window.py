"""Main window.

Layout, from general to specific::

    ┌ toolbar: Scrape… · Rescan · Settings ──────── frontend · ROM folder ┐
    │ Systems (tick to include) │ Games of the system │ Selected game      │
    ├ Activity: status · progress · Cancel · log ─────────────────────────┤

Everything that configures the program lives in the Settings window;
everything about one run lives in the Scrape dialog.
"""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from retroscrappy import __version__
from retroscrappy.core import paths
from retroscrappy.core.frontends import get_frontend
from retroscrappy.core.library import discover_systems
from retroscrappy.core.logs import TagFormatter, get_logger
from retroscrappy.core.platforms import load_registry
from retroscrappy.core.settings import Settings, load_settings, save_settings
from retroscrappy.gui.bridge import PendingQuestion, QtLogHandler, ScrapeWorker
from retroscrappy.gui.dialogs.pickers import pick_match, pick_media
from retroscrappy.gui.dialogs.scrape_dialog import Scope, ScopeCounts, ScrapeChoice, ScrapeDialog
from retroscrappy.gui.dialogs.settings_dialog import SettingsDialog
from retroscrappy.gui.library_view import GameDetail, load_rows
from retroscrappy.gui.panels import ActivityPanel, GamesPanel, SystemsPanel
from retroscrappy.pipeline.interaction import RunSummary
from retroscrappy.pipeline.scraper import ScrapeRequest

_log = get_logger("gui")
_PAGE_EMPTY, _PAGE_LIBRARY = 0, 1


class MainWindow(QMainWindow):
    """Library browser plus scrape controls."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Retroscrappy {__version__}")
        self.resize(1280, 800)
        self._settings = load_settings()
        self._worker: ScrapeWorker | None = None

        self._systems = SystemsPanel()
        self._games = GamesPanel()
        self._activity = ActivityPanel()
        self._empty_text = QLabel()
        self._library_label = QLabel()
        self._stack = QStackedWidget()
        self._scrape_action = QAction(self._icon("SP_MediaPlay"), self.tr("Scrape…"), self)

        self._log_handler = QtLogHandler()
        self._log_handler.setFormatter(TagFormatter(colour=False))
        self._log_handler.emitter.record.connect(self._activity.append_log)
        get_logger().addHandler(self._log_handler)

        self._systems.current_changed.connect(self._load_current_system)
        detail = GameDetail()
        self._games.game_selected.connect(detail.show_row)
        self._activity.cancel_requested.connect(self._cancel_scrape)

        self._build_toolbar()
        self._build_central(detail)
        self._build_activity_dock()
        self._rescan()

    # ── Construction ─────────────────────────────────────────────────────

    def _icon(self, name: str) -> QIcon:
        return self.style().standardIcon(getattr(QStyle.StandardPixmap, name))

    def _build_toolbar(self) -> None:
        self._scrape_action.setShortcut(QKeySequence("Ctrl+R"))
        self._scrape_action.setToolTip(self.tr("Scrape the ticked systems or the selected games"))
        self._scrape_action.triggered.connect(self._open_scrape_dialog)
        rescan = QAction(self._icon("SP_BrowserReload"), self.tr("Rescan"), self)
        rescan.setShortcut(QKeySequence.StandardKey.Refresh)
        rescan.triggered.connect(self._rescan)
        settings = QAction(self._icon("SP_FileDialogDetailedView"), self.tr("Settings"), self)
        settings.setShortcut(QKeySequence.StandardKey.Preferences)
        settings.triggered.connect(self._open_settings_window)

        toolbar = QToolBar(self.tr("Main"))
        toolbar.setObjectName("main-toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addAction(self._scrape_action)
        toolbar.addSeparator()
        toolbar.addAction(rescan)
        toolbar.addAction(settings)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self._library_label.setStyleSheet("color: palette(placeholder-text); padding-right: 8px;")
        toolbar.addWidget(self._library_label)
        self.addToolBar(toolbar)

    def _build_central(self, detail: GameDetail) -> None:
        empty = QWidget()
        column = QVBoxLayout(empty)
        self._empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_text.setWordWrap(True)
        button = QPushButton(self.tr("Open library settings…"))
        button.clicked.connect(lambda: self._open_settings(page=0))
        column.addStretch(1)
        column.addWidget(self._empty_text)
        column.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(2)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._systems)
        splitter.addWidget(self._games)
        splitter.addWidget(detail)
        splitter.setSizes([230, 560, 460])
        splitter.setChildrenCollapsible(False)

        self._stack.addWidget(empty)
        self._stack.addWidget(splitter)
        self.setCentralWidget(self._stack)

    def _build_activity_dock(self) -> None:
        dock = QDockWidget(self.tr("Activity"), self)
        dock.setObjectName("activity")
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        dock.setWidget(self._activity)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [200], Qt.Orientation.Vertical)

    # ── Library ──────────────────────────────────────────────────────────

    def _show_empty(self, text: str) -> None:
        self._systems.set_systems([])
        self._games.set_rows([])
        self._empty_text.setText(text)
        self._stack.setCurrentIndex(_PAGE_EMPTY)
        self._scrape_action.setEnabled(False)

    @Slot()
    def _rescan(self) -> None:
        frontend = get_frontend(self._settings.library.frontend)
        roms = self._settings.library.roms_path or frontend.default_roms_dir()
        es_file = self._settings.library.es_systems_path or frontend.default_es_systems()
        if roms is None or not roms.is_dir():
            self._library_label.setText(frontend.label)
            self._show_empty(
                self.tr("No ROM folder yet.\nChoose your {frontend} roms/ folder to start.").format(
                    frontend=frontend.label
                )
            )
            return
        self._library_label.setText(f"{frontend.label} · {roms}")
        systems = discover_systems(roms, load_registry(paths.user_platforms_file()), es_file)
        if not systems:
            self._show_empty(self.tr("No systems found in {path}").format(path=roms))
            return
        self._stack.setCurrentIndex(_PAGE_LIBRARY)
        self._scrape_action.setEnabled(not self._busy)
        self._systems.set_systems(systems)

    @Slot()
    def _load_current_system(self) -> None:
        system = self._systems.current()
        self._games.set_rows(load_rows(system) if system else [])

    # ── Settings ─────────────────────────────────────────────────────────

    @Slot()
    def _open_settings_window(self) -> None:
        self._open_settings()

    def _open_settings(self, page: int = 0) -> None:
        dialog = SettingsDialog(self._settings, self, page=page)
        dialog.applied.connect(self._apply_settings)
        dialog.exec()

    @Slot(object)
    def _apply_settings(self, settings: Settings) -> None:
        library_changed = settings.library != self._settings.library
        self._settings = settings
        try:
            save_settings(settings)
        except OSError as exc:
            _log.error("Cannot save settings: %s", exc)
        if library_changed:
            self._rescan()

    # ── Scraping ─────────────────────────────────────────────────────────

    @property
    def _busy(self) -> bool:
        return self._worker is not None and self._worker.running

    @Slot()
    def _open_scrape_dialog(self) -> None:
        if self._busy:
            return
        current = self._systems.current()
        selected = self._games.selected_rel_paths()
        ticked = self._systems.ticked()
        counts = ScopeCounts(
            checked_systems=len(ticked),
            current_system=current.label if current else "",
            selected_games=len(selected),
        )
        if ticked:
            preferred = Scope.CHECKED_SYSTEMS
        elif len(selected) > 1:
            preferred = Scope.SELECTED_GAMES
        else:
            preferred = Scope.CURRENT_SYSTEM
        dialog = ScrapeDialog(self._settings.scrape, counts, preferred, self)
        if dialog.exec() != ScrapeDialog.DialogCode.Accepted:
            return
        choice = dialog.choice()
        if not choice.fields and not choice.media:
            _log.warning("Nothing selected to scrape")
            return
        if choice.remember:
            self._remember_choice(choice)

        if choice.scope == Scope.CHECKED_SYSTEMS:
            systems = ticked
        else:
            systems = [current] if current else []
        request = ScrapeRequest(
            systems=systems,
            fields=choice.fields,
            media=choice.media,
            mode=choice.mode,
            overwrite=choice.overwrite,
            add_missing_roms=choice.add_missing_roms,
        )
        if choice.scope == Scope.SELECTED_GAMES and current:
            request.only = {current.folder: selected}
        self._start_worker(request)

    def _remember_choice(self, choice: ScrapeChoice) -> None:
        updated = copy.deepcopy(self._settings)
        defaults = updated.scrape
        defaults.fields, defaults.media = set(choice.fields), set(choice.media)
        defaults.mode, defaults.overwrite = choice.mode, choice.overwrite
        defaults.add_missing_roms = choice.add_missing_roms
        self._apply_settings(updated)

    def _start_worker(self, request: ScrapeRequest) -> None:
        worker = ScrapeWorker(copy.deepcopy(self._settings), self)
        worker.system_began.connect(self._activity.system_started)
        worker.game_began.connect(self._activity.game_started)
        worker.game_done.connect(self._activity.game_finished)
        worker.run_done.connect(self._on_scrape_finished)
        worker.interaction.match_requested.connect(self._ask_match)
        worker.interaction.media_requested.connect(self._ask_media)
        self._worker = worker
        self._scrape_action.setEnabled(False)
        self._activity.set_running(True)
        worker.start(request)

    @Slot()
    def _cancel_scrape(self) -> None:
        if self._worker:
            self._worker.cancel()

    @Slot(object)
    def _on_scrape_finished(self, summary: RunSummary) -> None:
        self._activity.set_running(False)
        self._scrape_action.setEnabled(self._stack.currentIndex() == _PAGE_LIBRARY)
        text = self.tr("{updated} updated · {unchanged} unchanged · {failed} failed").format(
            updated=summary.updated, unchanged=summary.unchanged, failed=summary.failed
        )
        self._activity.set_status(self.tr("Cancelled — ") + text if summary.cancelled else text)
        self._load_current_system()

    @Slot(object)
    def _ask_match(self, question: PendingQuestion) -> None:
        question.reply(pick_match(self, question.query, question.provider, question.options))

    @Slot(object)
    def _ask_media(self, question: PendingQuestion) -> None:
        if question.kind is None:
            question.reply(None)
            return
        question.reply(
            pick_media(self, question.query, question.kind, question.provider, question.options)
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # pylint: disable=invalid-name
        """Stop any running scrape before closing."""
        if self._worker and self._worker.running:
            self._worker.cancel()
        get_logger().removeHandler(self._log_handler)
        super().closeEvent(event)
