"""ScreenScraper.fr (API v2).

ROMs are identified by system + file name + size + hashes first (exact
match, the same way Batocera's built-in scraper does it) and by name search
only as a fallback.
"""

from __future__ import annotations

import hashlib
import re
import zlib
from pathlib import Path
from typing import Any

import requests

from retroscrappy.core.items import Field, MediaKind
from retroscrappy.core.logs import get_logger
from retroscrappy.core.names import title_from_filename
from retroscrappy.core.settings import RegionSettings, ScreenScraperAccount
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
from retroscrappy.providers.http import make_session

_log = get_logger("screenscraper")

API_URL = "https://api.screenscraper.fr/api2"
SOFTNAME = "retroscrappy"
TIMEOUT = 90  # ScreenScraper is often slow under load
HASH_CHUNK = 1 << 20

#: HTTP statuses after which the provider is useless for the rest of the run.
_FATAL_STATUSES = {
    401: "API closed for non-members (server overloaded)",
    403: "developer credentials rejected",
    423: "API closed",
    426: "this software is blacklisted",
    430: "daily quota exceeded",
    431: "too many unrecognised ROMs today",
}

#: ScreenScraper media types per kind, most preferred first.
_MEDIA_TYPES: dict[MediaKind, tuple[str, ...]] = {
    MediaKind.IMAGE: ("ss",),
    MediaKind.TITLESHOT: ("sstitle",),
    MediaKind.THUMBNAIL: ("box-2D",),
    MediaKind.MARQUEE: ("wheel-hd", "wheel"),
    MediaKind.FANART: ("fanart",),
    MediaKind.BOXBACK: ("box-2D-back",),
    MediaKind.VIDEO: ("video-normalized", "video"),
    MediaKind.MANUAL: ("manuel",),
}

_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?")


