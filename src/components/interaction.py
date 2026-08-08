"""interaction.py — Contrato entre la lógica de negocio (worker.py) y la GUI.

worker.py NUNCA importa tkinter: solo conoce este Protocol. Eso permite:
  - testear worker.py con un stub/mock sin abrir ninguna ventana,
  - cambiar de tkinter a otro toolkit el día de mañana tocando solo gui/.
"""

from __future__ import annotations

from typing import Protocol

from .models import GameCandidate, ImageCandidate


class UserInteraction(Protocol):
    def choose_game(self, query: str, candidates: list[GameCandidate]) -> int | None:
        """Debe devolver el id elegido, o None si el usuario decide saltar el juego."""
        ...

    def choose_image(self, label: str, candidates: list[ImageCandidate]) -> ImageCandidate | None:
        """Debe devolver el candidato elegido, o None si el usuario decide saltarlo."""
        ...

    def confirm_overwrite(self, filename: str) -> bool:
        """Debe devolver True si hay que sobreescribir un archivo ya existente."""
        ...

    def log(self, message: str) -> None:
        ...

    def set_status(self, message: str) -> None:
        ...
