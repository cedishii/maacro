"""Reusable pieces of the MAACRO window."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from . import theme

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def panel(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    """A rounded box with an optional title. Returns the box and its layout."""
    frame = QFrame(objectName="Panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)
    if title:
        label = QLabel(title, objectName="PanelTitle")
        layout.addWidget(label)
    return frame, layout


def key_value_row(key: str, value: str = "—") -> tuple[QWidget, QLabel]:
    """A 'Label ........ value' row. Returns the row and the value label."""
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QLabel(key, objectName="Muted"))
    layout.addStretch()
    value_label = QLabel(value, objectName="Value")
    layout.addWidget(value_label)
    return row, value_label


class LiveView(QWidget):
    """Shows the latest picture of the Roblox window, scaled to fit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LiveView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(480, 270)
        self._image: QImage | None = None
        self._message = "Looking for the Roblox window…"

    def set_frame(self, image: QImage) -> None:
        self._image = image
        self.update()

    def set_message(self, message: str) -> None:
        """Show a message instead of the game (e.g. Roblox not open)."""
        self._image = None
        self._message = message
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        area = self.rect().adjusted(6, 6, -6, -6)
        if self._image is None:
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, self._message)
            return
        scaled = self._image.size().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRect(0, 0, scaled.width(), scaled.height())
        target.moveCenter(area.center())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, self._image)


class LogPanel(QFrame):
    """The process log: every step the macro takes, with search and filter."""

    LEVELS = ("Info", "Warn", "Error")
    COLORS = {"Info": theme.TEXT, "Warn": theme.WARN, "Error": theme.LOSS}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self._entries: list[tuple[str, str, str]] = []  # (time, level, message)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(QLabel("Process Log", objectName="PanelTitle"))
        header.addStretch()
        self.search = QLineEdit(placeholderText="Search log")
        self.search.setFixedWidth(160)
        self.search.textChanged.connect(self._render)
        header.addWidget(self.search)
        self.level = QComboBox()
        self.level.addItems(("All",) + self.LEVELS)
        self.level.currentTextChanged.connect(self._render)
        header.addWidget(self.level)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear)
        header.addWidget(clear)
        layout.addLayout(header)

        self.text = QPlainTextEdit(readOnly=True)
        self.text.setMaximumBlockCount(2000)
        layout.addWidget(self.text)

    def _write_file(self, level: str, message: str) -> None:
        """Also keep the log on disk (logs/YYYY-MM-DD.log) for checking later."""
        try:
            LOG_DIR.mkdir(exist_ok=True)
            now = datetime.now()
            with open(LOG_DIR / f"{now:%Y-%m-%d}.log", "a", encoding="utf-8") as file:
                file.write(f"{now:%H:%M:%S} [{level}] {message}\n")
        except OSError:
            pass

    def log(self, message: str, level: str = "Info") -> None:
        self._write_file(level, message)
        entry = (datetime.now().strftime("%H:%M:%S"), level, message)
        self._entries.append(entry)
        if len(self._entries) > 2000:
            del self._entries[:500]
        if self._matches(entry):
            self._append(entry)

    def clear(self) -> None:
        self._entries.clear()
        self.text.clear()

    def _matches(self, entry: tuple[str, str, str]) -> bool:
        _, level, message = entry
        wanted = self.level.currentText()
        if wanted != "All" and level != wanted:
            return False
        query = self.search.text().strip().lower()
        return not query or query in message.lower()

    def _append(self, entry: tuple[str, str, str]) -> None:
        time_text, level, message = entry
        color = self.COLORS.get(level, theme.TEXT)
        safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.text.appendHtml(
            f'<span style="color:{theme.MUTED}">{time_text}</span> '
            f'<span style="color:{color}">{safe}</span>'
        )

    def _render(self) -> None:
        self.text.clear()
        for entry in self._entries:
            if self._matches(entry):
                self._append(entry)
