"""User settings, stored as INI in the user's config directory.

The model is plain dataclasses with no I/O; :func:`load_settings` and
:func:`save_settings` are the only functions that touch the file. The file
holds API credentials, so it is written with ``0600`` permissions.
"""

from __future__ import annotations

import configparser
import os
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from retroscrappy.core import paths
from retroscrappy.core.frontends import DEFAULT_FRONTEND, FRONTENDS
from retroscrappy.core.items import (
    DEFAULT_FIELDS,
    DEFAULT_MEDIA,
    Field,
    Item,
    MediaKind,
    parse_fields,
    parse_media,
)
from retroscrappy.core.logs import get_logger

_log = get_logger("settings")

#: Key of the 0.2 "all text fields" priority entry, read for migration only.
METADATA_KEY = "metadata"
PROVIDER_KEYS = ("screenscraper", "steamgriddb", "igdb")
#: Every item that has its own source order, in display order.
PRIORITY_KEYS = tuple(i.value for i in (*Field, *MediaKind))


class MatchMode(StrEnum):
    """How much the user is asked while scraping."""

    AUTO = "auto"  # never ask; best guess
    SEMI = "semi"  # ask only when the match is ambiguous
    MANUAL = "manual"  # always confirm game and pick media


def _default_priorities() -> dict[str, list[str]]:
    ss, sg, ig = PROVIDER_KEYS
    table: dict[str, list[str]] = {f.value: [ss, ig] for f in Field}
    table.update(
        {
            MediaKind.IMAGE.value: [ss, ig],
            MediaKind.THUMBNAIL.value: [ss, sg, ig],
            MediaKind.MARQUEE.value: [ss, sg],
            MediaKind.TITLESHOT.value: [ss],
            MediaKind.FANART.value: [ss, sg, ig],
            MediaKind.BOXBACK.value: [ss],
            MediaKind.VIDEO.value: [ss],
            MediaKind.MANUAL.value: [ss],
        }
    )
    return table


@dataclass
class LibrarySettings:
    """Where the library is."""

    frontend: str = DEFAULT_FRONTEND
    roms_dir: str = ""
    es_systems: str = ""

    @property
    def roms_path(self) -> Path | None:
        """``roms_dir`` as a path, or ``None`` if unset."""
        return Path(self.roms_dir).expanduser() if self.roms_dir else None

    @property
    def es_systems_path(self) -> Path | None:
        """``es_systems`` as a path, or ``None`` if unset."""
        return Path(self.es_systems).expanduser() if self.es_systems else None


@dataclass
class RegionSettings:
    """Language order for text and region order for names, dates and media."""

    languages: list[str] = field(default_factory=lambda: ["en"])
    regions: list[str] = field(default_factory=lambda: ["eu", "us", "wor", "jp"])


@dataclass
class ScrapeDefaults:
    """Defaults pre-filled in every scrape run."""

    mode: MatchMode = MatchMode.SEMI
    overwrite: bool = False
    add_missing_roms: bool = True
    fields: set[Field] = field(default_factory=lambda: set(DEFAULT_FIELDS))
    media: set[MediaKind] = field(default_factory=lambda: set(DEFAULT_MEDIA))
    hash_max_mb: int = 128


@dataclass
class ScreenScraperAccount:
    """ScreenScraper developer and user credentials."""

    enabled: bool = True
    dev_id: str = ""
    dev_password: str = ""
    username: str = ""
    password: str = ""

    @property
    def configured(self) -> bool:
        """True if the mandatory developer credentials are set."""
        return bool(self.dev_id and self.dev_password)


@dataclass
class SteamGridDBAccount:
    """SteamGridDB API key."""

    enabled: bool = True
    api_key: str = ""

    @property
    def configured(self) -> bool:
        """True if the API key is set."""
        return bool(self.api_key)


@dataclass
class IGDBAccount:
    """Twitch application credentials for IGDB."""

    enabled: bool = True
    client_id: str = ""
    client_secret: str = ""

    @property
    def configured(self) -> bool:
        """True if both Twitch credentials are set."""
        return bool(self.client_id and self.client_secret)


@dataclass
class Settings:
    """Everything the user can configure."""

    library: LibrarySettings = field(default_factory=LibrarySettings)
    region: RegionSettings = field(default_factory=RegionSettings)
    scrape: ScrapeDefaults = field(default_factory=ScrapeDefaults)
    screenscraper: ScreenScraperAccount = field(default_factory=ScreenScraperAccount)
    steamgriddb: SteamGridDBAccount = field(default_factory=SteamGridDBAccount)
    igdb: IGDBAccount = field(default_factory=IGDBAccount)
    priorities: dict[str, list[str]] = field(default_factory=_default_priorities)

    def priority(self, item: Item) -> list[str]:
        """Ordered provider keys to try for ``item``."""
        return list(self.priorities.get(item.value, []))


# ── INI conversion ───────────────────────────────────────────────────────


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _join(values: object) -> str:
    return ", ".join(
        sorted(str(v) for v in values) if isinstance(values, set) else map(str, values)
    )


