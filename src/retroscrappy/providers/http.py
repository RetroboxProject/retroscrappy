"""Shared HTTP session and download helpers."""

from __future__ import annotations

import mimetypes
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from retroscrappy import __version__

USER_AGENT = f"retroscrappy/{__version__} (+https://github.com/RetroboxProject/retroscrappy)"
DEFAULT_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 120
PREVIEW_WORKERS = 6

_EXTENSION_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "application/pdf": ".pdf",
}


def make_session() -> requests.Session:
    """Session with a project user agent and retries on transient errors."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    retry = Retry(
        total=3,
        connect=3,
        read=2,
        backoff_factor=1.0,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def guess_extension(url: str, content_type: str = "", fallback: str = "") -> str:
    """File extension from the response type, then the URL path."""
    mime = content_type.split(";")[0].strip().lower()
    if mime in _EXTENSION_BY_TYPE:
        return _EXTENSION_BY_TYPE[mime]
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix and len(suffix) <= 5:
        return ".jpg" if suffix == ".jpeg" else suffix
    guessed = mimetypes.guess_extension(mime) if mime else None
    return guessed or fallback


def download(session: requests.Session, url: str, dest_no_ext: Path, fallback_ext: str) -> Path:
    """Download ``url`` to ``dest_no_ext`` + detected extension, atomically.

    Raises :class:`requests.RequestException` or :class:`OSError` on failure.
    """
    with session.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True) as response:
        response.raise_for_status()
        ext = guess_extension(url, response.headers.get("Content-Type", ""), fallback_ext)
        dest = dest_no_ext.with_name(dest_no_ext.name + ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".dl-", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    handle.write(chunk)
            os.replace(tmp_name, dest)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    return dest


def fetch_bytes(session: requests.Session, url: str) -> bytes | None:
    """Small in-memory download (previews). ``None`` on any error."""
    try:
        response = session.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.content
    except requests.RequestException:
        return None


def fetch_many_bytes(session: requests.Session, urls: list[str]) -> list[bytes | None]:
    """Parallel :func:`fetch_bytes`, preserving order."""
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(PREVIEW_WORKERS, len(urls))) as pool:
        return list(pool.map(lambda u: fetch_bytes(session, u), urls))
