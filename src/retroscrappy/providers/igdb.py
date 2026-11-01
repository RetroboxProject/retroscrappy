"""IGDB (API v4, Twitch app credentials): metadata, covers, screenshots, artworks."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.settings import IGDBAccount, RegionSettings
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

OAUTH_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.igdb.com/v4"
IMAGE_URL = "https://images.igdb.com/igdb/image/upload/{size}/{image_id}.jpg"
SEARCH_LIMIT = 10

#: IGDB release region enum → ScreenScraper-style region codes.
_REGIONS = {1: "eu", 2: "us", 3: "au", 4: "nz", 5: "jp", 6: "cn", 7: "asi", 8: "wor", 9: "kr"}

_DETAIL_FIELDS = (
    "name, summary, genres.name, total_rating, "
    "involved_companies.company.name, involved_companies.developer, "
    "involved_companies.publisher, release_dates.date, release_dates.region, "
    "release_dates.platform, franchises.name, collection.name, "
    "cover.image_id, screenshots.image_id, artworks.image_id"
)


class IGDBProvider(Provider):
    """Metadata and some media from IGDB."""

    key = "igdb"
    label = "IGDB"
    fields = frozenset(
        {
            Field.NAME,
            Field.DESC,
            Field.DEVELOPER,
            Field.PUBLISHER,
            Field.GENRE,
            Field.FAMILY,
            Field.RELEASEDATE,
            Field.RATING,
        }
    )
    media = frozenset({MediaKind.THUMBNAIL, MediaKind.IMAGE, MediaKind.FANART})

    def __init__(self, account: IGDBAccount, region: RegionSettings) -> None:
        self._client_id = account.client_id
        self._client_secret = account.client_secret
        self._regions = [r.lower() for r in region.regions]
        self._session = make_session()
        self._token = ""
        self._token_expiry = 0.0

    # ── HTTP ─────────────────────────────────────────────────────────────

    def _ensure_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry:
            return self._token
        try:
            resp = self._session.post(
                OAUTH_URL,
                params={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"IGDB: network error ({exc.__class__.__name__})") from exc
        if resp.status_code != 200:
            raise ProviderUnavailable(
                f"IGDB: Twitch authentication failed (HTTP {resp.status_code})"
            )
        payload = resp.json()
        self._token = str(payload["access_token"])
        self._token_expiry = time.monotonic() + float(payload.get("expires_in", 3600)) - 60
        return self._token

    def _query(self, endpoint: str, body: str) -> list[dict[str, Any]]:
        headers = {"Client-ID": self._client_id, "Authorization": f"Bearer {self._ensure_token()}"}
        try:
            resp = self._session.post(
                f"{API_URL}/{endpoint}",
                headers=headers,
                data=body.encode(),
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"IGDB: network error ({exc.__class__.__name__})") from exc
        if resp.status_code in (401, 403):
            raise ProviderUnavailable(f"IGDB: access denied (HTTP {resp.status_code})")
        if resp.status_code != 200:
            raise ProviderError(f"IGDB: HTTP {resp.status_code}")
        result = resp.json()
        return result if isinstance(result, list) else []

    def _check(self) -> None:
        if not self._client_id or not self._client_secret:
            raise ProviderUnavailable("IGDB: Twitch client id/secret are missing")
        self._ensure_token()

    # ── Matching ─────────────────────────────────────────────────────────

    def find(self, query: GameQuery) -> list[Match]:
        if not query.name:
            return []
        safe = query.name.replace('"', " ")
        where = ""
        if query.platform.igdb_ids:
            where = f" where platforms = ({','.join(map(str, query.platform.igdb_ids))});"
        body = f'search "{safe}"; fields name, first_release_date;{where} limit {SEARCH_LIMIT};'
        matches = []
        for item in self._query("games", body):
            stamp = item.get("first_release_date")
            matches.append(
                Match(
                    provider=self.key,
                    game_id=str(item["id"]),
                    name=str(item.get("name") or "?"),
                    year=datetime.fromtimestamp(stamp, tz=timezone.utc).year if stamp else None,
                    extra={"platform_ids": query.platform.igdb_ids},
                )
            )
        return promote_exact_name(matches, query.name)

    # ── Data ─────────────────────────────────────────────────────────────

    def fetch(self, match: Match, wanted: set[Field | MediaKind]) -> GameData:
        results = self._query("games", f"fields {_DETAIL_FIELDS}; where id = {match.game_id};")
        if not results:
            return GameData()
        game = results[0]
        platform_ids = set(match.extra.get("platform_ids", ()))
        developers, publishers = _companies(game)
        family = _names(game.get("franchises"))
        rating = game.get("total_rating")
        values = {
            Field.NAME: str(game.get("name") or ""),
            Field.DESC: str(game.get("summary") or "").strip(),
            Field.DEVELOPER: ", ".join(developers),
            Field.PUBLISHER: ", ".join(publishers),
            Field.GENRE: ", ".join(_names(game.get("genres"))),
            Field.FAMILY: (
                family[0] if family else str((game.get("collection") or {}).get("name") or "")
            ),
            Field.RELEASEDATE: self._release_date(game.get("release_dates") or [], platform_ids),
            Field.RATING: f"{min(max(float(rating) / 100.0, 0.0), 1.0):.2f}" if rating else "",
        }
        return GameData(
            fields={k: v for k, v in values.items() if v and k in wanted},
            media={k: v for k, v in _media(game).items() if v and k in wanted},
        )

    def _release_date(self, dates: list[dict[str, Any]], platform_ids: set[int]) -> str:
        dated = [d for d in dates if d.get("date")]
        on_platform = [d for d in dated if d.get("platform") in platform_ids] or dated
        if not on_platform:
            return ""

        def rank(entry: dict[str, Any]) -> tuple[int, int]:
            code = _REGIONS.get(int(entry.get("region") or 0), "")
            order = self._regions.index(code) if code in self._regions else len(self._regions)
            return order, int(entry["date"])

        best = min(on_platform, key=rank)
        return datetime.fromtimestamp(best["date"], tz=timezone.utc).strftime("%Y%m%dT000000")


_IMAGE_SIZES = {
    MediaKind.THUMBNAIL: "t_cover_big",
    MediaKind.IMAGE: "t_screenshot_big",
    MediaKind.FANART: "t_1080p",
}


def _media(game: dict[str, Any]) -> dict[MediaKind, list[MediaCandidate]]:
    cover = (game.get("cover") or {}).get("image_id")
    ids = {
        MediaKind.THUMBNAIL: [cover] if cover else [],
        MediaKind.IMAGE: [s.get("image_id") for s in game.get("screenshots") or []],
        MediaKind.FANART: [a.get("image_id") for a in game.get("artworks") or []],
    }
    return {
        kind: [
            MediaCandidate(
                url=IMAGE_URL.format(size=_IMAGE_SIZES[kind], image_id=image_id),
                thumb_url=IMAGE_URL.format(size="t_thumb", image_id=image_id),
                extension=".jpg",
            )
            for image_id in image_ids
            if image_id
        ]
        for kind, image_ids in ids.items()
    }


def _names(items: Any) -> list[str]:
    return [str(i["name"]) for i in items or [] if isinstance(i, dict) and i.get("name")]


def _companies(game: dict[str, Any]) -> tuple[list[str], list[str]]:
    developers: list[str] = []
    publishers: list[str] = []
    for involved in game.get("involved_companies") or []:
        name = (involved.get("company") or {}).get("name")
        if not name:
            continue
        if involved.get("developer") and name not in developers:
            developers.append(name)
        if involved.get("publisher") and name not in publishers:
            publishers.append(name)
    return developers, publishers
