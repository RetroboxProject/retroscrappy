#!/usr/bin/env python3
"""
main.py — Punto de entrada de la aplicación gráfica.

Uso:
    python main.py

Todo se configura desde la ventana: carpeta roms/, API key, sistemas a
procesar y si las imágenes se eligen a mano (galería) o automáticamente.
"""

from components.gui.main_window import main

if __name__ == "__main__":
    main()
