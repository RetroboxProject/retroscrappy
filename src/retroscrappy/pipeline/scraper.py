"""Scrape runner: walks systems and games, asks providers in priority order,
downloads media and updates ``gamelist.xml``.

For each game the runner works out which fields and media are missing (or
all of them when overwriting). For every such item it tries the providers
listed in that item's priority order until one returns it. Each provider is
matched and fetched at most once per game, asking for every item that lists
it, so a provider is never queried twice for the same ROM.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import requests

from retroscrappy.core.gamelist import GameEntry
from retroscrappy.core.items import Field, Item, MediaKind
from retroscrappy.core.library import SystemDir, add_missing_roms, has_media
from retroscrappy.core.logs import get_logger, log_success
from retroscrappy.core.settings import MatchMode, Settings
from retroscrappy.pipeline.interaction import (
    GameOutcome,
    Interaction,
    NullProgress,
    ProgressListener,
    RunSummary,
)
from retroscrappy.providers.base import (
    GameData,
    GameQuery,
    Match,
    MediaCandidate,
    Provider,
    ProviderError,
    ProviderUnavailable,
)
from retroscrappy.pipeline.media import save_media
from retroscrappy.providers.http import fetch_many_bytes, make_session

_log = get_logger("scraper")

#: Save the gamelist every N updated games (and always at the end).
SAVE_EVERY = 10
#: In semi mode, media whose best score leads by at most this is "ambiguous".
SEMI_SCORE_MARGIN = 3


class Cancelled(Exception):
    """Raised internally when the user cancels the run."""


@dataclass
class ScrapeRequest:
    """What to scrape in one run."""

    systems: list[SystemDir]
    fields: set[Field]
    media: set[MediaKind]
    mode: MatchMode = MatchMode.SEMI
    overwrite: bool = False
    add_missing_roms: bool = True
    #: Restrict to these ROMs: system folder → set of ``./rel`` paths.
    only: dict[str, set[str]] | None = None


class Scraper:
    """Runs a :class:`ScrapeRequest`."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        settings: Settings,
        providers: dict[str, Provider],
        interaction: Interaction,
        *,
        progress: ProgressListener | None = None,
        cancel: threading.Event | None = None,
    ) -> None:
        self._settings = settings
        self._providers = dict(providers)
        self._ui = interaction
        self._progress = progress or NullProgress()
        self._cancel = cancel or threading.Event()
        self._session = make_session()

    # ── Run ──────────────────────────────────────────────────────────────

    def run(self, request: ScrapeRequest) -> RunSummary:
        """Process every requested system. Never raises for per-game errors."""
        summary = RunSummary()
        if not self._providers:
            _log.error("No data source is configured; add credentials in the settings")
            return summary
        _log.info("Sources: %s", ", ".join(p.label for p in self._providers.values()))
        try:
            for system in request.systems:
                self._run_system(system, request, summary)
        except Cancelled:
            summary.cancelled = True
            _log.warning("Scrape cancelled")
        log_success(
            _log,
            "Done: %d updated, %d unchanged, %d skipped, %d failed",
            summary.updated,
            summary.unchanged,
            summary.skipped,
            summary.failed,
        )
        return summary

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise Cancelled

    def _run_system(self, system: SystemDir, request: ScrapeRequest, summary: RunSummary) -> None:
        self._check_cancel()
        gamelist = system.gamelist()
        if request.add_missing_roms:
            added = add_missing_roms(system, gamelist)
            if added:
                _log.info("[%s] Added %d ROMs missing from gamelist.xml", system.folder, len(added))

        wanted = request.only.get(system.folder) if request.only else None
        # Hidden games are skipped unless the user picked them explicitly.
        entries = [
            e
            for e in gamelist.games
            if e.path and (e.path in wanted if wanted is not None else not e.hidden)
        ]
        _log.info("[%s] %s: %d games", system.folder, system.label, len(entries))
        self._progress.system_started(system, len(entries))

        pending_saves = 0
        try:
            for index, entry in enumerate(entries, 1):
                self._check_cancel()
                self._progress.game_started(index, len(entries), entry.name)
                outcome = self._scrape_game(system, entry, request)
                summary.count(outcome)
                self._progress.game_finished(outcome)
                if outcome.status == "updated":
                    gamelist.mark_dirty()
                    pending_saves += 1
                    if pending_saves >= SAVE_EVERY:
                        gamelist.save()
                        pending_saves = 0
        finally:
            if gamelist.save():
                _log.debug("[%s] gamelist.xml saved", system.folder)

    # ── One game ─────────────────────────────────────────────────────────

    def _scrape_game(
        self, system: SystemDir, entry: GameEntry, request: ScrapeRequest
    ) -> GameOutcome:
        outcome = GameOutcome(system=system.folder, rel_path=entry.path, name=entry.name)
        needed: list[Item] = [
            f for f in Field if f in request.fields and (request.overwrite or not entry.get(f))
        ]
        needed += [
            k
            for k in MediaKind
            if k in request.media and (request.overwrite or not has_media(system.path, entry, k))
        ]
        if not needed:
            return outcome

        query = GameQuery(
            platform=system.platform, system_dir=system.path, rel_path=entry.path, name=entry.name
        )
        job = _GameJob(self, query, request.mode, needed)
        for item in needed:
            self._check_cancel()
            if self._fill_item(job, system, entry, item):
                outcome.updated.append(item.value)
            else:
                outcome.missing.append(item.value)

        if outcome.updated:
            outcome.status = "updated"
            log_success(_log, "%s: %s", entry.name, ", ".join(outcome.updated))
        elif job.skipped_by_user:
            outcome.status = "skipped"
        elif job.failed:
            outcome.status = "failed"
        if outcome.missing:
            _log.info("%s: not found: %s", entry.name, ", ".join(outcome.missing))
        return outcome

    def _fill_item(self, job: _GameJob, system: SystemDir, entry: GameEntry, item: Item) -> bool:
        for key in self._settings.priority(item):
            provider = self._providers.get(key)
            if provider is None or not provider.can_provide(item):
                continue
            data = job.data_from(provider)
            if data is None:
                continue
            if isinstance(item, Field):
                value = data.fields.get(item)
                if value:
                    entry.set(item.value, value)
                    return True
            elif self._fill_media(job, system, entry, item, provider, data):
                return True
        return False

    def _fill_media(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        job: _GameJob,
        system: SystemDir,
        entry: GameEntry,
        kind: MediaKind,
        provider: Provider,
        data: GameData,
    ) -> bool:
        candidates = data.media.get(kind) or []
        chosen = self._choose_media(job, kind, provider, candidates)
        if chosen is None:
            return False
        try:
            save_media(self._session, system.path, entry, kind, chosen)
        except (requests.RequestException, OSError) as exc:
            _log.warning(
                "%s: %s download failed (%s)", entry.name, kind.value, exc.__class__.__name__
            )
            return False
        return True

    # ── Choices ──────────────────────────────────────────────────────────

    def choose_match(self, job: _GameJob, provider: Provider, matches: list[Match]) -> Match | None:
        """Apply the match mode, asking the user when needed."""
        if not matches:
            return None
        best = matches[0]
        if job.mode is MatchMode.AUTO or (job.mode is MatchMode.SEMI and best.exact):
            return best
        return self._ui.choose_match(job.query, provider.label, matches)

    def _choose_media(
        self, job: _GameJob, kind: MediaKind, provider: Provider, candidates: list[MediaCandidate]
    ) -> MediaCandidate | None:
        if not candidates:
            return None
        if job.mode is MatchMode.AUTO or (
            job.mode is MatchMode.SEMI and not _ambiguous(candidates)
        ):
            return candidates[0]
        self._check_cancel()
        if self._ui.wants_previews:
            missing = [c for c in candidates if c.preview is None]
            for cand, blob in zip(
                missing, fetch_many_bytes(self._session, [c.thumb_url or c.url for c in missing])
            ):
                cand.preview = blob
        return self._ui.choose_media(job.query, kind, provider.label, candidates)

    def disable(self, provider: Provider, reason: str) -> None:
        """Stop using a provider for the rest of the run."""
        if self._providers.pop(provider.key, None) is not None:
            _log.error("%s disabled for this run: %s", provider.label, reason)


