"""Platform table: maps system folder names to provider ids and ROM extensions."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from importlib import resources
from pathlib import Path
from typing import Any

from retroscrappy.core.logs import get_logger

_log = get_logger("platforms")


@dataclass(frozen=True)
class Platform:
    """A gaming platform as seen by the scraper."""

    key: str
    name: str
    extensions: frozenset[str] = frozenset()
    screenscraper_id: int | None = None
    igdb_ids: tuple[int, ...] = ()
    aliases: tuple[str, ...] = ()
    is_pc: bool = False

    @property
    def profile(self) -> str:
        """Source-priority profile: ``pc`` or ``console``."""
        return "pc" if self.is_pc else "console"


def generic_platform(folder: str) -> Platform:
    """Placeholder for folders that are not in the table (name-only scraping)."""
    return Platform(key=folder, name=folder)


@dataclass
class PlatformRegistry:
    """Lookup of platforms by folder name or alias."""

    platforms: dict[str, Platform] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)

    def add(self, platform: Platform) -> None:
        """Add or replace a platform."""
        self.platforms[platform.key] = platform
        for alias in platform.aliases:
            self._aliases[alias.lower()] = platform.key

    def get(self, folder: str) -> Platform | None:
        """Platform for a system folder name, or ``None`` if unknown."""
        key = folder.lower()
        key = key if key in self.platforms else self._aliases.get(key, "")
        return self.platforms.get(key)

    def with_overrides(self, folder: str, **changes: Any) -> Platform:
        """Known platform (or a generic one) with some attributes replaced."""
        base = self.get(folder) or generic_platform(folder)
        return replace(base, **{k: v for k, v in changes.items() if v})


def _parse_entry(key: str, raw: dict[str, Any]) -> Platform:
    return Platform(
        key=key,
        name=str(raw.get("name") or key),
        extensions=frozenset(str(e).lower() for e in raw.get("extensions", [])),
        screenscraper_id=raw.get("screenscraper"),
        igdb_ids=tuple(int(i) for i in raw.get("igdb", [])),
        aliases=tuple(str(a) for a in raw.get("aliases", [])),
        is_pc=bool(raw.get("pc", False)),
    )


def _load_table(text: str, origin: str) -> list[Platform]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        _log.error("Invalid platform table %s: %s", origin, exc)
        return []
    entries = data.get("platforms", {})
    return [_parse_entry(key, raw) for key, raw in entries.items() if isinstance(raw, dict)]


def load_registry(user_file: Path | None = None) -> PlatformRegistry:
    """Bundled platforms, extended or overridden by ``user_file`` if it exists."""
    registry = PlatformRegistry()
    bundled = resources.files("retroscrappy.data").joinpath("platforms.toml")
    for platform in _load_table(bundled.read_text(encoding="utf-8"), "(bundled)"):
        registry.add(platform)
    if user_file and user_file.is_file():
        for platform in _load_table(user_file.read_text(encoding="utf-8"), str(user_file)):
            registry.add(platform)
        _log.debug("Loaded user platforms from %s", user_file)
    return registry
