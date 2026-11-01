"""*Scrape* dialog: choose scope, what to fetch and how, then start."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.settings import MatchMode, ScrapeDefaults
from retroscrappy.gui.labels import mode_help, mode_label
from retroscrappy.gui.widgets import ItemChecklist


class Scope:
    """Which games a run covers."""

    CHECKED_SYSTEMS = "checked"
    CURRENT_SYSTEM = "current"
    SELECTED_GAMES = "selected"


@dataclass
class ScrapeChoice:
    """What the user picked in the dialog."""

    scope: str
    fields: set[Field]
    media: set[MediaKind]
    mode: MatchMode
    overwrite: bool
    add_missing_roms: bool
    remember: bool


@dataclass
class ScopeCounts:
    """Numbers shown next to each scope option (0 disables it)."""

    checked_systems: int
    current_system: str
    selected_games: int


class ScrapeDialog(QDialog):
    """Collects a :class:`ScrapeChoice`."""

    def __init__(
        self,
        defaults: ScrapeDefaults,
        counts: ScopeCounts,
        preferred_scope: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Scrape"))
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_scope(counts, preferred_scope))
        layout.addWidget(self._build_what(defaults))
        layout.addWidget(self._build_behaviour(defaults))

        buttons = QDialogButtonBox()
        start = buttons.addButton(self.tr("Start"), QDialogButtonBox.ButtonRole.AcceptRole)
        start.setDefault(True)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Sections ─────────────────────────────────────────────────────────

    def _build_scope(self, counts: ScopeCounts, preferred: str) -> QGroupBox:
        box = QGroupBox(self.tr("1. Games"))
        column = QVBoxLayout(box)
        self._scope_group = QButtonGroup(self)
        options = [
            (
                Scope.SELECTED_GAMES,
                self.tr("Selected games (%n)", "", counts.selected_games),
                counts.selected_games > 0,
            ),
            (
                Scope.CURRENT_SYSTEM,
                self.tr("Current system: {name}").format(name=counts.current_system or "—"),
                bool(counts.current_system),
            ),
            (
                Scope.CHECKED_SYSTEMS,
                self.tr("Ticked systems (%n)", "", counts.checked_systems),
                counts.checked_systems > 0,
            ),
        ]
        self._scope_buttons: dict[str, QRadioButton] = {}
        for key, text, enabled in options:
            button = QRadioButton(text)
            button.setEnabled(enabled)
            self._scope_group.addButton(button)
            self._scope_buttons[key] = button
            column.addWidget(button)
        enabled_keys = [k for k, _, on in options if on]
        chosen = (
            preferred if preferred in enabled_keys else (enabled_keys or [Scope.CURRENT_SYSTEM])[0]
        )
        self._scope_buttons[chosen].setChecked(True)
        return box

    def _build_what(self, defaults: ScrapeDefaults) -> QGroupBox:
        box = QGroupBox(self.tr("2. What to fetch"))
        row = QHBoxLayout(box)
        text_box = QGroupBox(self.tr("Text"))
        self._fields = ItemChecklist(list(Field))
        self._fields.set_checked(defaults.fields)
        QVBoxLayout(text_box).addWidget(self._fields)
        media_box = QGroupBox(self.tr("Media"))
        self._media = ItemChecklist(list(MediaKind))
        self._media.set_checked(defaults.media)
        QVBoxLayout(media_box).addWidget(self._media)
        row.addWidget(text_box)
        row.addWidget(media_box)
        return box

    def _build_behaviour(self, defaults: ScrapeDefaults) -> QGroupBox:
        box = QGroupBox(self.tr("3. How"))
        form = QFormLayout(box)
        self._mode = QComboBox()
        for mode in MatchMode:
            self._mode.addItem(mode_label(mode), mode)
        self._mode.setCurrentIndex(list(MatchMode).index(defaults.mode))
        self._mode_help = QLabel()
        self._mode_help.setWordWrap(True)
        self._mode_help.setStyleSheet("color: palette(placeholder-text);")
        self._mode.currentIndexChanged.connect(self._update_mode_help)
        self._update_mode_help()
        form.addRow(self.tr("Questions:"), self._mode)
        form.addRow("", self._mode_help)

        self._overwrite = QCheckBox(self.tr("Replace data that is already there"))
        self._overwrite.setChecked(defaults.overwrite)
        self._add_missing = QCheckBox(self.tr("Add ROMs that are missing from gamelist.xml"))
        self._add_missing.setChecked(defaults.add_missing_roms)
        self._remember = QCheckBox(self.tr("Use these choices as the default"))
        form.addRow(self._overwrite)
        form.addRow(self._add_missing)
        form.addRow(self._remember)
        return box

    def _update_mode_help(self) -> None:
        self._mode_help.setText(mode_help(MatchMode(self._mode.currentData())))

    # ── Result ───────────────────────────────────────────────────────────

    def choice(self) -> ScrapeChoice:
        """Current selections."""
        scope = next(k for k, b in self._scope_buttons.items() if b.isChecked())
        return ScrapeChoice(
            scope=scope,
            fields=self._fields.checked(),
            media=self._media.checked(),
            mode=MatchMode(self._mode.currentData()),
            overwrite=self._overwrite.isChecked(),
            add_missing_roms=self._add_missing.isChecked(),
            remember=self._remember.isChecked(),
        )