class ScreenScraperProvider(Provider):
    """Metadata and media from ScreenScraper."""

    key = "screenscraper"
    label = "ScreenScraper"
    fields = frozenset(Field)
    media = frozenset(MediaKind)

    def __init__(
        self, account: ScreenScraperAccount, region: RegionSettings, hash_max_mb: int = 128
    ) -> None:
        self._auth = {
            "devid": account.dev_id,
            "devpassword": account.dev_password,
            "softname": SOFTNAME,
            "output": "json",
        }
        if account.username:
            self._auth["ssid"] = account.username
            self._auth["sspassword"] = account.password
        self._regions = [r.lower() for r in region.regions]
        self._languages = [lang.lower() for lang in region.languages]
        self._hash_max_bytes = max(hash_max_mb, 0) * 1024 * 1024
        self._session = make_session()

    # ── HTTP ─────────────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict[str, str]) -> dict[str, Any] | None:
        """``response`` object of a call, or ``None`` when nothing was found."""
        try:
            resp = self._session.get(
                f"{API_URL}/{endpoint}", params={**self._auth, **params}, timeout=TIMEOUT
            )
        except requests.RequestException as exc:
            raise ProviderError(f"network error: {exc.__class__.__name__}") from exc

        if resp.status_code == 404:
            return None
        if resp.status_code in _FATAL_STATUSES:
            raise ProviderUnavailable(
                f"ScreenScraper: {_FATAL_STATUSES[resp.status_code]} (HTTP {resp.status_code})"
            )
        if resp.status_code == 429:
            raise ProviderError("ScreenScraper: too many simultaneous requests")
        if resp.status_code != 200:
            raise ProviderError(f"ScreenScraper: HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("ScreenScraper: invalid (non-JSON) response") from exc
        return (data or {}).get("response") or None

    def _check(self) -> None:
        if not self._auth["devid"] or not self._auth["devpassword"]:
            raise ProviderUnavailable("ScreenScraper: developer credentials are missing")
        endpoint = "ssuserInfos.php" if "ssid" in self._auth else "jeuRecherche.php"
        self._get(endpoint, {"recherche": "sonic", "systemeid": "1"})

    # ── Matching ─────────────────────────────────────────────────────────

    def find(self, query: GameQuery) -> list[Match]:
        exact = self._find_by_file(query)
        if exact:
            return [exact]
        return self._find_by_name(query)

    def _find_by_file(self, query: GameQuery) -> Match | None:
        rom = query.rom_path
        params = {"romtype": "rom", "romnom": query.file_name}
        if query.platform.screenscraper_id:
            params["systemeid"] = str(query.platform.screenscraper_id)
        if rom.is_file():
            size = rom.stat().st_size
            params["romtaille"] = str(size)
            if size <= self._hash_max_bytes:
                params.update(_hashes(rom))
        response = self._get("jeuInfos.php", params)
        game = (response or {}).get("jeu")
        if not game or not game.get("id"):
            return None
        return self._to_match(game, exact=True, keep_payload=True)

    def _find_by_name(self, query: GameQuery) -> list[Match]:
        params = {"recherche": query.name or title_from_filename(Path(query.rel_path).stem)}
        if query.platform.screenscraper_id:
            params["systemeid"] = str(query.platform.screenscraper_id)
        response = self._get("jeuRecherche.php", params) or {}
        matches = [
            self._to_match(game, exact=False, keep_payload=False)
            for game in response.get("jeux") or []
            if isinstance(game, dict) and game.get("id")
        ]
        return promote_exact_name(matches, params["recherche"])

    def _to_match(self, game: dict[str, Any], exact: bool, keep_payload: bool) -> Match:
        date = _parse_date(self._by_region(game.get("dates")))
        return Match(
            provider=self.key,
            game_id=str(game["id"]),
            name=self._by_region(game.get("noms")) or str(game.get("nom") or "?"),
            year=int(date[:4]) if date else None,
            exact=exact,
            extra={"jeu": game} if keep_payload else {},
        )

    # ── Data ─────────────────────────────────────────────────────────────

    def fetch(self, match: Match, wanted: set[Field | MediaKind]) -> GameData:
        game = match.extra.get("jeu")
        if game is None:
            response = self._get("jeuInfos.php", {"gameid": match.game_id})
            game = (response or {}).get("jeu")
        if not game:
            return GameData()

        data = GameData()
        values = {
            Field.NAME: match.name,
            Field.DESC: self._by_language(game.get("synopsis")),
            Field.DEVELOPER: _text(game.get("developpeur")),
            Field.PUBLISHER: _text(game.get("editeur")),
            Field.GENRE: ", ".join(self._localized_names(game.get("genres"))),
            Field.FAMILY: next(iter(self._localized_names(game.get("familles"))), ""),
            Field.PLAYERS: _text(game.get("joueurs")),
            Field.RELEASEDATE: _parse_date(self._by_region(game.get("dates"))),
            Field.RATING: _rating(_text(game.get("note"))),
        }
        data.fields = {k: v for k, v in values.items() if v and k in wanted}

        medias = [m for m in game.get("medias") or [] if isinstance(m, dict) and m.get("url")]
        for kind, types in _MEDIA_TYPES.items():
            if kind in wanted:
                candidates = self._media_candidates(medias, types)
                if candidates:
                    data.media[kind] = candidates
        return data

    def _media_candidates(self, medias: list[dict[str, Any]], types: tuple[str, ...]) -> list:
        ranked = []
        for media in medias:
            mtype = media.get("type", "")
            if mtype not in types:
                continue
            region = str(media.get("region") or "")
            fmt = str(media.get("format") or "").lower()
            ranked.append(
                (
                    types.index(mtype),
                    self._region_rank(region),
                    MediaCandidate(
                        url=media["url"],
                        thumb_url=media["url"],
                        note=region or "?",
                        extension=f".{fmt}" if fmt else "",
                    ),
                )
            )
        ranked.sort(key=lambda t: (t[0], t[1]))
        return [candidate for _, _, candidate in ranked]

    # ── Localisation helpers ─────────────────────────────────────────────

    def _region_rank(self, region: str) -> int:
        region = region.lower()
        if region in self._regions:
            return self._regions.index(region)
        return len(self._regions) + (0 if region in ("wor", "ss") else 1)

    def _by_region(self, items: Any) -> str:
        """Text of the entry whose ``region`` ranks best."""
        entries = [i for i in items or [] if isinstance(i, dict) and i.get("text")]
        if not entries:
            return ""
        best = min(entries, key=lambda i: self._region_rank(str(i.get("region") or "")))
        return str(best["text"]).strip()

    def _by_language(self, items: Any) -> str:
        """Text in the first available preferred language, then English, then anything."""
        entries = {
            str(i.get("langue") or ""): str(i.get("text") or "")
            for i in items or []
            if isinstance(i, dict)
        }
        for lang in (*self._languages, "en"):
            if entries.get(lang):
                return entries[lang].strip()
        return next((t.strip() for t in entries.values() if t.strip()), "")

    def _localized_names(self, groups: Any) -> list[str]:
        names: list[str] = []
        for group in groups or []:
            if isinstance(group, dict):
                name = self._by_language(group.get("noms")) or _text(group)
                if name and name not in names:
                    names.append(name)
        return names


# ── Module helpers ───────────────────────────────────────────────────────


def _hashes(path: Path) -> dict[str, str]:
    crc = 0
    md5 = hashlib.md5(usedforsecurity=False)
    sha1 = hashlib.sha1(usedforsecurity=False)
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(HASH_CHUNK):
                crc = zlib.crc32(chunk, crc)
                md5.update(chunk)
                sha1.update(chunk)
    except OSError as exc:
        _log.debug("Cannot hash %s: %s", path, exc)
        return {}
    return {"crc": f"{crc & 0xFFFFFFFF:08X}", "md5": md5.hexdigest(), "sha1": sha1.hexdigest()}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return value.strip() if isinstance(value, str) else ""


def _parse_date(text: str) -> str:
    """``1992-11-21`` → ``19921121T000000`` (EmulationStation format)."""
    match = _DATE_RE.match(text or "")
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}{(month or '01').zfill(2)}{(day or '01').zfill(2)}T000000"


def _rating(note: str) -> str:
    """ScreenScraper rates out of 20; EmulationStation wants 0..1."""
    try:
        value = float(note)
    except ValueError:
        return ""
    return f"{min(max(value / 20.0, 0.0), 1.0):.2f}"
