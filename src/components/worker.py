"""worker.py — Orquesta todo el proceso: recorre sistemas, resuelve juegos en
SteamGridDB, decide qué asset descargar (auto o vía `interaction`) y actualiza
gamelist.xml.

Pensado para ejecutarse en un hilo de fondo; toda comunicación con el usuario
pasa por la interfaz `UserInteraction` (ver interaction.py), nunca por
tkinter directamente.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .clean import clean_name
from .config import ASSET_DEFS, TOP_N_AUTO, TOP_N_INTERACTIVE
from .downloader import download_many_bytes, download_to_file
from .gamelist_io import parse_gamelist, update_gamelist
from .interaction import UserInteraction
from .models import GameCandidate, ImageCandidate
from .sgdb_client import SGDBClient


@dataclass
class ScraperOptions:
    roms: Path
    apikey: str
    systems: list[str]
    force: bool = False
    interactive: bool = False  # si True, el usuario elige la imagen entre varios candidatos


class ScraperCancelled(Exception):
    """Señal interna para abortar limpiamente si el usuario cancela desde la GUI."""


class Scraper:
    def __init__(self, interaction: UserInteraction, is_cancelled=lambda: False):
        self._ui = interaction
        self._is_cancelled = is_cancelled

    def run(self, options: ScraperOptions) -> None:
        if not options.roms.is_dir():
            self._ui.log(f"✗ La ruta '{options.roms}' no existe o no es un directorio.")
            return
        if not options.apikey.strip():
            self._ui.log("✗ API key vacía.")
            return

        client = SGDBClient(options.apikey)

        for system in options.systems:
            self._check_cancelled()
            system_path = options.roms / system
            gamelist = system_path / "gamelist.xml"

            if not gamelist.exists():
                self._ui.log(f"[{system}] ✗ No se encontró gamelist.xml, saltando.")
                continue

            games = parse_gamelist(gamelist)
            images_dir = system_path / "images"

            self._ui.log(f"═══ Sistema: {system} ({len(games)} juegos) ═══")

            for i, game in enumerate(games, 1):
                self._check_cancelled()
                self._ui.set_status(f"[{system}] {i}/{len(games)}: {game.name}")
                self._process_game(
                    client=client,
                    name=game.name,
                    file_stem=game.file_stem,
                    images_dir=images_dir,
                    gamelist_path=gamelist,
                    force=options.force,
                    interactive=options.interactive,
                )

        self._ui.set_status("Proceso completado.")
        self._ui.log("✓ Proceso completado.")

    def _check_cancelled(self) -> None:
        if self._is_cancelled():
            self._ui.log("— Proceso cancelado por el usuario.")
            raise ScraperCancelled()

    # ── Un juego ─────────────────────────────────────────────────────────

    def _process_game(
        self,
        client: SGDBClient,
        name: str,
        file_stem: str,
        images_dir: Path,
        gamelist_path: Path,
        force: bool,
        interactive: bool,
    ) -> None:
        to_download: dict[str, Path] = {}
        for key, adef in ASSET_DEFS.items():
            dest = images_dir / (file_stem + adef["suffix"])
            if dest.exists() and not force:
                if not self._ui.confirm_overwrite(dest.name):
                    continue
            to_download[key] = dest

        if not to_download:
            self._ui.log(f"✓ Sin cambios para '{name}'")
            return

        self._ui.log(f"▸ {name}: buscando en SteamGridDB…")
        game_id = self._resolve_game_id(client, name)
        if not game_id:
            self._ui.log(f"✗ No se pudo resolver '{name}', saltando.")
            return

        downloaded: dict[str, bool] = {}
        for key, dest in to_download.items():
            self._check_cancelled()
            adef = ASSET_DEFS[key]
            limit = TOP_N_INTERACTIVE if interactive else TOP_N_AUTO
            candidates = client.get_assets(game_id, adef["fetch"], limit)

            if not candidates:
                self._ui.log(f"  ✗ Sin assets '{key}' disponibles para '{name}'")
                downloaded[key] = False
                continue

            chosen = self._pick_image(candidates, adef["label"], interactive)
            if chosen is None:
                self._ui.log(f"  — '{key}' saltado.")
                downloaded[key] = False
                continue

            ok = download_to_file(chosen.url, dest)
            downloaded[key] = ok
            self._ui.log(f"  {'✓' if ok else '✗'} {dest.name}")

        if update_gamelist(gamelist_path, name, file_stem, downloaded):
            self._ui.log("  ✓ gamelist.xml actualizado")

    # ── Resolución del juego (búsqueda + desambiguación) ────────────────

    def _resolve_game_id(self, client: SGDBClient, name: str) -> int | None:
        results = client.search_games(name)
        if not results:
            self._ui.log(f"  ✗ Sin resultados en SGDB para '{name}'")
            return None

        if len(results) == 1:
            return results[0].id

        exact = [r for r in results if r.name.lower() == name.lower()]
        if len(exact) == 1:
            return exact[0].id

        chosen_id = self._ui.choose_game(name, results)
        return chosen_id

    # ── Selección de imagen (auto o manual) ─────────────────────────────

    def _pick_image(
        self,
        candidates: list[ImageCandidate],
        label: str,
        interactive: bool,
    ) -> ImageCandidate | None:
        if interactive:
            # Previsualizaciones en paralelo y usando el thumb pequeño que ya
            # sirve SGDB (no la imagen a resolución completa) — mucho más
            # rápido, y sigue en el hilo de trabajo, no en el de la GUI.
            self._check_cancelled()
            previews = download_many_bytes([c.thumb_url for c in candidates])
            for c, preview in zip(candidates, previews):
                c.preview = preview
            return self._ui.choose_image(label, candidates)

        # Modo automático: mejor score neto entre los TOP_N_AUTO primeros
        # (get_assets ya devuelve la lista ordenada por score descendente).
        best = candidates[0]
        self._ui.log(f"  → {label}: score={best.score:+d} {best.width}×{best.height} ({best.author})")
        return best
