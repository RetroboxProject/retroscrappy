"""sgdb_client.py — Envoltorio sobre el paquete `steamgrid` + llamadas directas
a la API REST v2 de SteamGridDB para los screenshots."""

from __future__ import annotations

from typing import Callable

import requests
from steamgrid import Grid, SteamGridDB

from .config import GRID_PREFERRED_DIMS
from .models import GameCandidate, ImageCandidate

SGDB_API_URL = "https://www.steamgriddb.com/api/v2"
TIMEOUT = 30


class SGDBClient:
    def __init__(self, api_key: str, log: Callable[[str], None] | None = None):
        self._api_key = api_key
        self._client = SteamGridDB(api_key)
        self._log = log or (lambda m: None)

    # ── Búsqueda de juego ────────────────────────────────────────────────

    def search_games(self, name: str) -> list[GameCandidate]:
        try:
            results = self._client.search_game(name)
        except Exception:
            return []
        if not results:
            return []

        # Desduplicar por id: el wrapper a veces devuelve el mismo juego
        # varias veces (mismo nombre, a veces con IDs distintos para ports).
        seen: dict[int, GameCandidate] = {}
        for r in results:
            year = r.release_date.year if getattr(r, "release_date", None) else None
            if r.id not in seen:
                seen[r.id] = GameCandidate(id=r.id, name=r.name, year=year)
        return list(seen.values())

    # ── Obtención de assets ──────────────────────────────────────────────

    def get_assets(self, game_id: int, fetch_type: str, limit: int) -> list[ImageCandidate]:
        if fetch_type == "screenshots":
            return self._fetch_screenshots(game_id, limit)

        try:
            if fetch_type == "grids":
                items = self._fetch_raw_grids(game_id, {"dimensions": GRID_PREFERRED_DIMS})
                items = [a for a in items if self._is_static_png(a)]

                if not items:
                    all_items = self._fetch_raw_grids(game_id, {})
                    png_items = [a for a in all_items if self._is_static_png(a)]
                    items = [a for a in png_items if self._is_2_3_ratio(a)]
                    if not items:
                        items = png_items

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

    # ── Screenshots vía API REST v2 ──────────────────────────────────────

    def _fetch_screenshots(self, game_id: int, limit: int) -> list[ImageCandidate]:
        url = f"{SGDB_API_URL}/screenshots/game/{game_id}"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                params={"limit": max(limit * 2, 20)},
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            self._log(f"  ✗ Screenshots: fallo de red ({e.__class__.__name__}: {e})")
            return []

        if resp.status_code == 404:
            # juego sin screenshots curadas en SGDB, no es un error
            self._log(f"  · Screenshots: este juego no tiene screenshots curadas en SGDB")
            return []
        if resp.status_code != 200:
            self._log(f"  ✗ Screenshots: HTTP {resp.status_code} — {(resp.text or '')[:150]}")
            return []

        try:
            payload = resp.json()
        except ValueError:
            self._log(f"  ✗ Screenshots: respuesta no JSON — {(resp.text or '')[:150]}")
            return []

        raw_items = payload.get("data") or []
        if not raw_items:
            self._log(f"  · Screenshots: SGDB no tiene screenshots para este juego")
            return []

        candidates = []
        discarded = 0
        for s in raw_items:
            asset_url = s.get("url") or ""
            mime = (s.get("mime") or "").lower()
            if not asset_url:
                continue
            # descarta animados/vídeo
            lower_url = asset_url.lower()
            if lower_url.endswith((".webm", ".gif", ".webp", ".mp4", ".avi", ".mov")):
                discarded += 1
                continue
            if mime and not mime.startswith("image/"):
                discarded += 1
                continue
            candidates.append(ImageCandidate(
                url=asset_url,
                thumb_url=s.get("thumb") or asset_url,
                width=s.get("width") or 0,
                height=s.get("height") or 0,
                author=(s.get("author") or {}).get("name") or "?",
                upvotes=s.get("upvotes") or 0,
                downvotes=s.get("downvotes") or 0,
                mime=mime,
            ))

        if not candidates and discarded:
            self._log(f"  · Screenshots: {discarded} candidatos descartados por ser vídeo/animados")
        return sorted(candidates, key=lambda c: c.score, reverse=True)[:limit]

    # ── Helpers internos ─────────────────────────────────────────────────

    def _fetch_raw_grids(self, game_id: int, extra_queries: dict) -> list:
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
            thumb_url=getattr(asset, "thumbnail", None) or asset.url,
            width=asset.width or 0,
            height=asset.height or 0,
            author=author,
            upvotes=getattr(asset, "upvotes", 0) or 0,
            downvotes=getattr(asset, "downvotes", 0) or 0,
            mime=getattr(asset, "mime", "") or "",
        )