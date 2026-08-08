"""screenscraper_client.py — Cliente de la API v2 de ScreenScraper.fr.

ScreenScraper es conocido por tener respuestas lentas; el timeout es de 90s
y se reintenta una vez antes de fallar."""

from __future__ import annotations

import re

import requests

from .config import SS_API_URL, SS_SOFTNAME
from .models import GameCandidate, GameMetadata

TIMEOUT = 90  # ScreenScraper puede ser MUY lento; 30s es insuficiente
MAX_RETRIES = 1


class ScreenScraperAuthError(Exception):
    pass


class ScreenScraperClient:
    def __init__(self, devid: str, devpassword: str, ssid: str = "", sspassword: str = ""):
        self._auth = {
            "devid": devid.strip(),
            "devpassword": devpassword.strip(),
            "softname": SS_SOFTNAME,
            "output": "json",
        }
        if ssid.strip():
            self._auth["ssid"] = ssid.strip()
            self._auth["sspassword"] = sspassword.strip()

    # ── HTTP ─────────────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict) -> dict:
        url = f"{SS_API_URL}/{endpoint}"
        last_err = None
        for attempt in range(1 + MAX_RETRIES):
            try:
                resp = requests.get(url, params={**self._auth, **params}, timeout=TIMEOUT)
                break
            except requests.Timeout as e:
                last_err = e
                if attempt < MAX_RETRIES:
                    continue  # reintento
                raise ScreenScraperAuthError(
                    f"ScreenScraper no respondió en {TIMEOUT}s tras {1+MAX_RETRIES} intentos "
                    f"(puede estar saturado o tu conexión ser lenta): {e}"
                )
            except requests.RequestException as e:
                raise ScreenScraperAuthError(
                    f"No se pudo conectar con ScreenScraper ({e.__class__.__name__}): {e}"
                )

        if resp.status_code in (401, 403):
            raise ScreenScraperAuthError(
                f"ScreenScraper rechazó las credenciales (HTTP {resp.status_code}). "
                "Revisa devid/devpassword (y ssid/sspassword si los usas)."
            )
        if resp.status_code != 200:
            raise ScreenScraperAuthError(
                f"ScreenScraper respondió HTTP {resp.status_code}: {(resp.text or '')[:200]}"
            )

        ctype = (resp.headers.get("Content-Type") or "").lower()
        body = resp.text or ""
        try:
            data = resp.json()
        except ValueError:
            snippet = body[:200].strip() or "(cuerpo vacío)"
            raise ScreenScraperAuthError(
                f"ScreenScraper devolvió una respuesta no JSON ({ctype or 'sin content-type'}): {snippet}"
            )

        if isinstance(data, dict) and (data.get("erreur") or data.get("error")):
            raise ScreenScraperAuthError(f"ScreenScraper: {data.get('erreur') or data.get('error')}")
        return (data or {}).get("response", {}) or {}

    def verify_credentials(self) -> None:
        self._get("jeuRecherche.php", {"recherche": "zelda", "maxrecords": "1"})

    # ── Búsqueda ─────────────────────────────────────────────────────────

    def search_games(self, name: str) -> list[GameCandidate]:
        try:
            response = self._get("jeuRecherche.php", {"recherche": name, "maxrecords": "10"})
        except ScreenScraperAuthError:
            raise
        except Exception:
            return []

        out = []
        for jeu in response.get("jeux", []) or []:
            year = None
            for d in jeu.get("dates", []) or []:
                parsed = _parse_ss_date(_date_text(d))
                if parsed:
                    year = int(parsed[:4])
                    break
            out.append(GameCandidate(id=int(jeu["id"]), name=_game_name(jeu), year=year))
        return out

    # ── Metadatos ────────────────────────────────────────────────────────

    def get_metadata(self, game_id: int) -> GameMetadata:
        try:
            response = self._get("jeuInfos.php", {"gameid": str(game_id)})
        except Exception:
            return GameMetadata()

        jeu = response.get("jeu")
        if not jeu:
            return GameMetadata()

        meta = GameMetadata()
        meta.developer = _text(jeu.get("developpeur"))
        meta.publisher = _text(jeu.get("editeur"))
        meta.players = _text(jeu.get("joueurs"))
        meta.genres = [_localized_genre(g) for g in jeu.get("genres", []) or []]
        meta.genres = [g for g in meta.genres if g]

        families = jeu.get("familles", []) or []
        if families:
            meta.family = _text(families[0])

        meta.desc = _localized_synopsis(jeu.get("synopsis", []) or [])
        meta.rating = _normalize_rating(_text(jeu.get("note")))
        meta.screenshot_url = _pick_screenshot(jeu.get("medias", []) or [])
        meta.release_date, meta.release_region = self._pick_release_date(jeu.get("dates", []) or [])
        return meta

    @staticmethod
    def _pick_release_date(dates: list[dict]) -> tuple[str, str]:
        parsed = []
        for d in dates:
            text = _date_text(d)
            es = _parse_ss_date(text)
            if es:
                parsed.append((es, _region_rank(d.get("region")), str(d.get("region", ""))))
        if not parsed:
            return "", ""
        parsed.sort(key=lambda t: (t[1], t[0]))
        best = parsed[0]
        return best[0], best[2] or "desconocida"


