"""igdb_client.py — Envoltorio sobre la API REST de IGDB (v4).

IGDB usa credenciales de aplicación de Twitch (Client ID + Client Secret,
gratis e instantáneas en https://dev.twitch.tv/console/apps). No hay
wrapper de terceros que merezca la pena aquí, así que hablamos directo con
la API vía `requests` y el lenguaje de consulta Apicalypse.

Como con sgdb_client.py: toda la conversión a nuestros dataclasses vive
aquí, para que worker.py y la GUI no sepan nada de la forma de la API.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from .config import (
    IGDB_API_URL,
    IGDB_OAUTH_URL,
    IGDB_PC_PLATFORM_IDS,
    IGDB_REGION_NAMES,
    IGDB_REGION_PRIORITY,
    TOP_N_GAME_SEARCH,
)
from .models import GameCandidate, GameMetadata

TIMEOUT = 30


class IGDBAuthError(Exception):
    pass


class IGDBClient:
    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ── Autenticación ────────────────────────────────────────────────────

    def _ensure_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        resp = requests.post(
            IGDB_OAUTH_URL,
            params={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            },
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            raise IGDBAuthError(
                f"No se pudo autenticar en Twitch/IGDB ({resp.status_code}): {resp.text[:200]}"
            )
        data = resp.json()
        self._token = data["access_token"]
        # Restamos un margen de 60s para no usar un token a punto de caducar.
        self._token_expires_at = time.monotonic() + data.get("expires_in", 3600) - 60
        return self._token

    def _headers(self) -> dict:
        return {
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {self._ensure_token()}",
        }

    def _query(self, endpoint: str, apicalypse_body: str) -> list[dict]:
        resp = requests.post(
            f"{IGDB_API_URL}/{endpoint}",
            headers=self._headers(),
            data=apicalypse_body,
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        return resp.json() or []

    # ── Búsqueda de juego ────────────────────────────────────────────────

    def search_games(self, name: str) -> list[GameCandidate]:
        safe_name = name.replace('"', "'")
        body = (
            f'search "{safe_name}"; '
            f"fields name,first_release_date; "
            f"limit {TOP_N_GAME_SEARCH};"
        )
        results = self._query("games", body)
        out = []
        for r in results:
            year = None
            ts = r.get("first_release_date")
            if ts:
                year = datetime.fromtimestamp(ts, tz=timezone.utc).year
            out.append(GameCandidate(id=r["id"], name=r["name"], year=year))
        return out

    # ── Metadatos completos ──────────────────────────────────────────────

    def get_metadata(self, game_id: int) -> GameMetadata:
        body = (
            "fields name, genres.name, "
            "involved_companies.company.name, involved_companies.developer, involved_companies.publisher, "
            "release_dates.date, release_dates.region, release_dates.platform, "
            "franchises.name, collection.name, "
            "screenshots.image_id, screenshots.url; "
            f"where id = {game_id};"
        )
        results = self._query("games", body)
        if not results:
            return GameMetadata()

        game = results[0]
        meta = GameMetadata()
        # ... existing code (genres, devs/pubs, family, release_date) ...

        # Screenshot: preferimos construir la URL con tamaño grande a partir del image_id
        shots = game.get("screenshots", []) or []
        if shots:
            img_id = shots[0].get("image_id")
            if img_id:
                meta.screenshot_url = f"https://images.igdb.com/igdb/image/upload/t_screenshot_big/{img_id}.jpg"

        return meta

    # ── Helpers internos ─────────────────────────────────────────────────

    @staticmethod
    def _pick_release_date(release_dates: list[dict]) -> tuple[str, str]:
        """Elige la fecha de lanzamiento en PC según la prioridad de región
        configurada (IGDB_REGION_PRIORITY). Si no hay ninguna en PC/región
        preferida, cae a la fecha más antigua disponible como último recurso.
        """
        pc_dates = [d for d in release_dates if d.get("platform") in IGDB_PC_PLATFORM_IDS and d.get("date")]
        candidates = pc_dates or [d for d in release_dates if d.get("date")]
        if not candidates:
            return "", ""

        for region in IGDB_REGION_PRIORITY:
            match = next((d for d in candidates if d.get("region") == region), None)
            if match:
                return _format_es_date(match["date"]), IGDB_REGION_NAMES.get(region, "")

        # Ninguna región de la lista de prioridad: la fecha más antigua conocida.
        earliest = min(candidates, key=lambda d: d["date"])
        return _format_es_date(earliest["date"]), IGDB_REGION_NAMES.get(earliest.get("region"), "desconocida")


def _format_es_date(unix_ts: int) -> str:
    """Convierte un timestamp unix al formato de fecha de EmulationStation: YYYYMMDDT000000."""
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y%m%dT000000")