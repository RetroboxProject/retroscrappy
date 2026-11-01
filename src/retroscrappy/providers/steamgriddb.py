"""SteamGridDB (REST API v2): covers, logos and heroes, mostly for PC games."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.settings import SteamGridDBAccount
from retroscrappy.providers.base import (
    GameData,
    GameQuery,
    Match,
    MediaCandidate,
    Provider,
    ProviderError,
    ProviderUnavailable,
    promote_exact_name,
)
from retroscrappy.providers.http import DEFAULT_TIMEOUT, make_session

API_URL = "https://www.steamgriddb.com/api/v2"
MAX_RESULTS = 20

#: Endpoint and filters per media kind. Grids are restricted to the
#: vertical 2:3 sizes that EmulationStation themes expect for thumbnails.
_ENDPOINTS: dict[MediaKind, tuple[str, dict[str, str]]] = {
    MediaKind.THUMBNAIL: ("grids", {"dimensions": "600x900,342x482,660x930"}),
    MediaKind.MARQUEE: ("logos", {}),
    MediaKind.FANART: ("heroes", {}),
}
_COMMON_FILTERS = {"types": "static", "nsfw": "false", "humor": "false"}
_STATIC_MIMES = ("image/png", "image/jpeg")


class SteamGridDBProvider(Provider):
    """Artwork from SteamGridDB."""

    key = "steamgriddb"
    label = "SteamGridDB"
    fields = frozenset()
    media = frozenset(_ENDPOINTS)

    def __init__(self, account: SteamGridDBAccount) -> None:
        self._session = make_session()
        self._session.headers["Authorization"] = f"Bearer {account.api_key}"
        self._has_key = bool(account.api_key)

    def _get(self, path: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        try:
            resp = self._session.get(f"{API_URL}/{path}", params=params, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            raise ProviderError(f"SteamGridDB: network error ({exc.__class__.__name__})") from exc
        if resp.status_code == 401:
            raise ProviderUnavailable("SteamGridDB: API key rejected")
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise ProviderError(f"SteamGridDB: HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProviderError("SteamGridDB: invalid response") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, list) else []

    def _check(self) -> None:
        if not self._has_key:
            raise ProviderUnavailable("SteamGridDB: API key is missing")
        self._get("search/autocomplete/sonic")

    def find(self, query: GameQuery) -> list[Match]:
        if not query.name:
            return []
        results = self._get(f"search/autocomplete/{quote(query.name, safe='')}")
        matches: dict[str, Match] = {}
        for item in results:
            game_id = str(item.get("id") or "")
            if not game_id or game_id in matches:
                continue
            stamp = item.get("release_date")
            year = datetime.fromtimestamp(stamp, tz=timezone.utc).year if stamp else None
            matches[game_id] = Match(
                provider=self.key, game_id=game_id, name=str(item.get("name") or "?"), year=year
            )
        return promote_exact_name(list(matches.values()), query.name)

    def fetch(self, match: Match, wanted: set[Field | MediaKind]) -> GameData:
        data = GameData()
        for kind, (endpoint, filters) in _ENDPOINTS.items():
            if kind not in wanted:
                continue
            items = self._get(f"{endpoint}/game/{match.game_id}", {**_COMMON_FILTERS, **filters})
            candidates = [_to_candidate(i) for i in items if _is_static(i)]
            candidates.sort(key=lambda c: c.score or 0, reverse=True)
            if candidates:
                data.media[kind] = candidates[:MAX_RESULTS]
        return data


def _is_static(item: dict[str, Any]) -> bool:
    mime = str(item.get("mime") or "").lower()
    return bool(item.get("url")) and (not mime or mime in _STATIC_MIMES)


def _to_candidate(item: dict[str, Any]) -> MediaCandidate:
    author = (item.get("author") or {}).get("name") or ""
    return MediaCandidate(
        url=str(item["url"]),
        thumb_url=str(item.get("thumb") or item["url"]),
        width=int(item.get("width") or 0),
        height=int(item.get("height") or 0),
        score=int(item.get("upvotes") or 0) - int(item.get("downvotes") or 0),
        note=author,
    )
