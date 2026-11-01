"""Per-user locations for configuration and cache.

Follows the XDG base directory spec on Linux and uses ``%APPDATA%`` /
``%LOCALAPPDATA%`` on Windows (RetroBat). Nothing is ever written next to
the installed code, so the package can live in a read-only prefix.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ID = "retroscrappy"


def _base(xdg_var: str, xdg_fallback: str, win_var: str) -> Path:
    if sys.platform == "win32":
        value = os.environ.get(win_var, "").strip()
        if value:
            return Path(value)
    value = os.environ.get(xdg_var, "").strip()
    return Path(value) if value else Path.home() / xdg_fallback


def config_dir() -> Path:
    """Directory holding ``config.ini`` and user overrides."""
    return _base("XDG_CONFIG_HOME", ".config", "APPDATA") / APP_ID


def cache_dir() -> Path:
    """Directory for disposable data (image previews, temp downloads)."""
    return _base("XDG_CACHE_HOME", ".cache", "LOCALAPPDATA") / APP_ID


def config_file() -> Path:
    """Main settings file."""
    return config_dir() / "config.ini"


def ui_state_file() -> Path:
    """Window layout (sizes, column widths); safe to delete."""
    return config_dir() / "ui.ini"


def user_platforms_file() -> Path:
    """Optional TOML file extending or overriding the bundled platforms."""
    return config_dir() / "platforms.toml"


def legacy_config_file() -> Path:
    """Settings file of the pre-0.2 tool (``sgdb-scraper``), used for migration."""
    return _base("XDG_CONFIG_HOME", ".config", "APPDATA") / "sgdb-scraper" / "config.ini"
