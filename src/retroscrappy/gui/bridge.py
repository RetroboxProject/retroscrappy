"""Thread plumbing between the scrape pipeline and the Qt main thread.

The pipeline runs in a plain worker thread. When it needs an answer
(:class:`QtInteraction`) it emits a signal carrying a :class:`PendingQuestion`
and blocks on an event until the main thread fills in the answer. Progress
and log records travel to the main thread as queued signals.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, Signal

from retroscrappy.core.items import MediaKind
from retroscrappy.core.library import SystemDir
from retroscrappy.core.settings import Settings
from retroscrappy.pipeline.interaction import GameOutcome, RunSummary
from retroscrappy.pipeline.scraper import ScrapeRequest, Scraper
from retroscrappy.providers.base import GameQuery, Match, MediaCandidate
from retroscrappy.providers.registry import build_providers

_POLL_SECONDS = 0.2


@dataclass
class PendingQuestion:
    """A question asked from the worker thread, answered on the main thread."""

    query: GameQuery
    provider: str
    options: list[Any]
    kind: MediaKind | None = None
    answer: Any = None
    done: threading.Event = field(default_factory=threading.Event)

    def reply(self, answer: Any) -> None:
        """Store the answer and wake the worker."""
        self.answer = answer
        self.done.set()


class QtInteraction(QObject):
    """:class:`~retroscrappy.pipeline.interaction.Interaction` backed by dialogs."""

    match_requested = Signal(object)
    media_requested = Signal(object)
    wants_previews = True

    def __init__(self, cancel: threading.Event, parent: QObject | None = None):
        super().__init__(parent)
        self._cancel = cancel

    def _ask(self, signal: Signal, question: PendingQuestion) -> Any:
        signal.emit(question)
        while not question.done.wait(_POLL_SECONDS):
            if self._cancel.is_set():
                return None
        return question.answer

    def choose_match(self, query: GameQuery, provider: str, matches: list[Match]) -> Match | None:
        """Ask the main thread to show the match picker."""
        return self._ask(self.match_requested, PendingQuestion(query, provider, matches))

    def choose_media(
        self, query: GameQuery, kind: MediaKind, provider: str, candidates: list[MediaCandidate]
    ) -> MediaCandidate | None:
        """Ask the main thread to show the media gallery."""
        question = PendingQuestion(query, provider, candidates, kind=kind)
        return self._ask(self.media_requested, question)


class ScrapeWorker(QObject):
    """Runs a scrape in a background thread and reports through signals."""

    system_began = Signal(str, int)
    game_began = Signal(int, int, str)
    game_done = Signal(object)
    run_done = Signal(object)

    def __init__(self, settings: Settings, parent: QObject | None = None):
        super().__init__(parent)
        self._settings = settings
        self.cancel_event = threading.Event()
        self.interaction = QtInteraction(self.cancel_event, self)
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        """True while the background thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(self, request: ScrapeRequest) -> None:
        """Start scraping ``request`` in the background."""
        self.cancel_event.clear()
        self._thread = threading.Thread(target=self._run, args=(request,), daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        """Ask the run to stop after the current step."""
        self.cancel_event.set()

    def _run(self, request: ScrapeRequest) -> None:
        summary = RunSummary()
        try:
            scraper = Scraper(
                self._settings,
                build_providers(self._settings),
                self.interaction,
                progress=self,
                cancel=self.cancel_event,
            )
            summary = scraper.run(request)
        except Exception:  # pylint: disable=broad-exception-caught
            logging.getLogger("retroscrappy").exception("Unexpected error while scraping")
        finally:
            self.run_done.emit(summary)

    # ProgressListener implementation (called from the worker thread)

    def system_started(self, system: SystemDir, total: int) -> None:
        """Forward to the main thread."""
        self.system_began.emit(system.label, total)

    def game_started(self, index: int, total: int, name: str) -> None:
        """Forward to the main thread."""
        self.game_began.emit(index, total, name)

    def game_finished(self, outcome: GameOutcome) -> None:
        """Forward to the main thread."""
        self.game_done.emit(outcome)


class _LogEmitter(QObject):
    record = Signal(int, str)


class QtLogHandler(logging.Handler):
    """Logging handler that forwards formatted records to a Qt slot."""

    def __init__(self) -> None:
        super().__init__()
        self.emitter = _LogEmitter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.emitter.record.emit(record.levelno, self.format(record))
        except RuntimeError:  # emitter deleted during shutdown
            pass
