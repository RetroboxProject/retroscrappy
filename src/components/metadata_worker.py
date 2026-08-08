"""metadata_worker.py — Recorre roms/, resuelve cada juego en la fuente de
metadatos elegida (IGDB / ScreenScraper) y vuelca el texto en gamelist.xml.
Además descarga el screenshot de la misma fuente y escribe <image>."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ASSET_DEFS, SOURCE_IGDB, SOURCE_NONE, SOURCE_SCREENSCRAPER
from .downloader import download_to_file
from .gamelist_io import parse_gamelist, update_gamelist, update_gamelist_metadata
from .igdb_client import IGDBAuthError, IGDBClient
from .interaction import UserInteraction
from .models import GameEntry
from .screenscraper_client import ScreenScraperAuthError, ScreenScraperClient
from .worker import ScraperCancelled


@dataclass
class MetadataScraperOptions:
    roms: Path
    systems: list[str]
    source: str = SOURCE_NONE
    igdb_client_id: str = ""
    igdb_client_secret: str = ""
    ss_devid: str = ""
    ss_devpassword: str = ""
    ss_ssid: str = ""
    ss_sspassword: str = ""
    force: bool = False


class MetadataScraper:
    def __init__(self, interaction: UserInteraction, is_cancelled=lambda: False):
        self._ui = interaction
        self._is_cancelled = is_cancelled

    def run(self, options: MetadataScraperOptions) -> None:
        if options.source == SOURCE_NONE:
            return
        if not options.roms.is_dir():
            self._ui.log(f"✗ La ruta '{options.roms}' no existe o no es un directorio.")
            return

        client = self._build_client(options)
        if client is None:
            return

        for system in options.systems:
            self._check_cancelled()
            system_path = options.roms / system
            gamelist = system_path / "gamelist.xml"

            if not gamelist.exists():
                self._ui.log(f"[{system}] ✗ No se encontró gamelist.xml, saltando.")
                continue

            games = parse_gamelist(gamelist)
            images_dir = system_path / "images"
            self._ui.log(f"═══ Metadatos [{options.source}] — Sistema: {system} ({len(games)} juegos) ═══")

            for i, game in enumerate(games, 1):
                self._check_cancelled()
                self._ui.set_status(f"[{options.source}][{system}] {i}/{len(games)}: {game.name}")
                self._process_game(client, game, gamelist, images_dir, options.force)

        self._ui.set_status("Metadatos completados.")
        self._ui.log("✓ Metadatos completados.")

    def _build_client(self, options: MetadataScraperOptions):
        if options.source == SOURCE_IGDB:
            if not options.igdb_client_id.strip() or not options.igdb_client_secret.strip():
                self._ui.log("✗ Faltan Client ID / Client Secret de IGDB.")
                return None
            client = IGDBClient(options.igdb_client_id, options.igdb_client_secret)
            try:
                client._ensure_token()
            except IGDBAuthError as e:
                self._ui.log(f"✗ {e}")
                return None
            self._ui.log("✓ Autenticado en IGDB.")
            return client

        if options.source == SOURCE_SCREENSCRAPER:
            if not options.ss_devid.strip() or not options.ss_devpassword.strip():
                self._ui.log("✗ Faltan devid / devpassword de ScreenScraper.")
                return None
            client = ScreenScraperClient(
                options.ss_devid, options.ss_devpassword, options.ss_ssid, options.ss_sspassword
            )
            try:
                client.verify_credentials()
            except Exception as e:
                self._ui.log(f"✗ {e}")
                return None
            self._ui.log("✓ Autenticado en ScreenScraper.")
            return client

        return None

    def _check_cancelled(self) -> None:
        if self._is_cancelled():
            self._ui.log("— Proceso cancelado por el usuario.")
            raise ScraperCancelled()

    def _process_game(self, client, game: GameEntry, gamelist_path: Path, images_dir: Path, force: bool) -> None:
        name = game.name
        self._ui.log(f"▸ {name}: buscando metadatos…")
        results = client.search_games(name)
        if not results:
            self._ui.log(f"  ✗ Sin resultados para '{name}'")
            return

        game_id = results[0].id
        if len(results) > 1:
            exact = [r for r in results if r.name.lower() == name.lower()]
            if len(exact) == 1:
                game_id = exact[0].id
                self._ui.log(f"  → coincidencia exacta «{exact[0].name}»")
            else:
                self._ui.log(f"  ? Conflicto de metadatos ({len(results)} candidatos): preguntando.")
                chosen = self._ui.choose_game(name, results)
                if chosen is None:
                    self._ui.log(f"  — '{name}' saltado.")
                    return
                game_id = chosen

        metadata = client.get_metadata(game_id)
        if not metadata.has_data():
            self._ui.log(f"  ✗ La fuente no devolvió datos usables para '{name}'")
            return

        # ── Texto ──
        self._ui.log(
            "  · datos: " + "; ".join(filter(None, [
                f"dev={metadata.developer}" if metadata.developer else "",
                f"pub={metadata.publisher}" if metadata.publisher else "",
                f"genre={', '.join(metadata.genres)}" if metadata.genres else "",
                f"family={metadata.family}" if metadata.family else "",
                f"players={metadata.players}" if metadata.players else "",
                f"date={metadata.release_date} ({metadata.release_region})" if metadata.release_date else "",
                "desc=sí" if metadata.desc else "",
                f"rating={metadata.rating}" if metadata.rating else "",
            ]))
        )
        written, skipped = update_gamelist_metadata(gamelist_path, name, metadata, force=force)
        if written:
            region_note = f" (fecha: región {metadata.release_region})" if "releasedate" in written else ""
            self._ui.log(f"  ✓ Escrito: {', '.join(written)}{region_note}")
        if skipped:
            self._ui.log(f"  — Se conservan (ya existían): {', '.join(skipped)}")

        # ── Screenshot -> <image> ──
        self._download_screenshot(client, metadata, game, gamelist_path, images_dir, force)

    def _download_screenshot(self, client, metadata, game: GameEntry, gamelist_path: Path, images_dir: Path, force: bool) -> None:
        adef = ASSET_DEFS["image"]
        dest = images_dir / (game.file_stem + adef["suffix"])

        if not metadata.screenshot_url:
            self._ui.log("  · La fuente no tiene screenshot para este juego.")
            return
        if dest.exists() and not force:
            self._ui.log(f"  — {dest.name} ya existe: se conserva (usa 'forzar')")
            return

        ok = download_to_file(metadata.screenshot_url, dest)
        if not ok:
            self._ui.log(f"  ✗ No se pudo descargar el screenshot de '{game.name}'")
            return
        if update_gamelist(gamelist_path, game.name, game.file_stem, {"image": True}):
            self._ui.log(f"  ✓ {dest.name} + <image> actualizado")