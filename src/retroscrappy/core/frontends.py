"""Supported EmulationStation-based frontends.

Batocera, RetroBat and Retrobox share the same ``gamelist.xml`` format and
media layout; a profile only supplies sensible defaults (where ROMs and
``es_systems.cfg`` usually are) so the user has less to configure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Frontend:
    """Defaults for one frontend."""

    key: str
    label: str
    roms_candidates: tuple[str, ...]
    es_systems_candidates: tuple[str, ...]

    def default_roms_dir(self) -> Path | None:
        """First existing ROM folder among the usual locations."""
        return _first_existing(self.roms_candidates, want_dir=True)

    def default_es_systems(self) -> Path | None:
        """First existing ``es_systems.cfg`` among the usual locations."""
        return _first_existing(self.es_systems_candidates, want_dir=False)


def _first_existing(candidates: tuple[str, ...], want_dir: bool) -> Path | None:
    for raw in candidates:
        expanded = os.path.expandvars(os.path.expanduser(raw))
        if "$" in expanded or "%" in expanded:
            continue  # unset environment variable
        path = Path(expanded)
        if path.is_dir() if want_dir else path.is_file():
            return path
    return None


FRONTENDS: dict[str, Frontend] = {
    "batocera": Frontend(
        key="batocera",
        label="Batocera",
        roms_candidates=("/userdata/roms",),
        es_systems_candidates=("/usr/share/emulationstation/es_systems.cfg",),
    ),
    "retrobat": Frontend(
        key="retrobat",
        label="RetroBat",
        roms_candidates=(r"C:\RetroBat\roms", r"D:\RetroBat\roms"),
        es_systems_candidates=(
            r"C:\RetroBat\emulationstation\.emulationstation\es_systems.cfg",
            r"D:\RetroBat\emulationstation\.emulationstation\es_systems.cfg",
        ),
    ),
    "retrobox": Frontend(
        key="retrobox",
        label="Retrobox",
        roms_candidates=("$RETROBOX_ROOT/roms",),
        es_systems_candidates=(
            "$RETROBOX_ROOT/emulationstation/es_systems.cfg",
            "~/.emulationstation/es_systems.cfg",
        ),
    ),
}

DEFAULT_FRONTEND = "batocera"


def get_frontend(key: str) -> Frontend:
    """Profile for ``key``, falling back to the default frontend."""
    return FRONTENDS.get(key, FRONTENDS[DEFAULT_FRONTEND])
