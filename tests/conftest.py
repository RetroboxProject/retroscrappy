"""Shared fixtures: a tiny fake ROM library and isolated config dirs."""

from __future__ import annotations

from pathlib import Path

import pytest

from retroscrappy.core.platforms import load_registry


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Never touch the real user config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path


@pytest.fixture
def roms(tmp_path: Path) -> Path:
    """roms/ with snes (gamelist), psx (multi-disc), steam and an unknown folder."""
    root = tmp_path / "roms"
    snes = root / "snes"
    snes.mkdir(parents=True)
    (snes / "Super Mario World (USA).sfc").write_bytes(b"smw")
    (snes / "Chrono Trigger (USA).sfc").write_bytes(b"ct")
    (snes / "gamelist.xml").write_text(
        "<?xml version='1.0'?><gameList><game>"
        "<path>./Super Mario World (USA).sfc</path><name>Super Mario World</name>"
        "<desc>Existing</desc><favorite>true</favorite></game></gameList>",
        encoding="utf-8",
    )
    psx = root / "psx"
    psx.mkdir()
    for disc in ("FF7 (Disc 1).chd", "FF7 (Disc 2).chd"):
        (psx / disc).write_bytes(b"x")
    (psx / "FF7.m3u").write_text("FF7 (Disc 1).chd\nFF7 (Disc 2).chd\n", encoding="utf-8")
    (root / "steam").mkdir()
    (root / "steam" / "Hades.steam").write_text("1145360", encoding="utf-8")
    (root / "mystery").mkdir()
    (root / "mystery" / "gamelist.xml").write_text("<gameList/>", encoding="utf-8")
    (root / "empty_unknown").mkdir()
    return root


@pytest.fixture
def registry():
    """Bundled platform table."""
    return load_registry()
