"""Translatable, human-readable labels for core enums."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from retroscrappy.core.items import METADATA_KEY, Field, MediaKind
from retroscrappy.core.settings import MatchMode


def _tr(text: str) -> str:
    return QCoreApplication.translate("labels", text)


def field_label(item: Field) -> str:
    """Label of a text field."""
    return {
        Field.NAME: _tr("Name"),
        Field.DESC: _tr("Description"),
        Field.DEVELOPER: _tr("Developer"),
        Field.PUBLISHER: _tr("Publisher"),
        Field.GENRE: _tr("Genre"),
        Field.FAMILY: _tr("Series"),
        Field.PLAYERS: _tr("Players"),
        Field.RELEASEDATE: _tr("Release date"),
        Field.RATING: _tr("Rating"),
    }[item]


def media_label(kind: MediaKind) -> str:
    """Label of a media kind."""
    return {
        MediaKind.IMAGE: _tr("Screenshot"),
        MediaKind.THUMBNAIL: _tr("Box art"),
        MediaKind.MARQUEE: _tr("Logo (marquee)"),
        MediaKind.TITLESHOT: _tr("Title screen"),
        MediaKind.FANART: _tr("Fan art"),
        MediaKind.BOXBACK: _tr("Box back"),
        MediaKind.VIDEO: _tr("Video"),
        MediaKind.MANUAL: _tr("Manual"),
    }[kind]


def priority_key_label(key: str) -> str:
    """Label of a source-priority key (``metadata`` or a media kind)."""
    if key == METADATA_KEY:
        return _tr("Text metadata")
    return media_label(MediaKind(key))


def mode_label(mode: MatchMode) -> str:
    """Short label of a match mode."""
    return {
        MatchMode.AUTO: _tr("Automatic"),
        MatchMode.SEMI: _tr("Ask when unsure"),
        MatchMode.MANUAL: _tr("Always ask"),
    }[mode]


def mode_help(mode: MatchMode) -> str:
    """One-line explanation of a match mode."""
    return {
        MatchMode.AUTO: _tr("Never asks. Fast, but fuzzy names may get the wrong game."),
        MatchMode.SEMI: _tr("Asks only when the game or the artwork is ambiguous."),
        MatchMode.MANUAL: _tr("Confirm every game and pick every image yourself."),
    }[mode]


def profile_label(profile: str) -> str:
    """Label of a source-priority profile."""
    return _tr("PC launchers (Steam, Lutris...)") if profile == "pc" else _tr("Consoles & arcade")