def _read_ini(parser: configparser.ConfigParser) -> Settings:
    s = Settings()
    get = parser.get
    getbool = parser.getboolean

    s.library.frontend = get("library", "frontend", fallback=s.library.frontend)
    if s.library.frontend not in FRONTENDS:
        s.library.frontend = DEFAULT_FRONTEND
    s.library.roms_dir = get("library", "roms_dir", fallback="")
    s.library.es_systems = get("library", "es_systems", fallback="")

    languages = _split(get("region", "languages", fallback=""))
    legacy_language = get("region", "language", fallback="").strip()
    s.region.languages = languages or ([legacy_language] if legacy_language else ["en"])
    s.region.regions = _split(get("region", "regions", fallback="")) or s.region.regions

    try:
        s.scrape.mode = MatchMode(get("scrape", "mode", fallback=MatchMode.SEMI.value))
    except ValueError:
        s.scrape.mode = MatchMode.SEMI
    s.scrape.overwrite = getbool("scrape", "overwrite", fallback=False)
    s.scrape.add_missing_roms = getbool("scrape", "add_missing_roms", fallback=True)
    if parser.has_option("scrape", "fields"):
        s.scrape.fields = parse_fields(_split(get("scrape", "fields")))
    if parser.has_option("scrape", "media"):
        s.scrape.media = parse_media(_split(get("scrape", "media")))
    s.scrape.hash_max_mb = parser.getint("scrape", "hash_max_mb", fallback=128)

    for name in PROVIDER_KEYS:
        account = getattr(s, name)
        for attr, default in vars(account).items():
            if isinstance(default, bool):
                setattr(account, attr, getbool(name, attr, fallback=default))
            else:
                setattr(account, attr, get(name, attr, fallback=default).strip())

    _read_priorities(parser, s)
    return s


def _read_priorities(parser: configparser.ConfigParser, s: Settings) -> None:
    """``[priority]``, or the 0.2 ``[priority.console]`` table if that is all there is."""
    section = "priority" if parser.has_section("priority") else "priority.console"
    if not parser.has_section(section):
        return
    legacy_text = parser.get(section, METADATA_KEY, fallback=None)
    for key in PRIORITY_KEYS:
        raw = parser.get(section, key, fallback=None)
        if raw is None and key in {f.value for f in Field}:
            raw = legacy_text
        if raw is not None:
            s.priorities[key] = [p for p in _split(raw) if p in PROVIDER_KEYS]


def _write_ini(s: Settings) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser["library"] = {
        "frontend": s.library.frontend,
        "roms_dir": s.library.roms_dir,
        "es_systems": s.library.es_systems,
    }
    parser["region"] = {
        "languages": _join(s.region.languages),
        "regions": _join(s.region.regions),
    }
    parser["scrape"] = {
        "mode": MatchMode(s.scrape.mode).value,
        "overwrite": str(s.scrape.overwrite).lower(),
        "add_missing_roms": str(s.scrape.add_missing_roms).lower(),
        "fields": _join({str(f) for f in s.scrape.fields}),
        "media": _join({str(m) for m in s.scrape.media}),
        "hash_max_mb": str(s.scrape.hash_max_mb),
    }
    for name in PROVIDER_KEYS:
        parser[name] = {
            k: (str(v).lower() if isinstance(v, bool) else str(v))
            for k, v in vars(getattr(s, name)).items()
        }
    parser["priority"] = {key: _join(s.priorities.get(key, [])) for key in PRIORITY_KEYS}
    return parser


# ── Legacy migration ─────────────────────────────────────────────────────

_LEGACY_KEYS = {
    "roms": ("library", "roms_dir"),
    "sgdb_apikey": ("steamgriddb", "api_key"),
    "apikey": ("steamgriddb", "api_key"),
    "igdb_client_id": ("igdb", "client_id"),
    "igdb_client_secret": ("igdb", "client_secret"),
    "ss_devid": ("screenscraper", "dev_id"),
    "ss_devpassword": ("screenscraper", "dev_password"),
    "ss_ssid": ("screenscraper", "username"),
    "ss_sspassword": ("screenscraper", "password"),
}


def _migrate_legacy(legacy: Path) -> Settings | None:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(legacy, encoding="utf-8")
    except configparser.Error:
        return None
    s = Settings()
    found = False
    for section in parser.sections():
        for old_key, (group, attr) in _LEGACY_KEYS.items():
            value = parser.get(section, old_key, fallback="").strip()
            if value:
                setattr(getattr(s, group), attr, value)
                found = True
    if found:
        _log.info("Imported settings from the previous version (%s)", legacy)
    return s if found else None


# ── Public API ───────────────────────────────────────────────────────────


def load_settings(path: Path | None = None) -> Settings:
    """Read settings, migrating from the old tool on first run."""
    path = path or paths.config_file()
    if not path.is_file():
        migrated = _migrate_legacy(paths.legacy_config_file())
        return migrated or Settings()
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error as exc:
        _log.error("Invalid settings file %s (%s); using defaults", path, exc)
        return Settings()
    return _read_ini(parser)


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    """Write settings atomically with owner-only permissions. Returns the file path."""
    path = path or paths.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = _write_ini(settings)  # fail before touching the file
    fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".ini", dir=path.parent)
    try:
        os.chmod(tmp_name, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            parser.write(handle)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path
