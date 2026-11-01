"""Questions asked during a scrape: which game is it, which image to use."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QListView,
    QVBoxLayout,
    QWidget,
)

from retroscrappy.core.items import MediaKind
from retroscrappy.gui.labels import media_label
from retroscrappy.providers.base import GameQuery, Match, MediaCandidate

PREVIEW_SIZE = QSize(180, 240)


class _PickerDialog(QDialog):
    """Common layout: explanation, list, Skip / Use buttons."""

    def __init__(self, title: str, message: str, parent: QWidget | None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self.accept)

        info = QLabel(message)
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)

        buttons = QDialogButtonBox()
        use = buttons.addButton(self.tr("Use selected"), QDialogButtonBox.ButtonRole.AcceptRole)
        use.setDefault(True)
        buttons.addButton(self.tr("Skip"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addWidget(self.list, 1)
        layout.addWidget(buttons)

    def selected_index(self) -> int | None:
        """Row chosen by the user, or ``None`` if skipped."""
        if self.exec() != QDialog.DialogCode.Accepted or self.list.currentRow() < 0:
            return None
        return self.list.currentRow()


def pick_match(
    parent: QWidget | None, query: GameQuery, provider: str, matches: list[Match]
) -> Match | None:
    """Ask which provider game corresponds to the ROM."""
    dialog = _PickerDialog(
        dialog_title(provider, query.name),
        dialog_tr("Which game is <b>{file}</b>?").format(file=query.file_name),
        parent,
    )
    dialog.resize(520, 420)
    for match in matches:
        item = QListWidgetItem(("★ " if match.exact else "") + match.describe())
        item.setToolTip(f"{provider} id {match.game_id}")
        dialog.list.addItem(item)
    dialog.list.setCurrentRow(0)
    index = dialog.selected_index()
    return None if index is None else matches[index]


def pick_media(
    parent: QWidget | None,
    query: GameQuery,
    kind: MediaKind,
    provider: str,
    candidates: list[MediaCandidate],
) -> MediaCandidate | None:
    """Thumbnail gallery to choose one media file."""
    dialog = _PickerDialog(
        dialog_title(provider, query.name),
        dialog_tr("Choose the <b>{kind}</b> to use:").format(kind=media_label(kind)),
        parent,
    )
    dialog.resize(860, 640)
    view = dialog.list
    view.setViewMode(QListView.ViewMode.IconMode)
    view.setIconSize(PREVIEW_SIZE)
    view.setResizeMode(QListView.ResizeMode.Adjust)
    view.setMovement(QListView.Movement.Static)
    view.setGridSize(QSize(PREVIEW_SIZE.width() + 24, PREVIEW_SIZE.height() + 40))
    view.setUniformItemSizes(True)
    view.setWordWrap(True)
    for candidate in candidates:
        pixmap = QPixmap()
        if candidate.preview:
            pixmap.loadFromData(candidate.preview)
        item = QListWidgetItem(candidate.describe())
        if not pixmap.isNull():
            item.setIcon(
                QIcon(
                    pixmap.scaled(
                        PREVIEW_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            )
        view.addItem(item)
    view.setCurrentRow(0)
    index = dialog.selected_index()
    return None if index is None else candidates[index]


def dialog_tr(text: str) -> str:
    """Translate a picker string."""
    return QCoreApplication.translate("pickers", text)


def dialog_title(provider: str, game: str) -> str:
    """``Provider — Game`` window title."""
    return f"{provider} — {game}"
