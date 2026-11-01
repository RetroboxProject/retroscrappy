"""Storing media files for a game: download, import from disk, remove.

All three keep the frontend layout (``images/<stem>-thumb.png``...) and the
``gamelist.xml`` tag in sync. They do not save the gamelist; callers do.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import requests

from retroscrappy.core.gamelist import GameEntry
from retroscrappy.core.items import MEDIA_LAYOUT, MediaKind
from retroscrappy.core.library import resolve_media_path
from retroscrappy.providers.base import MediaCandidate
from retroscrappy.providers.http import download


def media_base(system_dir: Path, entry: GameEntry, kind: MediaKind) -> Path:
    """Target path without extension, e.g. ``…/images/Game (USA)-thumb``."""
    layout = MEDIA_LAYOUT[kind]
    return system_dir / layout.folder / f"{entry.stem}{layout.suffix}"


def _set_tag(system_dir: Path, entry: GameEntry, kind: MediaKind, new_file: Path) -> None:
    _remove_replaced(system_dir, entry.get(kind.value), new_file)
    entry.set(kind.value, f"./{new_file.relative_to(system_dir).as_posix()}")


def save_media(
    session: requests.Session,
    system_dir: Path,
    entry: GameEntry,
    kind: MediaKind,
    candidate: MediaCandidate,
) -> Path:
    """Download ``candidate`` and point the entry's tag at it.

    Raises :class:`requests.RequestException` or :class:`OSError`.
    """
    base = media_base(system_dir, entry, kind)
    fallback = candidate.extension or MEDIA_LAYOUT[kind].default_ext
    saved = download(session, candidate.url, base, fallback)
    _set_tag(system_dir, entry, kind, saved)
    return saved


def import_media_file(system_dir: Path, entry: GameEntry, kind: MediaKind, source: Path) -> Path:
    """Copy a local file into the media folder and point the tag at it."""
    base = media_base(system_dir, entry, kind)
    dest = base.with_name(base.name + source.suffix.lower())
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != dest.resolve():
        fd, tmp_name = tempfile.mkstemp(prefix=".import-", dir=dest.parent)
        os.close(fd)
        try:
            shutil.copyfile(source, tmp_name)
            os.replace(tmp_name, dest)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    _set_tag(system_dir, entry, kind, dest)
    return dest


def remove_media(system_dir: Path, entry: GameEntry, kind: MediaKind) -> None:
    """Clear the tag and delete the file if it lives inside the system folder."""
    old = resolve_media_path(system_dir, entry.get(kind.value))
    entry.remove(kind.value)
    if old and old.is_file() and _inside(old, system_dir):
        old.unlink(missing_ok=True)


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
    except ValueError:
        return False
    return True


def _remove_replaced(system_dir: Path, old_value: str, new_file: Path) -> None:
    """Delete the previous file of a tag if it was ours and differs only by extension."""
    old = resolve_media_path(system_dir, old_value)
    if not old or old == new_file or not old.is_file() or not _inside(old, system_dir):
        return
    if old.stem == new_file.stem:
        old.unlink(missing_ok=True)
