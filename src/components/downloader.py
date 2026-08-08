"""downloader.py — Descarga de assets finales y de previsualizaciones para la GUI."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

TIMEOUT = 30
PREVIEW_WORKERS = 6  # descargas de miniatura en paralelo


def download_to_file(url: str, dest: Path) -> bool:
    """Descarga `url` a `dest`, creando carpetas intermedias. Devuelve éxito/fallo."""
    try:
        r = requests.get(url, timeout=TIMEOUT, stream=True)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception:
        return False


def download_bytes(url: str) -> bytes | None:
    """Descarga `url` en memoria (usado para las miniaturas de la GUI)."""
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def download_many_bytes(urls: list[str]) -> list[bytes | None]:
    """Descarga varias URLs en paralelo, preservando el orden de entrada.
    Usado para las previsualizaciones de la galería, que si no tardan
    demasiado al pedirlas una a una en serie."""
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(PREVIEW_WORKERS, len(urls))) as pool:
        return list(pool.map(download_bytes, urls))
