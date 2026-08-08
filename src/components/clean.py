"""clean.py — Normalización de nombres de fichero (≡ limpiar_nombre() en bash)."""

from __future__ import annotations

import re

_CLEAN_RE = re.compile(r'[/\\:*?"<>|]')


def clean_name(name: str) -> str:
    """
    Sustituye los caracteres no válidos en nombres de fichero  / \\ : * ? " < > |
    por '-' y recorta espacios. Debe coincidir exactamente con limpiar_nombre()
    en los scripts de sincronización en bash, ya que las rutas de imagen en
    disco dependen de esta convención.
    """
    return _CLEAN_RE.sub("-", name).strip()
