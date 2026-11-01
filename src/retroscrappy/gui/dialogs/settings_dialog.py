"""Settings window: one page per concern, navigated from a side list.

Pages edit a private copy of :class:`Settings`; nothing is applied until
*Apply* or *OK* is pressed.
"""

from __future__ import annotations

import copy
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from retroscrappy.core.frontends import FRONTENDS
from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.settings import (
    PRIORITY_KEYS,
    PROFILES,
    MatchMode,
    Settings,
)
from retroscrappy.gui.labels import mode_label, priority_key_label, profile_label
from retroscrappy.gui.widgets import ItemChecklist, OrderedCheckList, PathPicker
from retroscrappy.providers.base import ProviderUnavailable
from retroscrappy.providers.registry import PROVIDER_LABELS, build_provider, providers_for

LANGUAGES = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "ru": "Русский",
    "ja": "日本語",
}
REGIONS = {
    "eu": "Europe",
    "us": "USA",
    "wor": "World",
    "jp": "Japan",
    "ss": "ScreenScraper generic",
    "fr": "France",
    "de": "Germany",
    "sp": "Spain",
    "uk": "United Kingdom",
    "it": "Italy",
    "br": "Brazil",
    "kr": "Korea",
    "cn": "China",
}


class _Page(QWidget):
    """A settings page: copies values in and out of a :class:`Settings`."""

    title = ""

    def load(self, settings: Settings) -> None:
        """Fill the widgets from ``settings``."""

    def store(self, settings: Settings) -> None:
        """Write the widgets back into ``settings``."""


class LibraryPage(_Page):
    """Frontend and folders."""

    def __init__(self) -> None:
        super().__init__()
        self.title = self.tr("Library")
        form = QFormLayout(self)
        self._frontend = QComboBox()
        for key, frontend in FRONTENDS.items():
            self._frontend.addItem(frontend.label, key)
        self._roms = PathPicker(select_dir=True, placeholder=self.tr("Auto-detect"))
        self._es_systems = PathPicker(select_dir=False, placeholder=self.tr("Auto-detect"))
        hint = QLabel(
            self.tr(
                "If es_systems.cfg is found, its systems, names and extensions are used. "
                "Otherwise systems are recognised by folder name."
            )
        )
        hint.setWordWrap(True)
        form.addRow(self.tr("Frontend:"), self._frontend)
        form.addRow(self.tr("ROM folder:"), self._roms)
        form.addRow(self.tr("es_systems.cfg:"), self._es_systems)
        form.addRow("", hint)

    def load(self, settings: Settings) -> None:
        self._frontend.setCurrentIndex(max(self._frontend.findData(settings.library.frontend), 0))
        self._roms.set_text(settings.library.roms_dir)
        self._es_systems.set_text(settings.library.es_systems)

    def store(self, settings: Settings) -> None:
        settings.library.frontend = self._frontend.currentData()
        settings.library.roms_dir = self._roms.text()
        settings.library.es_systems = self._es_systems.text()


class _CheckSignals(QObject):
    done = Signal(str, bool, str)


