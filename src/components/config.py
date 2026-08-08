"""
config.py — Constantes compartidas por todo el paquete.

Tener todo esto en un único sitio evita "números mágicos" repartidos por el
código y hace trivial ajustar el comportamiento (p.ej. añadir un nuevo
sistema, o cambiar cuántos candidatos se muestran) sin tocar la lógica.
"""

from __future__ import annotations

# Sistemas que este script sabe procesar (subcarpetas de roms/)
SUPPORTED_SYSTEMS = ["steam", "heroic", "lutris"]

# Nombres de "juego" ficticios que crean los launchers y que hay que ignorar
LAUNCHER_NAMES = {"battle.net", "ubisoft connect", "epic games"}

# Cuántos candidatos se piden a la API / se muestran al usuario
TOP_N_AUTO = 3            # modo automática: el mejor de estos N por score neto
TOP_N_INTERACTIVE = 10    # modo interactivo: se muestran hasta N para elegir

# Dimensiones preferidas para grids (cover vertical de EmulationStation)
GRID_PREFERRED_DIMS = "600x900"

# Tipos de asset gestionados por este script.
#   xml_tag : etiqueta en gamelist.xml
#   suffix  : sufijo del archivo en disco (sobre clean_name())
#   fetch   : tipo de asset en la API de SteamGridDB ("grids"|"logos"|"heroes"|"screenshots")
ASSET_DEFS = {
    "thumb": {
        "xml_tag": "thumbnail",
        "suffix": "-thumb.png",
        "label": "Thumb / Cover (grid vertical 2:3)",
        "fetch": "grids",
        "provider": "sgdb",
    },
    "marquee": {
        "xml_tag": "marquee",
        "suffix": "-marquee.png",
        "label": "Marquee / Logo",
        "fetch": "logos",
        "provider": "sgdb",
    },
    "image": {
        "xml_tag": "image",
        "suffix": "-screenshot.jpg",
        "label": "Screenshot (imagen de gameplay)",
        "fetch": "screenshots",
        "provider": "metadata",  # lo sirve la fuente de metadatos (SS/IGDB), no SGDB
    },
}


# ── IGDB (metadatos textuales) ────────────────────────────────────────────

IGDB_OAUTH_URL = "https://id.twitch.tv/oauth2/token"
IGDB_API_URL = "https://api.igdb.com/v4"

IGDB_REGION_EUROPE = 1
IGDB_REGION_NORTH_AMERICA = 2
IGDB_REGION_AUSTRALIA = 3
IGDB_REGION_NEW_ZEALAND = 4
IGDB_REGION_JAPAN = 5
IGDB_REGION_CHINA = 6
IGDB_REGION_ASIA = 7
IGDB_REGION_WORLDWIDE = 8

IGDB_REGION_NAMES = {
    IGDB_REGION_EUROPE: "europe",
    IGDB_REGION_NORTH_AMERICA: "north_america",
    IGDB_REGION_AUSTRALIA: "australia",
    IGDB_REGION_NEW_ZEALAND: "new_zealand",
    IGDB_REGION_JAPAN: "japan",
    IGDB_REGION_CHINA: "china",
    IGDB_REGION_ASIA: "asia",
    IGDB_REGION_WORLDWIDE: "worldwide",
}

IGDB_REGION_PRIORITY = [
    IGDB_REGION_EUROPE,
    IGDB_REGION_NORTH_AMERICA,
    IGDB_REGION_JAPAN,
    IGDB_REGION_WORLDWIDE,
]

# IDs de plataforma IGDB relevantes para steam/heroic/lutris (todo PC).
# 6 = PC (Microsoft Windows), 3 = Linux, 14 = Mac
IGDB_PC_PLATFORM_IDS = [6, 3, 14]

TOP_N_GAME_SEARCH = 10  # candidatos a mostrar al desambiguar un juego

# ── Generación de gamelist.xml desde cero ────────────────────────────────
# Extensión de los ficheros launcher de cada sistema; el stem es la fuente
# canónica del nombre en disco (prefijo de imágenes y <path> del XML).
SYSTEM_LAUNCHER_EXTENSIONS = {
    "steam": ".steam",
    "heroic": ".heroic",
    "lutris": ".lynx",
}

# ── Modos de interacción ─────────────────────────────────────────────────
MODE_AUTO = "auto"      # nunca pregunta: coincidencia exacta o el 1er candidato
MODE_SEMI = "semi"      # solo pregunta si detecta un posible conflicto
MODE_MANUAL = "manual"  # siempre pregunta (juego y galería de imágenes)
MODES = [MODE_AUTO, MODE_SEMI, MODE_MANUAL]
MODE_LABELS = {
    MODE_AUTO: "Full automático (sin preguntas; riesgo de scrape erróneo con nombres difusos)",
    MODE_SEMI: "Semi-automático (solo interviene si hay posible conflicto)",
    MODE_MANUAL: "Full manual (elegir siempre juego e imágenes)",
}
# Semi: si la diferencia de score entre el 1º y el 2º asset es <= este margen,
# se considera conflicto y se muestra la galería.
SEMI_SCORE_MARGIN = 3

# ── Fuentes de metadatos textuales ───────────────────────────────────────
SOURCE_NONE = "none"
SOURCE_IGDB = "igdb"
SOURCE_SCREENSCRAPER = "screenscraper"
METADATA_SOURCES = [SOURCE_NONE, SOURCE_IGDB, SOURCE_SCREENSCRAPER]
METADATA_SOURCE_LABELS = {
    SOURCE_NONE: "(no scrapear texto)",
    SOURCE_IGDB: "IGDB (Twitch)",
    SOURCE_SCREENSCRAPER: "ScreenScraper.fr",
}

# ScreenScraper API v2 (gratis para apps gratuitas; pide tu devid/devpassword
# en el foro de screenscraper.fr). URL canónica documentada por la propia web.
SS_API_URL = "https://www.screenscraper.fr/api2"
SS_SOFTNAME = "es-sgdb-scraper"