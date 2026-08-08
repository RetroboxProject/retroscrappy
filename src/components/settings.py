"""settings.py — Persistencia de opciones en ~/.config/sgdb-scraper/config.ini."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path

from .config import MODE_SEMI, SUPPORTED_SYSTEMS

APP_NAME = "sgdb-scraper"
CONFIG_FILENAME = "config.ini"

# Valores por defecto para los toggles de scraping
_DEFAULT_SYSTEMS = list(SUPPORTED_SYSTEMS)

# Regiones / prioridades posibles para la fecha de lanzamiento
RELEASE_DATE_REGIONS = [
    ("europe", "Europa"),
    ("north_america", "Norteamérica"),
    ("japan", "Japón"),
    ("worldwide", "Mundial"),
    ("oldest", "La más antigua disponible"),
]


@dataclass
class AppSettings:
    # ── General ──────────────────────────────────────────────────────────
    roms: str = ""
    systems: list[str] = field(default_factory=lambda: list(_DEFAULT_SYSTEMS))
    gen_gamelist: bool = True
    mode: str = MODE_SEMI
    force_art: bool = False
    force_meta: bool = False

    # ── Credenciales ─────────────────────────────────────────────────────
    sgdb_apikey: str = ""
    igdb_client_id: str = ""
    igdb_client_secret: str = ""
    ss_devid: str = ""
    ss_devpassword: str = ""
    ss_ssid: str = ""
    ss_sspassword: str = ""

    # ── Elementos a scrapear (toggles) ───────────────────────────────────
    scrape_thumb: bool = True
    scrape_marquee: bool = True
    scrape_screenshot: bool = True
    scrape_desc: bool = True
    scrape_developer: bool = True
    scrape_publisher: bool = True
    scrape_genre: bool = True
    scrape_family: bool = True
    scrape_players: bool = True
    scrape_release_date: bool = True
    scrape_rating: bool = True

    # ── Fuente por elemento ──────────────────────────────────────────────
    # thumb:     sgdb | screenscraper | igdb
    # marquee:   sgdb | screenscraper
    # screenshot:screenscraper | igdb
    # metadata:  igdb | screenscraper
    thumb_source: str = "sgdb"
    marquee_source: str = "sgdb"
    screenshot_source: str = "screenscraper"
    metadata_source: str = "screenscraper"

    # Prioridad de región para la fecha de lanzamiento
    release_date_region: str = "europe"


# ── Localización del fichero ─────────────────────────────────────────────

def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_NAME


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


# ── Lectura ──────────────────────────────────────────────────────────────

_BOOL_KEYS = [
    "gen_gamelist", "force_art", "force_meta",
    "scrape_thumb", "scrape_marquee", "scrape_screenshot",
    "scrape_desc", "scrape_developer", "scrape_publisher",
    "scrape_genre", "scrape_family", "scrape_players",
    "scrape_release_date", "scrape_rating",
]
_STR_KEYS = [
    "roms", "mode",
    "sgdb_apikey", "igdb_client_id", "igdb_client_secret",
    "ss_devid", "ss_devpassword", "ss_ssid", "ss_sspassword",
    "thumb_source", "mar