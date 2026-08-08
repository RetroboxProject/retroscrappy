"""models.py — Estructuras de datos simples compartidas por todo el paquete.

Usar dataclasses en vez de pasar objetos del wrapper `steamgrid` o tuplas
sueltas por toda la aplicación hace que la GUI y la lógica de red no estén
acopladas a la librería externa: si el día de mañana cambia el wrapper de
SteamGridDB, solo hay que tocar sgdb_client.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GameEntry:
    """Una entrada del gamelist.xml a procesar."""
    name: str
    file_stem: str  # stem del fichero launcher; define el prefijo de las imágenes en disco


@dataclass
class GameCandidate:
    """Un resultado de búsqueda de juego en SteamGridDB."""
    id: int
    name: str
    year: int | None = None


@dataclass
class ImageCandidate:
    """Un asset (grid/logo/hero) candidato en SteamGridDB."""
    url: str
    thumb_url: str
    width: int
    height: int
    author: str
    upvotes: int = 0
    downvotes: int = 0
    mime: str = ""
    preview: bytes | None = field(default=None, repr=False)  # bytes de la imagen para previsualizar en la GUI

    @property
    def score(self) -> int:
        return self.upvotes - self.downvotes


@dataclass
class AssetJob:
    """Un asset (thumb/marquee) pendiente de descargar para un juego concreto."""
    key: str            # "thumb" | "marquee"
    dest: Path


@dataclass
class GameMetadata:
    """Metadatos textuales de un juego, listos para volcar a gamelist.xml.
    Todos los campos son opcionales: si IGDB no trae el dato, se deja vacío
    y ese tag del XML simplemente no se toca."""
    developer: str = ""
    publisher: str = ""
    genres: list[str] = field(default_factory=list)
    family: str = ""              # franquicia/saga
    players: str = ""             # heurística aproximada, ver igdb_client.py
    release_date: str = ""        # formato EmulationStation: YYYYMMDDT000000
    release_region: str = ""      # "europe" | "north_america" | "japan" | ... (informativo, para el log)

    def has_data(self) -> bool:
        return any([self.developer, self.publisher, self.genres, self.family, self.players, self.release_date])

@dataclass
class GameMetadata:
    """Metadatos textuales de un juego, listos para volcar a gamelist.xml.
    Todos los campos son opcionales: si la fuente no trae el dato, se deja vacío
    y ese tag del XML simplemente no se toca."""
    developer: str = ""
    publisher: str = ""
    genres: list[str] = field(default_factory=list)
    family: str = ""
    players: str = ""
    release_date: str = ""
    release_region: str = ""
    desc: str = ""
    rating: str = ""
    screenshot_url: str = ""  # media "ss" (SS) / screenshots (IGDB); lo baja el worker de metadatos

    def has_data(self) -> bool:
        return any([
            self.developer, self.publisher, self.genres, self.family,
            self.players, self.release_date, self.desc, self.rating,
            self.screenshot_url,
        ])



@dataclass
class GameDetails:
    """Entrada completa de gamelist.xml para la pantalla de previsualización."""
    name: str
    file_stem: str
    metadata: dict[str, str]   # tag -> texto (genre, desc, releasedate, ...)
    images: dict[str, str]     # xml_tag (thumbnail/marquee/image) -> ruta relativa