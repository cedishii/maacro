"""Small hand-drawn charts for the Stats page (no chart library needed)."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QToolTip, QWidget

from . import theme


class DayChart(QWidget):
    """Runs per day as bars: wins (green) with losses (red) stacked on top."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.days: list[tuple[date, int, int]] = []
        self.setMinimumHeight(150)
        self.setMouseTracking(True)

    def set_days(self, days: list[tuple[date, int, int]]) -> None:
        self.days = days
        self.update()

    def _bars(self) -> list[tuple[QRectF, tuple[date, int, int]]]:
        if not self.days:
            return []
        left, right, top, bottom = 8, 8, 18, 22
        width = max(1, self.width() - left - right)
        slot = width / len(self.days)
        tallest = max(1, max(w + l for _, w, l in self.days))
        usable = max(1, self.height() - top - bottom)
        bars = []
        for i, day in enumerate(self.days):
            total = day[1] + day[2]
            h = usable * total / tallest
            bars.append((QRectF(left + i * slot + slot * 0.18, top + usable - h, slot * 0.64, h), day))
        return bars

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        muted = QColor(theme.MUTED)
        bars = self._bars()
        if not bars or not any(w + l for _, w, l in self.days):
            painter.setPen(muted)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No runs in these days yet")
            return
        base = self.height() - 22
        painter.setPen(QColor(theme.BORDER))
        painter.drawLine(8, int(base), self.width() - 8, int(base))
        step = max(1, len(bars) // 7)
        labelled = set(range(len(bars) - 1, -1, -step))     # today always, then every step back
        for i, (rect, (day, wins, losses)) in enumerate(bars):
            total = wins + losses
            if total:
                win_h = rect.height() * wins / total
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(theme.WIN))
                painter.drawRoundedRect(QRectF(rect.x(), rect.bottom() - win_h, rect.width(), win_h), 2, 2)
                if losses:
                    painter.setBrush(QColor(theme.LOSS))
                    painter.drawRoundedRect(QRectF(rect.x(), rect.y(), rect.width(), rect.height() - win_h), 2, 2)
                painter.setPen(QColor(theme.TEXT))
                painter.drawText(QRectF(rect.x() - 10, rect.y() - 16, rect.width() + 20, 14),
                                 Qt.AlignmentFlag.AlignCenter, str(total))
            if i in labelled:
                painter.setPen(muted)
                painter.drawText(QRectF(rect.x() - 20, base + 4, rect.width() + 40, 16),
                                 Qt.AlignmentFlag.AlignCenter, f"{day:%b} {day.day}")

    def mouseMoveEvent(self, event) -> None:
        for rect, (day, wins, losses) in self._bars():
            if rect.x() - 4 <= event.position().x() <= rect.right() + 4:
                QToolTip.showText(event.globalPosition().toPoint(),
                                  f"{day:%a %b} {day.day}: {wins + losses} runs — {wins} won, {losses} lost",
                                  self)
                return
        QToolTip.hideText()
