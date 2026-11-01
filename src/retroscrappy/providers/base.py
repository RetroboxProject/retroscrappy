"""Provider contract shared by every data source.

A provider does two things: :meth:`Provider.find` turns a ROM into
candidate matches, and :meth:`Provider.fetch` returns text fields and media
candidates for a chosen match. Choosing between candidates is the
pipeline's job, not the provider's.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.names import same_game_name
from retroscrappy.core.platforms import Platform


class ProviderError(Exception):
    """A request failed; the current game is skipped for this provider."""


class ProviderUnavailable(ProviderError):
    """The provider cannot be used any more in this run (auth, quota, outage)."""


@dataclass(frozen=True)
class GameQuery:
    """What we know about a ROM before scraping it."""

    platform: Platform
    system_dir: Path
    rel_path: str
    name: str

    @property
    def rom_path(self) -> Path:
        """Absolute path of the ROM."""
        return self.system_dir / self.rel_path

    @property
    def file_name(self) -> str:
        """ROM file name with extension."""
        return Path(self.rel_path).name


@dataclass
class Match:
    """A game on a provider that may correspond to the ROM."""

    provider: str
    game_id: str
    name: str
    year: int | None = None
    exact: bool = False  # identified by hash/file name or unambiguous name
    extra: dict[str, Any] = field(default_factory=dict, repr=False)

    def describe(self) -> str:
        """``Name (1994)`` for lists."""
        return f"{self.name} ({self.year})" if self.year else self.name


@dataclass
class MediaCandidate:
    """One downloadable media file."""

    url: str
    thumb_url: str = ""
    width: int = 0
    height: int = 0
    score: int | None = None  # community votes, when the provider has them
    note: str = ""  # author, region...
    extension: str = ""  # ".png", ".mp4"... if known
    preview: bytes | None = field(default=None, repr=False)

    def describe(self) -> str:
        """Short one-line description for lists."""
        parts = []
        if self.width and self.height:
            parts.append(f"{self.width}×{self.height}")
        if self.score is not None:
            parts.append(f"score {self.score:+d}")
        if self.note:
            parts.append(self.note)
        return " · ".join(parts) or self.url


@dataclass
class GameData:
    """Everything a provider returned for one match."""

    fields: dict[Field, str] = field(default_factory=dict)
    media: dict[MediaKind, list[MediaCandidate]] = field(default_factory=dict)


class Provider(ABC):
    """Base class for data sources."""

    key: ClassVar[str]
    label: ClassVar[str]
    fields: ClassVar[frozenset[Field]] = frozenset()
    media: ClassVar[frozenset[MediaKind]] = frozenset()

    def supports(self, platform: Platform) -> bool:  # pylint: disable=unused-argument
        """Whether this provider is worth querying for ``platform``."""
        return True

    def can_provide(self, item: Field | MediaKind) -> bool:
        """Whether this provider ever returns ``item``."""
        return item in self.fields or item in self.media

    def check(self) -> None:
        """Validate credentials. Raises :class:`ProviderUnavailable` on failure."""
        try:
            self._check()
        except ProviderUnavailable:
            raise
        except ProviderError as exc:
            raise ProviderUnavailable(str(exc)) from exc

    @abstractmethod
    def _check(self) -> None:
        """Provider-specific credential test; may raise any :class:`ProviderError`."""

    @abstractmethod
    def find(self, query: GameQuery) -> list[Match]:
        """Candidate matches, best first. Empty list if nothing was found."""

    @abstractmethod
    def fetch(self, match: Match, wanted: set[Field | MediaKind]) -> GameData:
        """Data for ``match``; providers may skip work for items not in ``wanted``."""


def promote_exact_name(matches: list[Match], name: str) -> list[Match]:
    """Flag and move first the single match whose name equals ``name``.

    If several matches share the name the result stays ambiguous and
    nothing is flagged.
    """
    same = [m for m in matches if same_game_name(m.name, name)]
    if len(same) != 1:
        return matches
    same[0].exact = True
    return [same[0], *(m for m in matches if m is not same[0])]
