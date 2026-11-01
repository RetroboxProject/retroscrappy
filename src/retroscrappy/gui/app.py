"""Entry point of ``retroscrappy-gui``."""

from __future__ import annotations

import sys
from importlib import resources

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from retroscrappy import __version__
from retroscrappy.core.logs import setup_console_logging
from retroscrappy.gui.main_window import MainWindow

APP_ID = "io.github.retroboxproject.retroscrappy"


def _install_qt_translations(app: QApplication) -> None:
    """Translate Qt's own strings (standard buttons...) to the system language."""
    translator = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale.system(), "qtbase", "_", path):
        app.installTranslator(translator)


def _app_icon() -> QIcon:
    """Theme icon when installed, otherwise the copy bundled with the package."""
    bundled = resources.files("retroscrappy.data").joinpath("icons/retroscrappy.png")
    fallback = QIcon()
    if bundled.is_file():
        fallback.addPixmap(QPixmap.fromImage(QImage.fromData(bundled.read_bytes())))
    return QIcon.fromTheme(APP_ID, fallback)


def main() -> int:
    """Start the graphical interface."""
    setup_console_logging()
    # argv[0] becomes the X11 WM_CLASS; match the desktop file id.
    app = QApplication.instance() or QApplication([APP_ID, *sys.argv[1:]])
    assert isinstance(app, QApplication)
    app.setApplicationName("Retroscrappy")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("RetroboxProject")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(_app_icon())
    _install_qt_translations(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
