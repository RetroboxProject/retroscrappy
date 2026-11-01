"""Game name helpers: titles from ROM file names and fuzzy comparison."""

from __future__ import annotations

import re
import unicodedata

_TAGS_RE = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_SEPARATORS_RE = re.compile(r"[_\.]+")
_SPACES_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_INVALID_FILENAME_RE = re.compile(r'[/\\:*?"<>|]')
_LEADING_ARTICLE_RE = re.compile(r"^(.*), (the|a|an)$", re.IGNORECASE)


def title_from_filename(stem: str) -> str:
    """Turn ``Sonic The Hedgehog 2 (World) (Rev B)`` into a searchable title."""
    title = _TAGS_RE.sub("", stem)
    title = _SEPARATORS_RE.sub(" ", title)
    title = _SPACES_RE.sub(" ", title).strip()
    match = _LEADING_ARTICLE_RE.match(title)
    if match:
        title = f"{match.group(2)} {match.group(1)}"
    return title or stem


def normalize(name: str) -> str:
    """Comparable form of a name: no accents, case, tags or punctuation."""
    text = unicodedata.normalize("NFKD", title_from_filename(name))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("&", "and")
    return _NON_ALNUM_RE.sub("", text)


def same_game_name(left: str, right: str) -> bool:
    """True when two names are equal after :func:`normalize`."""
    return bool(left) and normalize(left) == normalize(right)


def safe_filename(name: str) -> str:
    """Replace characters that are invalid in file names with ``-``."""
    return _INVALID_FILENAME_RE.sub("-", name).strip()
