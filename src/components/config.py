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
TOP_N_AUTO = 3            # modo automático: el mejor de estos N por score neto
TOP_N_INTERACTIVE = 10    # modo interactivo: se muestran hasta N para elegir

# Dimensiones preferidas para grids (cover vertical de EmulationStation)
GRID_PREFERRED_DIMS = "600x900"

# Tipos de asset gestionados por este script.
#   xml_tag : etiqueta en gamelist.xml
#   suffix  : sufijo del archivo en disco (sobre clean_name())
#   fetch   : tipo de asset en la API de SteamGridDB ("grids" | "logos" | "heroes")
ASSET_DEFS = {
    "thumb": {
        "xml_tag": "thumbnail",
        "suffix": "-thumb.png",
        "label": "Thumb / Cover (grid vertical 2:3)",
        "fetch": "grids",
    },
    "marquee": {
        "xml_tag": "marquee",
        "suffix": "-marquee.png",
        "label": "Marquee / Logo",
        "fetch": "logos",
    },
}
