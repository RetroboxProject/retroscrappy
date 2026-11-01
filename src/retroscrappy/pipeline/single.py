"""On-demand operations on a single game, used by the game editor.

Unlike :class:`~retroscrappy.pipeline.scraper.Scraper`, the caller picks
the provider and the item explicitly. Matches are remembered per game and
provider, so fetching several items for the same game asks at most once.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from retroscrappy.core.gamelist import Gamelist, GameEntry
from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.library import SystemDir
from retroscrappy.core.names import title_from_filename
from retroscrappy.core.settings import Settings
from retroscrappy.pipeline.interaction import Interaction
from retroscrappy.pipeline.media import save_media
from retroscrappy.providers.base import GameQuery, Match, MediaCandidate, Provider
from retroscrappy.providers.http import fetch_many_bytes, make_session
from retroscrappy.providers.registry import build_provider

T = TypeVar("T")

#: Media kinds that have no image preview.
NO_PREVIEW = frozenset({MediaKind.VIDEO, MediaKind.MANUAL})


def edit_entry(system: SystemDir, rel_path: str, change: Callable[[GameEntry], T]) -> T:
    """Load the gamelist, apply ``change`` to the ROM's entry and save.

    The entry is created first if the ROM is not listed yet.
    """
    gamelist = Gamelist.for_system(system.path)
    entry = gamelist.find(rel_path) or gamelist.add(
        rel_path, title_from_filename(Path(rel_path).stem)
    )
    result = change(entry)
    gamelist.mark_dirty()
    gamelist.save()
    return result


def set_hidden(system: SystemDir, rel_paths: set[str], hidden: bool) -> int:
    """Hide or show several ROMs in EmulationStation. Returns how many changed."""
    gamelist = Gamelist.for_system(system.path)
    changed = 0
    for rel_path in sorted(rel_paths):
        entry = gamelist.find(rel_path) or gamelist.add(
            rel_path, title_from_filename(Path(rel_path).stem)
        )
        if entry.hidden != hidden:
            entry.hidden = hidden
            changed += 1
    if changed:
        gamelist.mark_dirty()
        gamelist.save()
    return changed


class ItemFetcher:
    """Fetches individual items for one game from a chosen provider."""

    def __init__(self, settings: Settings, interaction: Interaction) -> None:
        self._settings = settings
        self._ui = interaction
        self._session = make_session()
        self._providers: dict[str, Provider] = {}
        self._matches: dict[tuple[str, str], Match | None] = {}

    def provider(self, key: str) -> Provider:
        """Provider instance (created once per fetcher)."""
        if key not in self._providers:
            self._providers[key] = build_provider(key, self._settings)
        return self._providers[key]

    def _match(self, provider: Provider, query: GameQuery) -> Match | None:
        cache_key = (provider.key, query.rel_path)
        if cache_key not in self._matches:
            matches = provider.find(query)
            if not matches:
                match = None
            elif matches[0].exact:
                match = matches[0]
            else:
                match = self._ui.choose_match(query, provider.label, matches)
            self._matches[cache_key] = match
        return self._matches[cache_key]

    def fetch_fields(self, key: str, query: GameQuery, fields: set[Field]) -> dict[Field, str]:
        """Text values for ``fields``; empty if no match or nothing found.

        Raises :class:`~retroscrappy.providers.base.ProviderError`.
        """
        provider = self.provider(key)
        match = self._match(provider, query)
        if match is None:
            return {}
        return dict(provider.fetch(match, set(fields)).fields)

    def fetch_media(self, key: str, query: GameQuery, kind: MediaKind) -> list[MediaCandidate]:
        """Candidates for ``kind`` with previews loaded (except videos and manuals).

        Raises :class:`~retroscrappy.providers.base.ProviderError`.
        """
        provider = self.provider(key)
        match = self._match(provider, query)
        if match is None:
            return []
        candidates = provider.fetch(match, {kind}).media.get(kind, [])
        if kind not in NO_PREVIEW and candidates:
            blobs = fetch_many_bytes(self._session, [c.thumb_url or c.url for c in candidates])
            for candidate, blob in zip(candidates, blobs):
                candidate.preview = blob
        return candidates

    def store_media(
        self, system: SystemDir, rel_path: str, kind: MediaKind, candidate: MediaCandidate
    ) -> Path:
        """Download ``candidate`` for the ROM and update its gamelist entry.

        Raises :class:`requests.RequestException` or :class:`OSError`.
        """
        return edit_entry(
            system,
            rel_path,
            lambda entry: save_media(self._session, system.path, entry, kind, candidate),
        )
