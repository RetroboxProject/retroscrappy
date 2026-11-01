"""Read and write EmulationStation ``gamelist.xml`` files.

Entries are matched by ``<path>`` (never by name), unknown tags and
attributes are preserved, and saving is atomic with a one-time ``.bak``.
"""

from __future__ import annotations

import os
import posixpath
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

GAMELIST_NAME = "gamelist.xml"
HIDDEN_TAG = "hidden"


def normalize_rel_path(path: str) -> str:
    """Canonical ``./sub/file.ext`` form used for comparisons."""
    text = path.strip().replace("\\", "/")
    if not text:
        return ""
    if posixpath.isabs(text) or (len(text) > 1 and text[1] == ":"):
        return text
    norm = posixpath.normpath(text)
    return norm if norm.startswith("../") else f"./{norm.removeprefix('./')}"


@dataclass
class GameEntry:
    """Thin wrapper around a ``<game>`` element."""

    element: ET.Element

    @property
    def path(self) -> str:
        """Normalized ``<path>`` value."""
        return normalize_rel_path(self.get("path"))

    @property
    def name(self) -> str:
        """``<name>`` value."""
        return self.get("name")

    @property
    def stem(self) -> str:
        """File name of the ROM without extension, used to name media."""
        return Path(self.path).stem if self.path else self.name

    def get(self, tag: str) -> str:
        """Stripped text of a child tag, or ``""``."""
        return (self.element.findtext(tag) or "").strip()

    def set(self, tag: str, value: str) -> None:
        """Create or replace a child tag."""
        child = self.element.find(tag)
        if child is None:
            child = ET.SubElement(self.element, tag)
        child.text = value

    def remove(self, tag: str) -> None:
        """Delete a child tag if present."""
        child = self.element.find(tag)
        if child is not None:
            self.element.remove(child)

    @property
    def hidden(self) -> bool:
        """Whether EmulationStation hides this game (``<hidden>true</hidden>``)."""
        return self.get(HIDDEN_TAG).lower() == "true"

    @hidden.setter
    def hidden(self, value: bool) -> None:
        if value:
            self.set(HIDDEN_TAG, "true")
        else:
            self.remove(HIDDEN_TAG)

    def tags(self) -> dict[str, str]:
        """All non-empty child tags as a dict."""
        return {c.tag: (c.text or "").strip() for c in self.element if (c.text or "").strip()}


class Gamelist:
    """In-memory ``gamelist.xml`` with path index."""

    def __init__(self, path: Path, root: ET.Element) -> None:
        self.path = path
        self._root = root
        self._index = {e.path: e for e in self._entries() if e.path}
        self._dirty = False
        self._backed_up = False

    @classmethod
    def load(cls, path: Path) -> Gamelist:
        """Parse ``path`` or start an empty list if it does not exist."""
        if path.is_file():
            root = ET.parse(path).getroot()
        else:
            root = ET.Element("gameList")
        return cls(path, root)

    @classmethod
    def for_system(cls, system_dir: Path) -> Gamelist:
        """Gamelist of a system folder."""
        return cls.load(system_dir / GAMELIST_NAME)

    def _entries(self) -> list[GameEntry]:
        return [GameEntry(el) for el in self._root.findall("game")]

    @property
    def games(self) -> list[GameEntry]:
        """All ``<game>`` entries in file order."""
        return self._entries()

    @property
    def dirty(self) -> bool:
        """True if there are unsaved changes."""
        return self._dirty

    def find(self, rel_path: str) -> GameEntry | None:
        """Entry whose ``<path>`` matches ``rel_path``."""
        return self._index.get(normalize_rel_path(rel_path))

    def add(self, rel_path: str, name: str) -> GameEntry:
        """Append a new entry (or return the existing one)."""
        existing = self.find(rel_path)
        if existing:
            return existing
        element = ET.SubElement(self._root, "game")
        entry = GameEntry(element)
        entry.set("path", normalize_rel_path(rel_path))
        entry.set("name", name)
        self._index[entry.path] = entry
        self._dirty = True
        return entry

    def mark_dirty(self) -> None:
        """Flag the list as modified."""
        self._dirty = True

    def save(self, force: bool = False) -> bool:
        """Write to disk atomically if dirty. Returns True if written."""
        if not (self._dirty or force):
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_file() and not self._backed_up:
            shutil.copy2(self.path, self.path.with_suffix(".xml.bak"))
            self._backed_up = True
        tree = ET.ElementTree(self._root)
        ET.indent(tree, space="\t")
        fd, tmp_name = tempfile.mkstemp(prefix=".gamelist-", suffix=".xml", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                tree.write(handle, encoding="utf-8", xml_declaration=True)
            os.replace(tmp_name, self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        self._dirty = False
        return True
