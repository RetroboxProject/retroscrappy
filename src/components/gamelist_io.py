"""gamelist_io.py — Lectura y escritura de gamelist.xml de EmulationStation.

Aislar todo el manejo de XML aquí significa que el resto del código
(la lógica de negocio y la GUI) no necesita saber nada sobre ElementTree.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .clean import clean_name
from .config import ASSET_DEFS, LAUNCHER_NAMES
from .models import GameEntry, GameMetadata

import re
from .config import ASSET_DEFS, LAUNCHER_NAMES, SYSTEM_LAUNCHER_EXTENSIONS
from .models import GameEntry, GameDetails, GameMetadata

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


# ── Tags de texto que gestiona IGDB (no pisan lo que ya escribe ScreenScraper
# salvo que se pida force=True) ───────────────────────────────────────────

_METADATA_TAGS = {
    "desc": lambda m: m.desc,
    "developer": lambda m: m.developer,
    "publisher": lambda m: m.publisher,
    "genre": lambda m: ", ".join(m.genres),
    "family": lambda m: m.family,
    "players": lambda m: m.players,
    "releasedate": lambda m: m.release_date,
    "rating": lambda m: m.rating,
}

def update_gamelist_metadata(
    gamelist_path: Path,
    name: str,
    metadata: GameMetadata,
    force: bool = False,
) -> list[str]:
    """
    Rellena <developer>/<publisher>/<genre>/<family>/<players>/<releasedate>
    en el <game> cuyo <name> coincide, con lo que traiga `metadata`.

    Por defecto (force=False) NUNCA sobreescribe un tag que ya tenga texto:
    esto es clave porque ScreenScraper ya rellena varios de estos campos, y
    no queremos pisar datos buenos con datos de IGDB si ya estaban.

    Devuelve la lista de tags que se han escrito (para loguear en la GUI).
    """
    if not metadata.has_data():
        return []

    tree = ET.parse(gamelist_path)
    root = tree.getroot()

    target = None
    for game_el in root.findall("game"):
        name_el = game_el.find("name")
        if name_el is not None and (name_el.text or "").strip() == name:
            target = game_el
            break

    if target is None:
        return []

    written: list[str] = []
    for tag, getter in _METADATA_TAGS.items():
        value = getter(metadata)
        if not value:
            continue

        el = target.find(tag)
        existing = (el.text or "").strip() if el is not None else ""
        if existing and not force:
            continue  # ya había dato: no lo tocamos

        if el is None:
            el = ET.SubElement(target, tag)
        el.text = value
        written.append(tag)

    if written:
        ET.indent(tree, space="\t")
        tree.write(gamelist_path, encoding="unicode", xml_declaration=True)

    return written


def update_gamelist_metadata(
    gamelist_path: Path,
    name: str,
    metadata: GameMetadata,
    force: bool = False,
) -> tuple[list[str], list[str]]:
    """
    Como antes, pero devuelve (tags_escritos, tags_saltados_por_ya_existir)
    para que el worker pueda dar feedback preciso en el log.
    """
    if not metadata.has_data():
        return [], []

    tree = ET.parse(gamelist_path)
    root = tree.getroot()

    target = None
    for game_el in root.findall("game"):
        name_el = game_el.find("name")
        if name_el is not None and (name_el.text or "").strip() == name:
            target = game_el
            break

    if target is None:
        return [], []

    written: list[str] = []
    skipped: list[str] = []
    for tag, getter in _METADATA_TAGS.items():
        value = getter(metadata)
        if not value:
            continue

        el = target.find(tag)
        existing = (el.text or "").strip() if el is not None else ""
        if existing and not force:
            skipped.append(tag)
            continue

        if el is None:
            el = ET.SubElement(target, tag)
        el.text = value
        written.append(tag)

    if written:
        ET.indent(tree, space="\t")
        tree.write(gamelist_path, encoding="unicode", xml_declaration=True)

    return written, skipped


# ── Generación de gamelist.xml desde cero ────────────────────────────────

def _pretty_name(stem: str) -> str:
    """'age_of_empires_ii' -> 'age of empires ii' (solo estética del <name>)."""
    name = re.sub(r"[_\.]+", " ", stem)
    name = re.sub(r"\s+", " ", name).strip()
    return name or stem


def generate_gamelist(system_path: Path, system: str) -> Path | None:
    """
    Crea gamelist.xml escaneando los ficheros launcher del sistema
    (.steam/.heroic/.lynx). Devuelve la ruta creada, o None si no había nada.
    """
    ext = SYSTEM_LAUNCHER_EXTENSIONS.get(system)
    if not ext:
        return None

    files = sorted(p for p in system_path.glob(f"*{ext}") if p.is_file())
    root = ET.Element("gameList")
    count = 0
    for f in files:
        name = _pretty_name(f.stem)
        if name.lower() in LAUNCHER_NAMES:
            continue
        game_el = ET.SubElement(root, "game")
        ET.SubElement(game_el, "path").text = f"./{f.name}"
        ET.SubElement(game_el, "name").text = name
        count += 1

    if not count:
        return None

    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t")
    out = system_path / "gamelist.xml"
    tree.write(out, encoding="unicode", xml_declaration=True)
    return out


# ── Lectura completa para la pantalla de previsualización ────────────────

def parse_gamelist_details(gamelist_path: Path) -> list[GameDetails]:
    """Lee cada <game> con todos sus tags de texto y de imagen."""
    tree = ET.parse(gamelist_path)
    root = tree.getroot()
    out: list[GameDetails] = []

    image_tags = {adef["xml_tag"] for adef in ASSET_DEFS.values()}
    for game_el in root.findall("game"):
        name_el = game_el.find("name")
        if name_el is None or not (name_el.text or "").strip():
            continue
        name = name_el.text.strip()

        path_el = game_el.find("path")
        file_stem = Path(path_el.text.strip()).stem if path_el is not None and path_el.text else clean_name(name)

        metadata: dict[str, str] = {}
        images: dict[str, str] = {}
        for child in game_el:
            text = (child.text or "").strip()
            if not text:
                continue
            if child.tag in image_tags:
                images[child.tag] = text
            elif child.tag not in ("path", "name", "md5"):
                metadata[child.tag] = text

        out.append(GameDetails(name=name, file_stem=file_stem, metadata=metadata, images=images))
    return out