class AccountsPage(_Page):
    """Credentials for each provider, with a *Test* button."""

    _FIELDS = {
        "screenscraper": (
            ("dev_id", "Developer id", False),
            ("dev_password", "Developer password", True),
            ("username", "User name (optional)", False),
            ("password", "User password", True),
        ),
        "steamgriddb": (("api_key", "API key", True),),
        "igdb": (
            ("client_id", "Twitch client id", False),
            ("client_secret", "Client secret", True),
        ),
    }
    _HELP = {
        "screenscraper": "https://www.screenscraper.fr/",
        "steamgriddb": "https://www.steamgriddb.com/profile/preferences/api",
        "igdb": "https://api-docs.igdb.com/#account-creation",
    }

    def __init__(self) -> None:
        super().__init__()
        self.title = self.tr("Accounts")
        self._groups: dict[str, QGroupBox] = {}
        self._edits: dict[tuple[str, str], QLineEdit] = {}
        self._status: dict[str, QLabel] = {}
        self._signals = _CheckSignals()
        self._signals.done.connect(self._on_check_done)
        self._snapshot: Settings | None = None

        column = QVBoxLayout(self)
        for key, fields in self._FIELDS.items():
            column.addWidget(self._build_group(key, fields))
        column.addStretch(1)

    def _build_group(self, key: str, fields: tuple) -> QGroupBox:
        group = QGroupBox(PROVIDER_LABELS[key])
        group.setCheckable(True)
        form = QFormLayout(group)
        for attr, label, secret in fields:
            edit = QLineEdit()
            if secret:
                edit.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
            self._edits[(key, attr)] = edit
            form.addRow(self.tr(label) + ":", edit)
        link = QLabel(f'<a href="{self._HELP[key]}">{self.tr("Where do I get these?")}</a>')
        link.setOpenExternalLinks(True)
        test = QPushButton(self.tr("Test"))
        test.clicked.connect(lambda _=False, k=key: self._run_check(k))
        status = QLabel()
        self._status[key] = status
        row = QHBoxLayout()
        row.addWidget(link)
        row.addStretch(1)
        row.addWidget(status)
        row.addWidget(test)
        form.addRow(row)
        self._groups[key] = group
        return group

    def load(self, settings: Settings) -> None:
        self._snapshot = settings
        for key, group in self._groups.items():
            account = getattr(settings, key)
            group.setChecked(account.enabled)
            for (prov, attr), edit in self._edits.items():
                if prov == key:
                    edit.setText(getattr(account, attr))

    def store(self, settings: Settings) -> None:
        for key, group in self._groups.items():
            account = getattr(settings, key)
            account.enabled = group.isChecked()
            for (prov, attr), edit in self._edits.items():
                if prov == key:
                    setattr(account, attr, edit.text().strip())

    def _run_check(self, key: str) -> None:
        trial = copy.deepcopy(self._snapshot or Settings())
        self.store(trial)
        self._status[key].setText(self.tr("Testing…"))

        def work() -> None:
            try:
                build_provider(key, trial).check()
                self._signals.done.emit(key, True, "")
            except ProviderUnavailable as exc:
                self._signals.done.emit(key, False, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_check_done(self, key: str, ok: bool, message: str) -> None:
        label = self._status[key]
        label.setText(self.tr("✔ Working") if ok else self.tr("✘ Failed"))
        label.setToolTip(message)
        label.setStyleSheet("color: #2e7d32;" if ok else "color: #c62828;")


class SourcesPage(_Page):
    """Which provider to try first for every item, per platform profile."""

    def __init__(self) -> None:
        super().__init__()
        self.title = self.tr("Sources")
        self._priorities: dict[str, dict[str, list[str]]] = {}
        self._current: tuple[str, str] | None = None

        self._profile = QComboBox()
        for profile in PROFILES:
            self._profile.addItem(profile_label(profile), profile)
        self._items = QListWidget()
        for key in PRIORITY_KEYS:
            self._items.addItem(priority_key_label(key))
        self._order = OrderedCheckList()

        hint = QLabel(
            self.tr(
                "For each item, sources are tried from top to bottom until one has it. "
                "Drag to reorder; untick to never use a source for that item."
            )
        )
        hint.setWordWrap(True)
        top = QFormLayout()
        top.addRow(self.tr("Platforms:"), self._profile)
        lists = QHBoxLayout()
        lists.addWidget(self._items, 1)
        lists.addWidget(self._order, 1)
        column = QVBoxLayout(self)
        column.addLayout(top)
        column.addWidget(hint)
        column.addLayout(lists, 1)

        self._profile.currentIndexChanged.connect(self._show_current)
        self._items.currentRowChanged.connect(self._show_current)

    def _commit_current(self) -> None:
        if self._current:
            profile, key = self._current
            self._priorities[profile][key] = self._order.checked_keys()

    def _show_current(self) -> None:
        self._commit_current()
        row = self._items.currentRow()
        if row < 0:
            return
        profile = self._profile.currentData()
        key = PRIORITY_KEYS[row]
        self._current = (profile, key)
        capable = providers_for(key)
        current = [p for p in self._priorities[profile].get(key, []) if p in capable]
        self._order.set_items(current, capable, PROVIDER_LABELS)

    def load(self, settings: Settings) -> None:
        self._priorities = copy.deepcopy(settings.priorities)
        self._current = None
        self._items.setCurrentRow(0)
        self._show_current()

    def store(self, settings: Settings) -> None:
        self._commit_current()
        settings.priorities = copy.deepcopy(self._priorities)


class RegionPage(_Page):
    """Language for text and region order for names, dates and media."""

    def __init__(self) -> None:
        super().__init__()
        self.title = self.tr("Language & region")
        self._language = QComboBox()
        for code, name in LANGUAGES.items():
            self._language.addItem(name, code)
        self._regions = OrderedCheckList()
        form = QFormLayout(self)
        form.addRow(self.tr("Description language:"), self._language)
        form.addRow(self.tr("Preferred regions:"), self._regions)

    def load(self, settings: Settings) -> None:
        self._language.setCurrentIndex(max(self._language.findData(settings.region.language), 0))
        self._regions.set_items(settings.region.regions, list(REGIONS), REGIONS)

    def store(self, settings: Settings) -> None:
        settings.region.language = self._language.currentData()
        settings.region.regions = self._regions.checked_keys() or ["wor"]


class DefaultsPage(_Page):
    """Defaults pre-filled in the *Scrape* dialog."""

    def __init__(self) -> None:
        super().__init__()
        self.title = self.tr("Scrape defaults")
        self._mode = QComboBox()
        for mode in MatchMode:
            self._mode.addItem(mode_label(mode), mode)
        self._overwrite = QCheckBox(self.tr("Replace data that is already there"))
        self._add_missing = QCheckBox(self.tr("Add ROMs that are missing from gamelist.xml"))
        self._fields = ItemChecklist(list(Field))
        self._media = ItemChecklist(list(MediaKind))
        self._hash_limit = QSpinBox()
        self._hash_limit.setRange(0, 4096)
        self._hash_limit.setSuffix(" MB")
        self._hash_limit.setToolTip(
            self.tr("ROMs up to this size are hashed so ScreenScraper can identify them exactly.")
        )
        form = QFormLayout(self)
        form.addRow(self.tr("Questions:"), self._mode)
        form.addRow(self._overwrite)
        form.addRow(self._add_missing)
        form.addRow(self.tr("Text:"), self._fields)
        form.addRow(self.tr("Media:"), self._media)
        form.addRow(self.tr("Hash ROMs up to:"), self._hash_limit)

    def load(self, settings: Settings) -> None:
        scrape = settings.scrape
        self._mode.setCurrentIndex(list(MatchMode).index(scrape.mode))
        self._overwrite.setChecked(scrape.overwrite)
        self._add_missing.setChecked(scrape.add_missing_roms)
        self._fields.set_checked(scrape.fields)
        self._media.set_checked(scrape.media)
        self._hash_limit.setValue(scrape.hash_max_mb)

    def store(self, settings: Settings) -> None:
        scrape = settings.scrape
        scrape.mode = self._mode.currentData()
        scrape.overwrite = self._overwrite.isChecked()
        scrape.add_missing_roms = self._add_missing.isChecked()
        scrape.fields = self._fields.checked()
        scrape.media = self._media.checked()
        scrape.hash_max_mb = self._hash_limit.value()


class SettingsDialog(QDialog):
    """Modal settings window. Emits :attr:`applied` with the new settings."""

    applied = Signal(object)

    def __init__(self, settings: Settings, parent: QWidget | None = None, page: int = 0):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))
        self.resize(820, 560)
        self._settings = copy.deepcopy(settings)
        self._pages: list[_Page] = [
            LibraryPage(),
            AccountsPage(),
            SourcesPage(),
            RegionPage(),
            DefaultsPage(),
        ]

        nav = QListWidget()
        nav.setFixedWidth(180)
        stack = QStackedWidget()
        for widget in self._pages:
            widget.load(self._settings)
            nav.addItem(widget.title)
            stack.addWidget(widget)
        nav.currentRowChanged.connect(stack.setCurrentIndex)
        nav.setCurrentRow(page)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_button.clicked.connect(self._apply)

        body = QHBoxLayout()
        body.addWidget(nav)
        body.addWidget(stack, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(buttons)
        nav.setFocus(Qt.FocusReason.OtherFocusReason)

    def _apply(self) -> None:
        for widget in self._pages:
            widget.store(self._settings)
        self.applied.emit(copy.deepcopy(self._settings))

    def accept(self) -> None:
        self._apply()
        super().accept()
