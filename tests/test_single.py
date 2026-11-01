"""Tests for single-game editing helpers (no network)."""

from __future__ import annotations

from pathlib import Path

from retroscrappy.core.gamelist import Gamelist
from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.library import discover_systems
from retroscrappy.core.settings import Settings
from retroscrappy.gui.game_editor import date_from_display, date_to_display
from retroscrappy.pipeline.interaction import AutoInteraction
from retroscrappy.pipeline.media import import_media_file, remove_media
from retroscrappy.pipeline.single import ItemFetcher, edit_entry
from retroscrappy.providers.base import GameData, GameQuery, Match, Provider


class CountingProvider(Provider):
    """Returns a genre and counts lookups."""

    key = "screenscraper"
    label = "Fake"
    fields = frozenset({Field.GENRE, Field.DEVELOPER})

    def __init__(self) -> None:
        self.finds = 0

    def _check(self) -> None:
        """Always fine."""

    def find(self, query: GameQuery) -> list[Match]:
        self.finds += 1
        return [Match(self.key, "1", query.name, exact=True)]

    def fetch(self, match: Match, wanted: set) -> GameData:
        values = {Field.GENRE: "Platform", Field.DEVELOPER: "Nintendo"}
        return GameData(fields={k: v for k, v in values.items() if k in wanted})


def _snes(roms: Path, registry):
    return next(s for s in discover_systems(roms, registry) if s.folder == "snes")


def test_import_and_remove_media(roms: Path, registry, tmp_path: Path) -> None:
    """A local file is copied with the frontend name and can be removed again."""
    system = _snes(roms, registry)
    picture = tmp_path / "mine.JPG"
    picture.write_bytes(b"jpg")
    rel = "./Chrono Trigger (USA).sfc"  # not in gamelist yet: entry is created
    edit_entry(
        system, rel, lambda e: import_media_file(system.path, e, MediaKind.THUMBNAIL, picture)
    )
    target = system.path / "images" / "Chrono Trigger (USA)-thumb.jpg"
    assert target.read_bytes() == b"jpg"
    entry = Gamelist.for_system(system.path).find(rel)
    assert entry is not None and entry.get("thumbnail") == "./images/Chrono Trigger (USA)-thumb.jpg"

    edit_entry(system, rel, lambda e: remove_media(system.path, e, MediaKind.THUMBNAIL))
    assert not target.exists()
    entry = Gamelist.for_system(system.path).find(rel)
    assert entry is not None and not entry.get("thumbnail")


def test_fetcher_matches_once_per_game(roms: Path, registry) -> None:
    """Fetching two fields separately only looks the game up once."""
    system = _snes(roms, registry)
    fetcher = ItemFetcher(Settings(), AutoInteraction())
    provider = CountingProvider()
    fetcher._providers["screenscraper"] = provider  # pylint: disable=protected-access
    query = GameQuery(system.platform, system.path, "./Super Mario World (USA).sfc", "SMW")
    assert fetcher.fetch_fields("screenscraper", query, {Field.GENRE}) == {Field.GENRE: "Platform"}
    assert fetcher.fetch_fields("screenscraper", query, {Field.DEVELOPER}) == {
        Field.DEVELOPER: "Nintendo"
    }
    assert provider.finds == 1


def test_date_conversion() -> None:
    """Dates round-trip between gamelist and display formats."""
    assert date_to_display("19921121T000000") == "1992-11-21"
    assert date_from_display("1992-11-21") == "19921121T000000"
    assert date_from_display("1992") == "19920101T000000"
    assert date_from_display("1992-3") == "19920301T000000"
    assert date_from_display("soon") == "soon"
