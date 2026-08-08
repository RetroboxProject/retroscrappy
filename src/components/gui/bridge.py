"""bridge.py — Implementación de UserInteraction basada en PySide6.

Usa señales Qt con Qt.QueuedConnection + QWaitCondition para bloquear
el hilo de fondo mientras se muestra un diálogo modal en el hilo principal.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot, Qt, QMutex, QWaitCondition

from ..models import GameCandidate, ImageCandidate


class BridgeSignals(QObject):
    """Señales compartidas entre el hilo principal (MainWindow) y el worker."""

    log_signal = Signal(str)
    status_signal = Signal(str)

    # Diálogos solicitados por el worker -> hilo principal los muestra
    choose_game_requested = Signal(str, list)      # query, list[GameCandidate]
    choose_image_requested = Signal(str, list)     # label, list[ImageCandidate]
    confirm_overwrite_requested = Signal(str)      # filename

    # Resultados devueltos por el hilo principal -> worker
    game_chosen = Signal(object)                   # int | None
    image_chosen = Signal(object)                  # ImageCandidate | None
    overwrite_confirmed = Signal(bool)             # bool


class QtBridge:
    def __init__(self, signals: BridgeSignals):
        self._signals = signals
        self._mutex = QMutex()
        self._wait_condition = QWaitCondition()
        self._pending_result = None

    # ── UserInteraction ──────────────────────────────────────────────────

    def choose_game(self, query: str, candidates: list[GameCandidate]) -> int | None:
        return self._run_dialog(
            lambda: self._signals.choose_game_requested.emit(query, candidates),
            self._signals.game_chosen,
        )

    def choose_image(self, label: str, candidates: list[ImageCandidate]) -> ImageCandidate | None:
        return self._run_dialog(
            lambda: self._signals.choose_image_requested.emit(label, candidates),
            self._signals.image_chosen,
        )

    def confirm_overwrite(self, filename: str) -> bool:
        return self._run_dialog(
            lambda: self._signals.confirm_overwrite_requested.emit(filename),
            self._signals.overwrite_confirmed,
        )

    def log(self, message: str) -> None:
        self._signals.log_signal.emit(message)

    def set_status(self, message: str) -> None:
        self._signals.status_signal.emit(message)

    # ── Interno ──────────────────────────────────────────────────────────

    def _run_dialog(self, emit_fn: Callable[[], None], result_signal: Signal):
        """Bloquea el hilo de fondo hasta que el hilo principal emita el resultado.

        Usa QMutex + QWaitCondition para sincronización entre hilos.
        """
        self._mutex.lock()
        try:
            self._pending_result = None
            # Conectamos temporalmente para recibir el resultado
            result_signal.connect(self._on_result_received, Qt.QueuedConnection)
            emit_fn()
            # Bloqueamos el hilo worker hasta que wakeAll() sea llamado
            while self._pending_result is None:
                self._wait_condition.wait(self._mutex)
            result = self._pending_result
            result_signal.disconnect(self._on_result_received)
            return result
        finally:
            self._mutex.unlock()

    @Slot(object)
    def _on_result_received(self, result):
        """Slot invocado en el hilo worker cuando el main thread emite el resultado."""
        self._mutex.lock()
        try:
            self._pending_result = result
            self._wait_condition.wakeAll()
        finally:
            self._mutex.unlock()