# ── Helpers defensivos ───────────────────────────────────────────────────

def _text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _date_text(d: dict) -> str:
    return str(d.get("date") or d.get("texte") or "").strip()


def _parse_ss_date(s: str) -> str:
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", s)
    if not m:
        return ""
    y, mo, da = m.groups()
    return f"{y}{(mo or '01').zfill(2)}{(da or '01').zfill(2)}T000000"


def _region_rank(region) -> int:
    s = str(region).lower()
    if any(k in s for k in ("eu", "fr")):
        return 0
    if "us" in s or s == "2":
        return 1
    if "jp" in s or "jap" in s:
        return 2
    if "wor" in s or "world" in s:
        return 3
    return 4


def _localized_synopsis(synopsis: list) -> str:
    if not synopsis:
        return ""
    by_lang = {s.get("langue", ""): s.get("text", "") for s in synopsis if isinstance(s, dict)}
    return (by_lang.get("es") or by_lang.get("en") or synopsis[0].get("text", "")).strip()


def _localized_genre(genre: dict) -> str:
    for n in genre.get("noms", []) or []:
        if n.get("langue") in ("es", "en"):
            return (n.get("text") or "").strip()
    return _text(genre)


def _normalize_rating(note: str) -> str:
    m = re.match(r"^(\d+(?:\.\d+)?)", note)
    if not m:
        return ""
    try:
        value = float(m.group(1))
    except ValueError:
        return ""
    if value > 1:
        value = value / 20.0
    return f"{min(max(value, 0.0), 1.0):.2f}"

def _game_name(jeu: dict) -> str:
    """El nombre puede venir en 'nom' o en la tabla localizada 'noms'/'names'."""
    name = jeu.get("nom")
    if isinstance(name, str) and name.strip():
        return name.strip()
    for key in ("noms", "names"):
        for n in jeu.get(key, []) or []:
            if isinstance(n, dict):
                cand = n.get("name") or n.get("text") or n.get("nom")
            else:
                cand = n
            if isinstance(cand, str) and cand.strip():
                return cand.strip()
    return "?"


def _pick_screenshot(medias: list) -> str:
    """Prefiere el screenshot in-game ('ss'); si no, el de título ('sstitle')."""
    title = ""
    for m in medias:
        if not isinstance(m, dict):
            continue
        url = m.get("url") or ""
        if not url:
            continue
        mtype = m.get("type") or ""
        if mtype == "ss":
            return url
        if mtype == "sstitle" and not title:
            title = url
    return title
