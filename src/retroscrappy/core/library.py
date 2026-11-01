"""The user's ROM library: system folders, their ROMs and scrape coverage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from retroscrappy.core.es_systems import EsSystem, parse_es_systems
from retroscrappy.core.gamelist import GAMELIST_NAME, Gamelist, GameEntry, normalize_rel_path
from retroscrappy.core.items import MEDIA_FOLDERS, Field, MediaKind
from retroscrappy.core.names import title_from_filename
from retroscrappy.core.platforms import Platform, PlatformRegistry

#: How deep to look for ROMs inside a system folder (multi-disc subfolders...).
MAX_SCAN_DEPTH = 3


@dataclass(frozen=True)
class SystemDir:
    """A system folder under ``roms/`` and the platform it maps to."""

    path: Path
    platform: Platform
    known: bool

    @property
    def folder(self) -> str:
        """Folder name, e.g. ``snes``."""
        return self.path.name

    @property
    def label(self) -> str:
        """Human readable name."""
        return self.platform.name

    def gamelist(self) -> Gamelist:
        """Load this system's gamelist."""
        return Gamelist.for_system(self.path)


@dataclass
class Coverage:
    """How complete the scraped data of a system is."""

    games: int = 0
    with_item: dict[str, int] = field(default_factory=dict)

    def ratio(self, key: str) -> float:
        """Fraction of games having ``key``."""
        return self.with_item.get(key, 0) / self.games if self.games else 0.0


def discover_systems(
    roms_dir: Path, registry: PlatformRegistry, es_systems_file: Path | None = None
) -> list[SystemDir]:
    """System folders in ``roms_dir`` that are known or already have a gamelist."""
    if not roms_dir.is_dir():
        return []
    declared: dict[str, EsSystem] = parse_es_systems(es_systems_file) if es_systems_file else {}
    systems: list[SystemDir] = []
    for child in sorted(roms_dir.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith(".") or child.name in MEDIA_FOLDERS:
            continue
        es_entry = declared.get(child.name)
        known = registry.get(child.name) or (registry.get(es_entry.platform) if es_entry else None)
        if es_entry:
            platform = registry.with_overrides(
                known.key if known else child.name,
                name=es_entry.fullname,
                extensions=es_entry.extensions,
            )
        elif known and _has_content(child, known.extensions):
            platform = known
        elif (child / GAMELIST_NAME).is_file():
            platform = registry.with_overrides(child.name)
        else:
            continue
        systems.append(SystemDir(path=child, platform=platform, known=known is not None))
    return systems


def _has_content(folder: Path, extensions: frozenset[str]) -> bool:
    """Cheap check: a gamelist or at least one ROM-looking entry at the top level.

    Batocera creates every system folder up front, so empty ones are hidden.
    """
    if (folder / GAMELIST_NAME).is_file():
        return True
    try:
        return any(
            _is_rom(child, extensions) or (child.is_dir() and child.name not in MEDIA_FOLDERS)
            for child in folder.iterdir()
        )
    except OSError:
        return False


def _is_rom(path: Path, extensions: frozenset[str]) -> bool:
    return path.suffix.lower() in extensions and not path.name.startswith(".")


def find_roms(system: SystemDir) -> list[str]:
    """ROM paths relative to the system folder, in ``./x`` form.

    Folders whose name carries a ROM extension (``Game.ps3``) count as one
    ROM and are not descended into. Files referenced by an ``.m3u`` in the
    same folder are skipped so multi-disc games appear once.
    """
    extensions = system.platform.extensions
    if not extensions:
        return []
    found: list[Path] = []
    _scan(system.path, extensions, found, depth=0)
    in_playlists = _m3u_members(found)
    rels = [p for p in found if p not in in_playlists]
    return sorted(normalize_rel_path(p.relative_to(system.path).as_posix()) for p in rels)


def _scan(folder: Path, extensions: frozenset[str], found: list[Path], depth: int) -> None:
    try:
        children = list(folder.iterdir())
    except OSError:
        return
    for child in children:
        if child.is_dir():
            if _is_rom(child, extensions):
                found.append(child)
            elif depth < MAX_SCAN_DEPTH and child.name not in MEDIA_FOLDERS:
                if not child.name.startswith("."):
                    _scan(child, extensions, found, depth + 1)
        elif _is_rom(child, extensions):
            found.append(child)


def _m3u_members(paths: list[Path]) -> set[Path]:
    members: set[Path] = set()
    for playlist in (p for p in paths if p.suffix.lower() == ".m3u" and p.is_file()):
        try:
            lines = playlist.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                members.add((playlist.parent / line).resolve())
    return {p for p in paths if p.resolve() in members}


def add_missing_roms(system: SystemDir, gamelist: Gamelist) -> list[GameEntry]:
    """Create entries for ROMs on disk that the gamelist does not list yet."""
    added = []
    for rel in find_roms(system):
        if gamelist.find(rel) is None:
            stem = Path(rel).stem
            added.append(gamelist.add(rel, title_from_filename(stem)))
    return added


def resolve_media_path(system_dir: Path, value: str) -> Path | None:
    """Absolute path of a media tag value, or ``None`` if empty."""
    if not value:
        return None
    path = Path(value.replace("\\", "/")).expanduser()
    return path if path.is_absolute() else (system_dir / path)


def has_media(system_dir: Path, entry: GameEntry, kind: MediaKind) -> bool:
    """True if the tag is set and points to an existing file."""
    path = resolve_media_path(system_dir, entry.get(kind.value))
    return bool(path and path.exists())


def compute_coverage(system: SystemDir, gamelist: Gamelist) -> Coverage:
    """Count, per field and media kind, how many games already have it."""
    coverage = Coverage(games=len(gamelist.games))
    for entry in gamelist.games:
        for fld in Field:
            if entry.get(fld.value):
                coverage.with_item[fld.value] = coverage.with_item.get(fld.value, 0) + 1
        for kind in MediaKind:
            if has_media(system.path, entry, kind):
                coverage.with_item[kind.value] = coverage.with_item.get(kind.value, 0) + 1
    return coverage
