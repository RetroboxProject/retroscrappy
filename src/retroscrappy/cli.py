"""Command-line interface: ``retroscrappy <command>``.

Commands::

    retroscrappy systems             list detected systems and their coverage
    retroscrappy scrape [options]    scrape metadata and media
    retroscrappy check               test provider credentials
    retroscrappy config              print the settings file path and contents
    retroscrappy gui                 open the graphical interface
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from retroscrappy import __version__
from retroscrappy.core import paths
from retroscrappy.core.frontends import FRONTENDS, get_frontend
from retroscrappy.core.items import Field, MediaKind, parse_fields, parse_media
from retroscrappy.core.library import SystemDir, compute_coverage, discover_systems, find_roms
from retroscrappy.core.logs import get_logger, log_success, setup_console_logging
from retroscrappy.core.platforms import load_registry
from retroscrappy.core.settings import MatchMode, Settings, load_settings
from retroscrappy.pipeline.interaction import AutoInteraction, Interaction
from retroscrappy.pipeline.scraper import ScrapeRequest, Scraper
from retroscrappy.providers.base import GameQuery, Match, MediaCandidate, ProviderUnavailable
from retroscrappy.providers.registry import PROVIDER_LABELS, build_provider, build_providers

_log = get_logger("cli")
_SECRET_KEYS = ("password", "secret", "api_key")


class TerminalInteraction:
    """Numbered prompts on the terminal."""

    wants_previews = False

    @staticmethod
    def _ask(title: str, options: list[str]) -> int | None:
        print(f"\n{title}", file=sys.stderr)
        for number, text in enumerate(options, 1):
            print(f"  {number:>2}) {text}", file=sys.stderr)
        print("   0) skip", file=sys.stderr)
        while True:
            try:
                answer = input("Choice [1]: ").strip() or "1"
            except EOFError:
                return None
            if answer.isdigit() and 0 <= int(answer) <= len(options):
                return int(answer) - 1 if answer != "0" else None
            print("Please type one of the numbers above.", file=sys.stderr)

    def choose_match(self, query: GameQuery, provider: str, matches: list[Match]) -> Match | None:
        """Ask which game the ROM is."""
        index = self._ask(
            f"[{provider}] Which game is '{query.file_name}'?", [m.describe() for m in matches]
        )
        return None if index is None else matches[index]

    def choose_media(
        self, query: GameQuery, kind: MediaKind, provider: str, candidates: list[MediaCandidate]
    ) -> MediaCandidate | None:
        """Ask which media file to use."""
        index = self._ask(
            f"[{provider}] {kind.value} for '{query.name}':", [c.describe() for c in candidates]
        )
        return None if index is None else candidates[index]


# ── Helpers ──────────────────────────────────────────────────────────────


def _resolve_library(args: argparse.Namespace, settings: Settings) -> list[SystemDir] | None:
    frontend = get_frontend(args.frontend or settings.library.frontend)
    roms = Path(args.roms).expanduser() if args.roms else settings.library.roms_path
    roms = roms or frontend.default_roms_dir()
    if roms is None or not roms.is_dir():
        _log.error("ROM folder not found; pass --roms or set it in the settings")
        return None
    es_file = settings.library.es_systems_path or frontend.default_es_systems()
    systems = discover_systems(roms, load_registry(paths.user_platforms_file()), es_file)
    if args.system:
        wanted = set(args.system)
        unknown = wanted - {s.folder for s in systems}
        if unknown:
            _log.warning("Unknown systems ignored: %s", ", ".join(sorted(unknown)))
        systems = [s for s in systems if s.folder in wanted]
    return systems


def _cmd_systems(args: argparse.Namespace, settings: Settings) -> int:
    systems = _resolve_library(args, settings)
    if systems is None:
        return 1
    print(
        f"{'FOLDER':<16} {'PLATFORM':<32} {'ROMS':>6} {'LISTED':>6} "
        f"{'DESC':>5} {'THUMB':>6} {'IMAGE':>6}"
    )
    for system in systems:
        cov = compute_coverage(system, system.gamelist())
        marker = "" if system.known else " *"
        print(
            f"{system.folder:<16} {(system.label + marker)[:32]:<32} "
            f"{len(find_roms(system)):>6} {cov.games:>6} "
            f"{cov.ratio(Field.DESC):>5.0%} {cov.ratio(MediaKind.THUMBNAIL):>6.0%} "
            f"{cov.ratio(MediaKind.IMAGE):>6.0%}"
        )
    if any(not s.known for s in systems):
        print("\n* unknown platform: scraped by name only", file=sys.stderr)
    return 0


def _cmd_scrape(args: argparse.Namespace, settings: Settings) -> int:
    systems = _resolve_library(args, settings)
    if systems is None:
        return 1
    defaults = settings.scrape
    mode = MatchMode(args.mode) if args.mode else defaults.mode
    interaction: Interaction = TerminalInteraction()
    if mode is not MatchMode.AUTO and not sys.stdin.isatty():
        _log.warning("No terminal attached: switching to automatic mode")
        mode = MatchMode.AUTO
    if mode is MatchMode.AUTO:
        interaction = AutoInteraction()

    request = ScrapeRequest(
        systems=systems,
        fields=parse_fields(args.fields.split(",")) if args.fields else set(defaults.fields),
        media=parse_media(args.media.split(",")) if args.media else set(defaults.media),
        mode=mode,
        overwrite=args.overwrite or defaults.overwrite,
        add_missing_roms=defaults.add_missing_roms and not args.no_add_missing,
    )
    if args.game:
        request.only = {s.folder: {f"./{g.removeprefix('./')}" for g in args.game} for s in systems}
    providers = build_providers(settings)
    if not providers:
        _log.error("No data source is configured; run 'retroscrappy config' to find the file")
        return 1
    summary = Scraper(settings, providers, interaction).run(request)
    return 130 if summary.cancelled else 0


def _cmd_check(_args: argparse.Namespace, settings: Settings) -> int:
    failures = 0
    for key, label in PROVIDER_LABELS.items():
        account = getattr(settings, key)
        if not account.enabled:
            _log.info("%s: disabled", label)
            continue
        try:
            build_provider(key, settings).check()
            log_success(_log, "%s: credentials OK", label)
        except ProviderUnavailable as exc:
            failures += 1
            _log.error("%s", exc)
    return 1 if failures else 0


def _cmd_config(_args: argparse.Namespace, _settings: Settings) -> int:
    path = paths.config_file()
    print(path)
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and value.strip() and any(s in key for s in _SECRET_KEYS):
                line = f"{key}= ********"
            print(f"  {line}")
    else:
        print("  (not created yet; defaults in use)")
    return 0


def _cmd_gui(_args: argparse.Namespace, _settings: Settings) -> int:
    try:
        from retroscrappy.gui.app import main as gui_main  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        _log.error("The GUI needs PySide6 (pip install 'retroscrappy[gui]'): %s", exc)
        return 1
    return gui_main()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="retroscrappy", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug output")
    sub = parser.add_subparsers(dest="command", required=True)

    library = argparse.ArgumentParser(add_help=False)
    library.add_argument("--roms", help="ROM folder (default: from settings)")
    library.add_argument("--frontend", choices=sorted(FRONTENDS), help="frontend profile")
    library.add_argument("-s", "--system", action="append", help="limit to a system folder")

    sub.add_parser("systems", parents=[library], help="list systems and coverage")
    scrape = sub.add_parser("scrape", parents=[library], help="scrape metadata and media")
    scrape.add_argument("--mode", choices=[m.value for m in MatchMode])
    scrape.add_argument("--fields", help=f"comma list from: {','.join(f.value for f in Field)}")
    scrape.add_argument("--media", help=f"comma list from: {','.join(k.value for k in MediaKind)}")
    scrape.add_argument("--overwrite", action="store_true", help="replace existing data")
    scrape.add_argument("--no-add-missing", action="store_true", help="only existing entries")
    scrape.add_argument("--game", action="append", help="ROM path relative to its system folder")
    sub.add_parser("check", help="test provider credentials")
    sub.add_parser("config", help="show the settings file")
    sub.add_parser("gui", help="open the graphical interface")
    return parser


_COMMANDS = {
    "systems": _cmd_systems,
    "scrape": _cmd_scrape,
    "check": _cmd_check,
    "config": _cmd_config,
    "gui": _cmd_gui,
}


def main(argv: list[str] | None = None) -> int:
    """Entry point of the ``retroscrappy`` command."""
    args = _build_parser().parse_args(argv)
    setup_console_logging(args.verbose)
    try:
        return _COMMANDS[args.command](args, load_settings())
    except KeyboardInterrupt:
        _log.warning("Interrupted")
        return 130