class _GameJob:
    """Per-game cache of matches and fetched data."""

    def __init__(self, scraper: Scraper, query: GameQuery, mode: MatchMode, needed: list[Item]):
        self.scraper = scraper
        self.query = query
        self.mode = mode
        self.needed = needed
        self.skipped_by_user = False
        self.failed = False
        self._data: dict[str, GameData | None] = {}

    def data_from(self, provider: Provider) -> GameData | None:
        """Match and fetch once; later calls reuse the result."""
        if provider.key in self._data:
            return self._data[provider.key]
        result: GameData | None = None
        try:
            if provider.supports(self.query.platform):
                result = self._match_and_fetch(provider)
        except ProviderUnavailable as exc:
            self.scraper.disable(provider, str(exc))
            self.failed = True
        except ProviderError as exc:
            _log.warning("%s: %s", self.query.name, exc)
            self.failed = True
        self._data[provider.key] = result
        return result

    def _match_and_fetch(self, provider: Provider) -> GameData | None:
        matches = provider.find(self.query)
        if not matches:
            _log.info("%s: no match on %s", self.query.name, provider.label)
            return None
        match = self.scraper.choose_match(self, provider, matches)
        if match is None:
            self.skipped_by_user = True
            return None
        _log.debug("%s → %s on %s", self.query.name, match.describe(), provider.label)
        wanted = {i for i in self.needed if provider.can_provide(i)}
        return provider.fetch(match, wanted)


def _ambiguous(candidates: list[MediaCandidate]) -> bool:
    """Votes exist and do not clearly favour the first candidate."""
    if len(candidates) < 2 or candidates[0].score is None:
        return False
    best = candidates[0].score
    second = candidates[1].score or 0
    return best <= 0 or best - second <= SEMI_SCORE_MARGIN
