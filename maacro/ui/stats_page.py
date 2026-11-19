"""The Stats page: every run ever recorded (runs/runs.csv) — totals, today,
streaks, results per map, per stage kind and per day, and the latest runs."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..history import RUNS_CSV, Group, Summary, hms, load_runs, summarize
from . import theme
from .widgets import panel


def _table(headers: list[str], height: int = 260) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSortingEnabled(True)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for col in range(1, len(headers)):
        table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    table.setMinimumHeight(height)
    return table


class _Item(QTableWidgetItem):
    """A cell that sorts by a number when it has one."""

    def __init__(self, text: str, key=None, color: str | None = None):
        super().__init__(text)
        self.key = key if key is not None else text
        if color:
            self.setForeground(QColor(color))
        if isinstance(self.key, (int, float)):
            self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):
        if isinstance(other, _Item) and type(self.key) is type(other.key):
            return self.key < other.key
        return super().__lt__(other)


def _rate_color(rate: float) -> str:
    return theme.WIN if rate >= 80 else theme.WARN if rate >= 50 else theme.LOSS


class StatsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(QLabel("Stats", objectName="PageTitle"))
        self.range_label = QLabel("", objectName="Muted")
        header.addWidget(self.range_label)
        header.addStretch()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        folder = QPushButton("Open runs folder")
        folder.setToolTip("runs.csv (every run) and the latest end-screen pictures.")
        folder.clicked.connect(self._open_folder)
        header.addWidget(folder)
        layout.addLayout(header)

        # Headline numbers.
        cards = QGridLayout()
        cards.setSpacing(10)
        self.values: dict[str, tuple[QLabel, QLabel]] = {}
        for index, (key, title) in enumerate((
                ("runs", "All-time runs"), ("rate", "Win rate"), ("today", "Today"),
                ("streak", "Best win streak"), ("per_hour", "Runs per hour"), ("avg", "Avg stage time"))):
            card = QFrame(objectName="Card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 10)
            card_layout.setSpacing(2)
            card_layout.addWidget(QLabel(title, objectName="Muted"))
            value = QLabel("—", objectName="StatValue")
            card_layout.addWidget(value)
            note = QLabel("", objectName="Muted")
            card_layout.addWidget(note)
            cards.addWidget(card, index // 3, index % 3)
            self.values[key] = (value, note)
        layout.addLayout(cards)

        row = QHBoxLayout()
        row.setSpacing(12)
        box, box_layout = panel("By map")
        self.map_table = _table(["Map", "Runs", "Wins", "Win %", "Avg time"])
        box_layout.addWidget(self.map_table)
        row.addWidget(box, 3)
        box, box_layout = panel("By stage kind")
        self.kind_table = _table(["Kind", "Runs", "Win %", "Avg time"])
        box_layout.addWidget(self.kind_table)
        row.addWidget(box, 2)
        layout.addLayout(row)

        box, box_layout = panel("Latest runs")
        self.recent_table = _table(["Map", "When", "Result", "Kind", "Mode", "Waves", "Time", "Pearls"], 320)
        box_layout.addWidget(self.recent_table)
        layout.addWidget(box)

        box, box_layout = panel("By day")
        self.day_table = _table(["Day", "Runs", "Wins", "Losses", "Win %", "Played"], 200)
        box_layout.addWidget(self.day_table)
        layout.addWidget(box)

        self.empty = QLabel("No runs recorded yet — they show up here once MAACRO finishes a match.",
                            objectName="Muted")
        layout.addWidget(self.empty)
        layout.addStretch()
        self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        self.show_summary(summarize(load_runs()))

    def show_summary(self, s: Summary) -> None:
        total = s.total
        self.empty.setVisible(total.runs == 0)
        if s.first and s.last:
            self.range_label.setText(f"  {s.first:%b %d, %Y} – {s.last:%b %d, %Y}")
        self._set("runs", f"{total.runs:,}", f"{total.wins:,} wins · {total.losses:,} losses")
        self._set("rate", f"{total.win_rate:.1f}%" if total.runs else "—", "", _rate_color(total.win_rate)
                  if total.runs else None)
        today = s.today
        self._set("today", f"{today.runs}", f"{today.wins} wins · {today.losses} losses" if today.runs else "no runs yet")
        current = (f"now {s.current_streak} win{'s' if s.current_streak != 1 else ''} in a row"
                   if s.current_streak > 0 else
                   f"now {-s.current_streak} loss{'es' if s.current_streak != -1 else ''} in a row"
                   if s.current_streak < 0 else "")
        self._set("streak", str(s.best_win_streak), current)
        self._set("per_hour", f"{s.runs_per_hour:.1f}" if s.runs_per_hour else "—", "of stage time")
        self._set("avg", hms(total.avg_seconds), f"{total.pearls:,} pearls total" if total.pearls else "")

        self._fill(self.map_table, [
            [_Item(g.name), _Item(str(g.runs), g.runs), _Item(str(g.wins), g.wins),
             _Item(f"{g.win_rate:.0f}%", g.win_rate, _rate_color(g.win_rate)),
             _Item(hms(g.avg_seconds), g.avg_seconds or 0)] for g in s.by_map], sort=1)
        self._fill(self.kind_table, [
            [_Item(g.name), _Item(str(g.runs), g.runs),
             _Item(f"{g.win_rate:.0f}%", g.win_rate, _rate_color(g.win_rate)),
             _Item(hms(g.avg_seconds), g.avg_seconds or 0)] for g in s.by_kind], sort=1)
        self._fill(self.recent_table, [
            [_Item(r.map or "?"), _Item(f"{r.time:%b %d %H:%M}", r.time.timestamp()),
             _Item("Win" if r.result == "win" else "Loss", r.result,
                   theme.WIN if r.result == "win" else theme.LOSS),
             _Item(r.kind or "—"), _Item(r.mode or "—"),
             _Item(str(r.waves) if r.waves else "—", r.waves or 0),
             _Item(hms(r.seconds), r.seconds or 0),
             _Item(f"{r.pearls:,}" if r.pearls else "—", r.pearls or 0)] for r in s.recent], sort=1)
        self._fill(self.day_table, [self._day_row(g) for g in s.by_day], sort=0)

    @staticmethod
    def _day_row(g: Group) -> list[QTableWidgetItem]:
        return [_Item(g.name), _Item(str(g.runs), g.runs), _Item(str(g.wins), g.wins),
                _Item(str(g.losses), g.losses),
                _Item(f"{g.win_rate:.0f}%", g.win_rate, _rate_color(g.win_rate)),
                _Item(hms(sum(g.seconds)) if g.seconds else "—", sum(g.seconds))]

    def _set(self, key: str, value: str, note: str, color: str | None = None) -> None:
        label, note_label = self.values[key]
        label.setText(value)
        label.setStyleSheet(f"color: {color};" if color else "")
        note_label.setText(note)

    @staticmethod
    def _fill(table: QTableWidget, rows: list[list[QTableWidgetItem]], sort: int) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, item in enumerate(row):
                table.setItem(r, c, item)
        table.setSortingEnabled(True)
        table.sortItems(sort, Qt.SortOrder.DescendingOrder)

    @staticmethod
    def _open_folder() -> None:
        try:
            RUNS_CSV.parent.mkdir(exist_ok=True)
            os.startfile(RUNS_CSV.parent)
        except OSError:
            pass
