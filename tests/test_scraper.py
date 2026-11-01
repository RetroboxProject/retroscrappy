"""Pipeline tests with fake providers (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from retroscrappy.core.gamelist import Gamelist
from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.library import discover_systems
from retroscrappy.core.settings import MatchMode, Settings
from retroscrappy.pipeline import scraper as scraper_module
from retroscrappy.pipeline.interaction import AutoInteraction
from retroscrappy.pipeline.scraper import ScrapeRequest, Scraper
from retroscrappy.providers.base import (
    GameData,
    GameQuery,
    Match,
    MediaCandidate,
    Provider,
    ProviderUnavailable,
)


class FakeProvider(Provider):
    """Returns canned data and counts calls."""

    label = "Fake"

    def __init__(self, key: str, data: GameData, exact: bool = True, fail: bool = False):
        self.key = key  # type: ignore[misc]
        self.fields = frozenset(data.fields)  # type: ignore[misc]
        self.media = frozenset(data.media)  # type: ignore[misc]
        self._data = data
        self._exact = exact
        self._fail = fail
        self.finds = 0

    def _check(self) -> None:
        """Always fine."""

    def find(self, query: GameQuery) -> list[Match]:
        self.finds += 1
        if self._fail:
            raise ProviderUnavailable("quota")
        return [Match(self.key, "1", query.name, exact=self._exact)]

    def fetch(self, match: Match, wanted: set) -> GameData:
        return GameData(
            fields={k: v for k, v in self._data.fields.items() if k in wanted},
            media={k: v for k, v in self._data.media.items() if k in wanted},
        )


@pytest.fixture(autouse=True)
def fake_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Write a dummy file instead of downloading."""

    def _download(_session, url: str, dest_no_ext: Path, fallback_ext: str) -> Path:
        dest = dest_no_ext.with_name(dest_no_ext.name + fallback_ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(url, encoding="utf-8")
        return dest

    monkeypatch.setattr(scraper_module, "download", _download)


def _snes(roms: Path, registry):
    return [s for s in discover_systems(roms, registry) if s.folder == "snes"]


def test_priority_and_missing_only(roms: Path, registry) -> None:
    """Sources are tried in order and only missing items are filled."""
    settings = Settings()
    settings.priorities["console"]["metadata"] = ["screenscraper", "igdb"]
    settings.priorities["console"]["thumbnail"] = ["screenscraper", "igdb"]
    first = FakeProvider("screenscraper", GameData(fields={Field.DEVELOPER: "Nintendo EAD"}))
    second = FakeProvider(
        "igdb",
        GameData(
            fields={Field.DEVELOPER: "IGNORED", Field.GENRE: "Platform", Field.DESC: "New"},
            media={MediaKind.THUMBNAIL: [MediaCandidate(url="http://x/box.png")]},
        ),
    )
    request = ScrapeRequest(
        systems=_snes(roms, registry),
        fields={Field.DEVELOPER, Field.GENRE, Field.DESC},
        media={MediaKind.THUMBNAIL},
        mode=MatchMode.AUTO,
    )
    summary = Scraper(settings, {"screenscraper": first, "igdb": second}, AutoInteraction()).run(
        request
    )

    assert summary.updated == 2  # Mario + Chrono (added from disk)
    gamelist = Gamelist.for_system(roms / "snes")
    mario = gamelist.find("./Super Mario World (USA).sfc")
    assert mario is not None
    assert mario.get("developer") == "Nintendo EAD"  # first provider wins
    assert mario.get("genre") == "Platform"  # second fills the gap
    assert mario.get("desc") == "Existing"  # not overwritten
    assert mario.get("thumbnail") == "./images/Super Mario World (USA)-thumb.png"
    assert (roms / "snes" / "images" / "Super Mario World (USA)-thumb.png").is_file()
    assert first.finds == 2 and second.finds == 2  # one lookup per game per provider


def test_unavailable_provider_is_disabled(roms: Path, registry) -> None:
    """A provider failing hard is not queried again."""
    settings = Settings()
    broken = FakeProvider("screenscraper", GameData(fields={Field.GENRE: "x"}), fail=True)
    request = ScrapeRequest(
        systems=_snes(roms, registry), fields={Field.GENRE}, media=set(), mode=MatchMode.AUTO
    )
    summary = Scraper(settings, {"screenscraper": broken}, AutoInteraction()).run(request)
    assert broken.finds == 1  # not retried for the second game
    assert summary.failed == 1 and summary.unchanged == 1


class RecordingInteraction(AutoInteraction):
    """Records questions and skips everything."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def choose_match(self, query, provider, matches):
        """Record the question and skip."""
        del provider, matches
        self.asked.append(query.name)


def test_semi_mode_asks_only_when_not_exact(roms: Path, registry) -> None:
    """Semi mode asks about fuzzy matches."""
    settings = Settings()
    vague = FakeProvider("screenscraper", GameData(fields={Field.GENRE: "x"}), exact=False)
    interaction = RecordingInteraction()
    request = ScrapeRequest(
        systems=_snes(roms, registry), fields={Field.GENRE}, media=set(), mode=MatchMode.SEMI
    )
    summary = Scraper(settings, {"screenscraper": vague}, interaction).run(request)
    assert sorted(interaction.asked) == ["Chrono Trigger", "Super Mario World"]
    assert summary.skipped == 2
