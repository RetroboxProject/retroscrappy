"""Reader for EmulationStation ``es_systems.cfg`` files.

When available it is the authority on which folders are systems, their
display names and accepted extensions, so the scraper sees exactly what
EmulationStation sees.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from retroscrappy.core.logs import get_logger

_log = get_logger("es_systems")


@dataclass(frozen=True)
class EsSystem:
    """One ``<system>`` entry."""

    name: str
    fullname: str
    folder: str
    extensions: frozenset[str]
    platform: str


def _folder_of(path_text: str, name: str) -> str:
    """Last component of ``<path>`` (handles Windows and POSIX paths)."""
    text = path_text.strip().rstrip("/\\")
    if not text:
        return name
    return PureWindowsPath(text).name if "\\" in text else Path(text).name


def parse_es_systems(path: Path) -> dict[str, EsSystem]:
    """Systems declared in ``path``, keyed by folder name. Empty on error."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        _log.warning("Cannot read %s: %s", path, exc)
        return {}

    systems: dict[str, EsSystem] = {}
    for node in root.iter("system"):
        name = (node.findtext("name") or "").strip()
        if not name:
            continue
        folder = _folder_of(node.findtext("path") or "", name)
        extensions = frozenset(
            ext.lower() for ext in (node.findtext("extension") or "").split() if ext.startswith(".")
        )
        systems[folder] = EsSystem(
            name=name,
            fullname=(node.findtext("fullname") or name).strip(),
            folder=folder,
            extensions=extensions,
            platform=(node.findtext("platform") or "").split(",")[0].strip(),
        )
    return systems
