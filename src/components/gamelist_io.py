"""gamelist_io.py — Lectura y escritura de gamelist.xml de EmulationStation.

Aislar todo el manejo de XML aquí significa que el resto del código
(la lógica de negocio y la GUI) no necesita saber nada sobre ElementTree.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .clean import clean_name
from .config import ASSET_DEFS, LAUNCHER_NAMES
from .models import GameEntry


def parse_gamelist(gamelist_path: Path) -> list[GameEntry]:
    """Devuelve la lista de juegos a procesar (excluyendo entradas de launcher)."""
    tree = ET.parse(gamelist_path)
    root = tree.getroot()
    games: list[GameEntry] = []

    for game_el in root.findall("game"):
        name_el = game_el.find("name")
        if name_el is None or not (name_el.text or "").strip():
            continue
        name = name_el.text.strip()
        if name.lower() in LAUNCHER_NAMES:
            continue

        # El stem del fichero launcher (.steam/.heroic/.lutris) es la fuente
        # canónica del nombre en disco: coincide con el prefijo de las imágenes.
        path_el = game_el.find("path")
        if path_el is not None and (path_el.text or "").strip():
            file_stem = Path(path_el.text.strip()).stem
        else:
            file_stem = clean_name(name)  # fallback si falta <path>

        games.append(GameEntry(name=name, file_stem=file_stem))

    return games


def update_gamelist(
    gamelist_path: Path,
    name: str,
    file_stem: str,
    downloaded: dict[str, bool],
) -> bool:
    """
    Actualiza o inserta <thumbnail>/<marquee> en el <game> cuyo <name> coincide.
    Solo toca los tags de los assets descargados correctamente.
    Devuelve True si se actualizó el XML, False si no se encontró el juego.
    """
    successful = {k: v for k, v in downloaded.items() if v}
    if not successful:
        return False

    tree = ET.parse(gamelist_path)
    root = tree.getroot()

    target = None
    for game_el in root.findall("game"):
        name_el = game_el.find("name")
        if name_el is not None and (name_el.text or "").strip() == name:
            target = game_el
            break

    if target is None:
        return False

    for key in successful:
        adef = ASSET_DEFS[key]
        xml_tag = adef["xml_tag"]
        rel_path = f"./images/{file_stem}{adef['suffix']}"

        el = target.find(xml_tag)
        if el is None:
            el = ET.SubElement(target, xml_tag)
        el.text = rel_path

    ET.indent(tree, space="\t")
    tree.write(gamelist_path, encoding="unicode", xml_declaration=True)
    return True
