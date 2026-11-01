"""Tests for names, gamelists, library discovery and settings."""

from __future__ import annotations

import configparser
from pathlib import Path

from retroscrappy.core import paths
from retroscrappy.core.gamelist import Gamelist, normalize_rel_path
from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.library import add_missing_roms, discover_systems, find_roms
from retroscrappy.core.names import normalize, same_game_name, title_from_filename
from retroscrappy.core.settings import MatchMode, Settings, load_settings, save_settings


def test_title_from_filename() -> None:
    """ROM tags and trailing articles are cleaned up."""
    assert title_from_filename("Sonic The Hedgehog 2 (World) (Rev B) [!]") == (
        "Sonic The Hedgehog 2"
    )
    assert title_from_filename("Legend of Zelda, The (USA)") == "The Legend of Zelda"
    assert title_from_filename("age_of_empires_ii") == "age of empires ii"


def test_name_comparison() -> None:
    """Accents, case, tags and '&' do not affect equality."""
    assert same_game_name("Pokémon Red", "pokemon red (USA)")
    assert normalize("Ratchet & Clank") == normalize("Ratchet and Clank")
    assert not same_game_name("", "")


def test_normalize_rel_path() -> None:
    """Paths are compared in ./posix form."""
    assert normalize_rel_path("game.zip") == "./game.zip"
    assert normalize_rel_path("./sub//game.zip") == "./sub/game.zip"
    assert normalize_rel_path(".\\sub\\game.zip") == "./sub/game.zip"
    assert normalize_rel_path("/abs/game.zip") == "/abs/game.zip"


def test_gamelist_roundtrip_keeps_unknown_tags(roms: Path) -> None:
    """Saving keeps foreign tags and writes a backup."""
    gamelist = Gamelist.for_system(roms / "snes")
    entry = gamelist.find("Super Mario World (USA).sfc")
    assert entry is not None and entry.get("favorite") == "true"
    entry.set(Field.DEVELOPER, "Nintendo")
    gamelist.mark_dirty()
    assert gamelist.save()
    assert (roms / "snes" / "gamelist.xml.bak").is_file()

    again = Gamelist.for_system(roms / "snes")
    reloaded = again.find("./Super Mario World (USA).sfc")
    assert reloaded is not None
    assert reloaded.get("developer") == "Nintendo"
    assert reloaded.get("favorite") == "true"


def test_discovery(roms: Path, registry) -> None:
    """Known, PC and unknown-with-gamelist folders are detected."""
    systems = {s.folder: s for s in discover_systems(roms, registry)}
    assert set(systems) == {"snes", "psx", "steam", "mystery"}
    assert systems["snes"].known and systems["snes"].platform.screenscraper_id == 4
    assert systems["steam"].platform.is_pc
    assert not systems["mystery"].known


def test_find_roms_collapses_m3u(roms: Path, registry) -> None:
    """Discs listed in an .m3u count once; missing ROMs get entries."""
    systems = {s.folder: s for s in discover_systems(roms, registry)}
    assert find_roms(systems["psx"]) == ["./FF7.m3u"]
    added = add_missing_roms(systems["snes"], gamelist := systems["snes"].gamelist())
    assert [e.name for e in added] == ["Chrono Trigger"]
    assert len(gamelist.games) == 2


def test_settings_roundtrip() -> None:
    """Settings survive a save/load cycle with private permissions."""
    settings = Settings()
    settings.library.roms_dir = "/userdata/roms"
    settings.scrape.mode = MatchMode.MANUAL
    settings.scrape.media = {MediaKind.VIDEO}
    settings.priorities["pc"]["thumbnail"] = ["igdb"]
    path = save_settings(settings)
    assert path.stat().st_mode & 0o077 == 0
    loaded = load_settings()
    assert loaded.library.roms_dir == "/userdata/roms"
    assert loaded.scrape.mode is MatchMode.MANUAL
    assert loaded.scrape.media == {MediaKind.VIDEO}
    assert loaded.priority("pc", MediaKind.THUMBNAIL) == ["igdb"]
    assert loaded.priority("console", Field.DESC) == ["screenscraper", "igdb"]


def test_legacy_settings_migration() -> None:
    """Credentials from sgdb-scraper are imported."""
    legacy = paths.legacy_config_file()
    legacy.parent.mkdir(parents=True)
    parser = configparser.ConfigParser()
    parser["general"] = {"roms": "/old/roms", "sgdb_apikey": "KEY", "ss_devid": "dev"}
    with legacy.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    settings = load_settings()
    assert settings.library.roms_dir == "/old/roms"
    assert settings.steamgriddb.api_key == "KEY"
    assert settings.screenscraper.dev_id == "dev"
