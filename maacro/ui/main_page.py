"""The Main page: live game view, overview panel and process log."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)

from ..capture import CaptureThread
from ..config import MacroConfig
from ..control import input as inp
from ..detector import DetectorThread
from ..macro import MacroThread
from ..stats import SessionStats
from ..vision.screens import SCREEN_LABELS
from . import theme
from .widgets import LiveView, LogPanel, key_value_row, panel


class MainPage(QWidget):
    def __init__(self, stats: SessionStats, capture: CaptureThread,
                 detector: DetectorThread, parent=None):
        super().__init__(parent)
        self.stats = stats

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Left: live view above the log.
        left = QSplitter(Qt.Orientation.Vertical)
        left.setChildrenCollapsible(False)
        self.live_view = LiveView()
        self.log_panel = LogPanel()
        self.log_panel.setMinimumHeight(110)
        left.addWidget(self.live_view)
        left.addWidget(self.log_panel)
        left.setStretchFactor(0, 4)
        left.setStretchFactor(1, 1)
        layout.addWidget(left, 1)

        # Right: overview.
        layout.addWidget(self._build_overview())

        self.stats.changed.connect(self._refresh_stats)
        self._clock = QTimer(self, interval=1000, timeout=self._refresh_time)
        self._clock.start()
        self._refresh_stats()

        capture.frame_ready.connect(self._on_frame)
        capture.status_changed.connect(self._on_capture_status)
        detector.event.connect(self._on_game_event)
        detector.failed.connect(lambda msg: self.log_panel.log(msg, "Error"))

        self.macro = MacroThread(capture, detector, parent=self)
        self.macro.status.connect(self.action_value.setText)
        self.macro.log.connect(self.log_panel.log)
        self.macro.finished.connect(self._on_macro_finished)
        self.macro.run_recorded.connect(
            lambda record: self.stats.add_pearls(record.pearls) if record.pearls else None)

        # F1 = start, F3 = stop; checked even when Roblox is in front.
        self._keys_down: set[int] = set()
        self._hotkeys = QTimer(self, interval=80, timeout=self._poll_hotkeys)
        self._hotkeys.start()

        self.log_panel.log("MAACRO started. Waiting for Roblox… (F1 = start, F3 = stop)")

    # --- layout --------------------------------------------------------
    def _build_overview(self) -> QWidget:
        column = QWidget()
        column.setFixedWidth(330)
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        col.addWidget(QLabel("Overview", objectName="PageTitle"))

        # Status + start/stop
        box, box_layout = panel()
        status_row = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_text = QLabel()
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_text)
        status_row.addStretch()
        box_layout.addLayout(status_row)
        row, self.screen_value = key_value_row("Screen", "—")
        box_layout.addWidget(row)
        row, self.action_value = key_value_row("Doing", "—")
        self.action_value.setWordWrap(True)
        box_layout.addWidget(row)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start (F1)", objectName="StartButton")
        self.stop_button = QPushButton("Stop (F3)")
        self.start_button.clicked.connect(self.start_macro)
        self.stop_button.clicked.connect(self.stop_macro)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        box_layout.addLayout(buttons)
        col.addWidget(box)

        # Roblox window
        box, box_layout = panel("Roblox")
        row, self.roblox_value = key_value_row("Window", "Looking…")
        box_layout.addWidget(row)
        row, self.resolution_value = key_value_row("Size", "—")
        box_layout.addWidget(row)
        col.addWidget(box)

        # Current match
        box, box_layout = panel("Current Match")
        row, self.map_value = key_value_row("Map")
        box_layout.addWidget(row)
        row, self.wave_value = key_value_row("Wave")
        box_layout.addWidget(row)
        col.addWidget(box)

        # Session results
        box, box_layout = panel("Session Results")
        cards = QGridLayout()
        cards.setSpacing(8)
        self.wins_value = self._result_card(cards, 0, "Wins", "BigWin")
        self.losses_value = self._result_card(cards, 1, "Losses", "BigLoss")
        box_layout.addLayout(cards)
        row, self.win_rate_value = key_value_row("Win Rate", "0%")
        box_layout.addWidget(row)
        row, self.runs_value = key_value_row("Completed Runs", "0")
        box_layout.addWidget(row)
        row, self.time_value = key_value_row("Session Time", "00:00:00")
        box_layout.addWidget(row)
        row, self.pearls_value = key_value_row("SummerPearls Earned", "0")
        box_layout.addWidget(row)

        # Wins/losses are counted automatically; these fix a wrong count.
        manual = QHBoxLayout()
        for text, slot, tip in (
            ("+ Win", self._manual_win, "Add a win by hand (if one was missed)."),
            ("+ Loss", self._manual_loss, "Add a loss by hand (if one was missed)."),
            ("Reset", self._reset_stats, "Set wins, losses and session time back to zero."),
        ):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            manual.addWidget(button)
        box_layout.addLayout(manual)
        col.addWidget(box)

        col.addStretch()
        return column

    @staticmethod
    def _result_card(grid: QGridLayout, column: int, title: str, style: str) -> QLabel:
        card = QFrame(objectName="Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(0)
        layout.addWidget(QLabel(title, objectName="Muted"))
        value = QLabel("0", objectName=style)
        layout.addWidget(value)
        grid.addWidget(card, 0, column)
        return value

    # --- macro control -------------------------------------------------
    def start_macro(self) -> None:
        if self.stats.running or self.macro.isRunning():
            return
        self.macro.settings = MacroConfig.load()
        self.stats.start()
        self.macro.start()

    def stop_macro(self) -> None:
        if not self.stats.running and not self.macro.isRunning():
            return
        self.macro.requestInterruption()
        self.stats.stop()
        inp.release_all()
        self.log_panel.log("Macro stopped.")

    def _on_macro_finished(self) -> None:
        self.action_value.setText("—")
        if self.stats.running:      # loop ended by itself
            self.stats.stop()

    def _poll_hotkeys(self) -> None:
        for vk, action in ((inp.VK_F1, self.start_macro), (inp.VK_F3, self.stop_macro)):
            if inp.is_pressed(vk):
                if vk not in self._keys_down:
                    self._keys_down.add(vk)
                    action()
            else:
                self._keys_down.discard(vk)

    def shutdown(self) -> None:
        self.macro.requestInterruption()
        self.macro.wait(3000)

    def _manual_win(self) -> None:
        self.stats.add_win()
        self.log_panel.log(f"Win added by hand (run {self.stats.runs}).")

    def _manual_loss(self) -> None:
        self.stats.add_loss()
        self.log_panel.log(f"Loss added by hand (run {self.stats.runs}).", "Warn")

    def _reset_stats(self) -> None:
        self.stats.reset()
        self.log_panel.log("Session results reset.")

    # --- updates -------------------------------------------------------
    def _refresh_stats(self) -> None:
        s = self.stats
        self.wins_value.setText(str(s.wins))
        self.losses_value.setText(str(s.losses))
        self.win_rate_value.setText(f"{s.win_rate:.1f}%" if s.runs else "0%")
        self.runs_value.setText(str(s.runs))
        self.pearls_value.setText(f"{s.pearls:,}")
        color = theme.WIN if s.running else theme.LOSS
        self.status_dot.setStyleSheet(f"color: {color}; background: transparent;")
        self.status_text.setText("Running" if s.running else "Not running")
        self.start_button.setEnabled(not s.running)
        self.stop_button.setEnabled(s.running)
        self._refresh_time()

    def _refresh_time(self) -> None:
        self.time_value.setText(self.stats.session_time_text())

    def _on_frame(self, image: QImage) -> None:
        self.live_view.set_frame(image)
        self.resolution_value.setText(f"{image.width()} × {image.height()}")

    def _on_capture_status(self, status: str) -> None:
        if status == "found":
            self.roblox_value.setText("Found")
            self.log_panel.log("Roblox window found.")
        elif status == "minimized":
            self.roblox_value.setText("Minimized")
            self.live_view.set_message("Roblox is minimized. Restore it to see the game.")
            self.log_panel.log("Roblox is minimized; can't capture it.", "Warn")
        else:
            self.roblox_value.setText("Not open")
            self.resolution_value.setText("—")
            self.live_view.set_message("Open Roblox to see the game here.")
            self.log_panel.log("Roblox window not found.", "Warn")

    def _on_game_event(self, kind: str, value: object) -> None:
        if kind == "screen":
            label = SCREEN_LABELS.get(value, value)
            self.screen_value.setText(label)
            if value != "unknown":
                self.log_panel.log(f"Screen: {label}")
            if value == "captcha":
                self.log_panel.log("Captcha showing — type the number and press Submit.", "Warn")
        elif kind == "wave":
            self.wave_value.setText("—" if value is None else str(value))
        elif kind == "map":
            self.map_value.setText(str(value))
        elif kind == "result":
            if value == "win":
                self.stats.add_win()
                self.log_panel.log(f"VICTORY detected — win counted (run {self.stats.runs}).")
            else:
                self.stats.add_loss()
                self.log_panel.log(f"DEFEAT detected — loss counted (run {self.stats.runs}).", "Warn")
