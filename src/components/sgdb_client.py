"""sgdb_client.py — Envoltorio sobre el paquete `steamgrid`.

Toda la interacción con la librería externa vive aquí, y sale convertida a
los dataclasses de models.py. El resto de la aplicación (worker, GUI) nunca
importa `steamgrid` directamente, así que si esa librería cambia solo hay
que tocar este fichero.
"""

from __future__ import annotations

from steamgrid import Grid, SteamGridDB

from .config import GRID_PREFERRED_DIMS
from .models import GameCandidate, ImageCandidate


class SGDBClient:
    def __init__(self, api_key: str):
        self._client = SteamGridDB(api_key)

    # ── Búsqueda de juego ────────────────────────────────────────────────

    def search_games(self, name: str) -> list[GameCandidate]:
        try:
            results = self._client.search_game(name)
        except Exception:
            return []
        if not results:
            return []
        out = []
        for r in results:
            year = r.release_date.year if getattr(r, "release_date", None) else None
            out.append(GameCandidate(id=r.id, name=r.name, year=year))
        return out

    # ── Obtención de assets ──────────────────────────────────────────────

    def get_assets(self, game_id: int, fetch_type: str, limit: int) -> list[ImageCandidate]:
        """
        Devuelve hasta `limit` assets PNG estáticos para game_id.

        Para grids:
          1. Pide solo 600×900 (GRID_PREFERRED_DIMS) a la API.
          2. Si no hay resultados, cualquier dimensión filtrando ratio 2:3.
          3. Si tampoco hay ratio 2:3, cualquier PNG estático.

        Para logos/heroes: descarga todo y filtra PNG estáticos manualmente
        (el wrapper tiene un bug de espacio final en ImageType.Static).
        """
        try:
            if fetch_type == "grids":
                items = self._fetch_raw_grids(game_id, {"dimensions": GRID_PREFERRED_DIMS})
                items = [a for a in items if self._is_static_png(a)]

                if not items:
                    all_items = self._fetch_raw_grids(game_id, {})
                    png_items = [a for a in all_items if self._is_static_png(a)]
                    items = [a for a in png_items if self._is_2_3_ratio(a)]
                    if not items:
                        items = png_items  # fallback final: cualquier PNG

            elif fetch_type == "logos":
                raw = self._client.get_logos_by_gameid([game_id])
                items = [a for a in (raw or []) if self._is_static_png(a)]

            elif fetch_type == "heroes":
                raw = self._client.get_heroes_by_gameid([game_id])
                items = [a for a in (raw or []) if self._is_static_png(a)]

            else:
                return []

            candidates = [self._to_candidate(a) for a in items[:limit]]
            return sorted(candidates, key=lambda c: c.score, reverse=True)

        except Exception:
            return []

    # ── Helpers internos ─────────────────────────────────────────────────

    def _fetch_raw_grids(self, game_id: int, extra_queries: dict) -> list:
        """
        Llama directamente a _http.get_grid() para poder inyectar parámetros
        extra (como dimensions=600x900) que la API pública del wrapper no
        expone.
        """
        try:
            payloads = self._client._http.get_grid(
                [game_id], "game",
                queries={"nsfw": "false", "humor": "false", **extra_queries},
            )
            if payloads:
                return [Grid(p, self._client._http) for p in payloads]
        except Exception:
            pass
        return []

    @staticmethod
    def _is_static_png(asset) -> bool:
        """Descarta WebP y GIF; acepta PNG o mime vacío (la URL manda)."""
        mime = (getattr(asset, "mime", "") or "").lower()
        url = (getattr(asset, "url", "") or "").lower()
        if mime and "png" not in mime:
            return False
        if url.endswith((".webp", ".gif")):
            return False
        return True

    @staticmethod
    def _is_2_3_ratio(asset) -> bool:
        w = getattr(asset, "width", 0) or 0
        h = getattr(asset, "height", 0) or 0
        if not w or not h:
            return False
        return abs((w / h) - (2 / 3)) < 0.05

    @staticmethod
    def _to_candidate(asset) -> ImageCandidate:
        author = asset.author.name if getattr(asset, "author", None) else "?"
        return ImageCandidate(
            url=asset.url,
            # SGDB ya sirve una miniatura pequeña ("thumb"); si no viene, se
            # cae a la url completa (peor caso, pero sigue funcionando).
            thumb_url=getattr(asset, "thumbnail", None) or asset.url,
            width=asset.width or 0,
            height=asset.height or 0,
            author=author,
            upvotes=getattr(asset, "upvotes", 0) or 0,
            downvotes=getattr(asset, "downvotes", 0) or 0,
            mime=getattr(asset, "mime", "") or "",
        )
