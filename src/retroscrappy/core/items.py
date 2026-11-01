"""What can be scraped: text fields and media kinds of a ``gamelist.xml`` entry.

Names and folders follow Batocera's EmulationStation, which RetroBat and
Retrobox share: ``images/<stem>-thumb.png``, ``videos/<stem>-video.mp4``...
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Field(StrEnum):
    """Text fields; the value is the ``gamelist.xml`` tag."""

    NAME = "name"
    DESC = "desc"
    DEVELOPER = "developer"
    PUBLISHER = "publisher"
    GENRE = "genre"
    FAMILY = "family"
    PLAYERS = "players"
    RELEASEDATE = "releasedate"
    RATING = "rating"


class MediaKind(StrEnum):
    """Media kinds; the value is the ``gamelist.xml`` tag."""

    IMAGE = "image"
    THUMBNAIL = "thumbnail"
    MARQUEE = "marquee"
    TITLESHOT = "titleshot"
    FANART = "fanart"
    BOXBACK = "boxback"
    VIDEO = "video"
    MANUAL = "manual"


@dataclass(frozen=True)
class MediaLayout:
    """Where a media kind lives on disk, relative to the system folder."""

    folder: str
    suffix: str
    default_ext: str


MEDIA_LAYOUT: dict[MediaKind, MediaLayout] = {
    MediaKind.IMAGE: MediaLayout("images", "-image", ".png"),
    MediaKind.THUMBNAIL: MediaLayout("images", "-thumb", ".png"),
    MediaKind.MARQUEE: MediaLayout("images", "-marquee", ".png"),
    MediaKind.TITLESHOT: MediaLayout("images", "-titleshot", ".png"),
    MediaKind.FANART: MediaLayout("images", "-fanart", ".jpg"),
    MediaKind.BOXBACK: MediaLayout("images", "-boxback", ".png"),
    MediaKind.VIDEO: MediaLayout("videos", "-video", ".mp4"),
    MediaKind.MANUAL: MediaLayout("manuals", "-manual", ".pdf"),
}

#: Folders that hold media, never ROMs.
MEDIA_FOLDERS = frozenset({"images", "videos", "manuals", "media", "downloaded_images"})

DEFAULT_FIELDS = frozenset(
    {
        Field.DESC,
        Field.DEVELOPER,
        Field.PUBLISHER,
        Field.GENRE,
        Field.PLAYERS,
        Field.RELEASEDATE,
        Field.RATING,
    }
)
DEFAULT_MEDIA = frozenset({MediaKind.IMAGE, MediaKind.THUMBNAIL, MediaKind.MARQUEE})

#: An item is either a text field or a media kind.
Item = Field | MediaKind

#: Key used in priority tables for "all text fields".
METADATA_KEY = "metadata"


def item_key(item: Item) -> str:
    """Priority-table key of an item: text fields share ``metadata``."""
    return METADATA_KEY if isinstance(item, Field) else item.value


def parse_fields(values: list[str]) -> set[Field]:
    """Parse field names, silently dropping unknown ones."""
    known = {f.value for f in Field}
    return {Field(v.strip()) for v in values if v.strip() in known}


def parse_media(values: list[str]) -> set[MediaKind]:
    """Parse media kind names, silently dropping unknown ones."""
    known = {k.value for k in MediaKind}
    return {MediaKind(v.strip()) for v in values if v.strip() in known}
