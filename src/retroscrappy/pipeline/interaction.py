"""Contracts between the pipeline and a user interface (CLI, Qt, tests).

The pipeline never imports a UI toolkit; it only calls these protocols.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from retroscrappy.core.items import MediaKind
from retroscrappy.core.library import SystemDir
from retroscrappy.providers.base import GameQuery, Match, MediaCandidate


class Interaction(Protocol):
    """Questions the pipeline may ask while scraping."""

    #: Whether :meth:`choose_media` wants ``MediaCandidate.preview`` filled.
    wants_previews: bool

    def choose_match(self, query: GameQuery, provider: str, matches: list[Match]) -> Match | None:
        """Pick the right game, or ``None`` to skip this provider for this ROM."""

    def choose_media(
        self, query: GameQuery, kind: MediaKind, provider: str, candidates: list[MediaCandidate]
    ) -> MediaCandidate | None:
        """Pick one media file, or ``None`` to skip it."""


@dataclass
class GameOutcome:
    """Result of scraping one ROM."""

    system: str
    rel_path: str
    name: str
    status: str = "unchanged"  # unchanged | updated | skipped | failed
    updated: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass
class RunSummary:
    """Totals for a whole run."""

    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: bool = False

    def count(self, outcome: GameOutcome) -> None:
        """Add one game's outcome to the totals."""
        setattr(self, outcome.status, getattr(self, outcome.status) + 1)


class ProgressListener(Protocol):
    """Progress notifications; all methods are optional to implement."""

    def system_started(self, system: SystemDir, total: int) -> None:
        """A system is about to be processed."""

    def game_started(self, index: int, total: int, name: str) -> None:
        """Game ``index`` (1-based) of ``total`` is being processed."""

    def game_finished(self, outcome: GameOutcome) -> None:
        """A game has been processed."""


class NullProgress:
    """Progress listener that ignores everything."""

    def system_started(self, system: SystemDir, total: int) -> None:
        """Ignore."""

    def game_started(self, index: int, total: int, name: str) -> None:
        """Ignore."""

    def game_finished(self, outcome: GameOutcome) -> None:
        """Ignore."""


class AutoInteraction:
    """Never asks: picks the first candidate. Used for unattended runs."""

    wants_previews = False

    def choose_match(self, query: GameQuery, provider: str, matches: list[Match]) -> Match | None:
        """First match."""
        del query, provider
        return matches[0] if matches else None

    def choose_media(
        self, query: GameQuery, kind: MediaKind, provider: str, candidates: list[MediaCandidate]
    ) -> MediaCandidate | None:
        """First candidate."""
        del query, kind, provider
        return candidates[0] if candidates else None
