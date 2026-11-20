"""The Main page: live game view, overview panel and process log."""
from __future__ import annotations

import collections
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter,
    QVBoxLayout, QWidget,
)

from .. import night_guard, relaunch, setup_check
from ..loss_replay import LossReplay, latest_replay
from .. import runs as runs_module
from ..app_settings import AppSettings, hotkey_vk
from ..auto_profile import with_auto_profile
from ..unit_plan import with_unit_plan
from ..remote import RemoteControl, help_text
from ..capture import CaptureThread, window_state
from ..control import input as inp
from ..detector import DetectorThread
from ..goals import eta_text, goal_reached, goal_text, stop_time
from ..history import hms, load_runs, summarize
from ..card_strategy import STRATEGIES
from ..summer_config import SummerConfig
from ..modes import BY_KEY, MODES, find_mode, last_behavior, last_mode, save_behavior, save_mode
from ..party import BEHAVIORS, PARTY, SOLO, with_party
from ..stats import SessionStats
from ..webhook import Notifier
from ..vision.screens import SCREEN_LABELS
from . import theme
from .widgets import LiveView, LogPanel, key_value_row, panel


class _LogBridge(QObject):
    """Lets background threads (Discord sends) write to the log safely."""
    line = Signal(str, str)


class MainPage(QWidget):
    mode_changed = Signal(str)
    behavior_changed = Signal(str)

    def __init__(self, stats: SessionStats, capture: CaptureThread,
                 detector: DetectorThread, parent=None):
        super().__init__(parent)
        self.stats = stats
        self.capture = capture
        self.detector = detector
        self.app_settings = AppSettings.load()
        self.rejoin_watch = relaunch.RejoinWatch()
        self._relaunching = False
        # Overnight: loss replays, fresh Roblox, start at a time, resume after a crash.
        self.replay = LossReplay()
        self.fresh = night_guard.FreshRestart()
        self._start_at_fired = None
        self._resume_pending = False
        self._session_ending = False

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
        # Scrolls instead of squashing when the window is short.
        overview = QScrollArea(widgetResizable=True)
        overview.setFrameShape(QFrame.Shape.NoFrame)
        overview.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        overview.setWidget(self._build_overview())
        overview.setFixedWidth(344)
        layout.addWidget(overview)

        self.stats.changed.connect(self._refresh_stats)
        self._clock = QTimer(self, interval=1000, timeout=self._refresh_time)
        self._clock.start()
        self._refresh_stats()

        capture.frame_ready.connect(self._on_frame)
        capture.status_changed.connect(self._on_capture_status)
        detector.event.connect(self._on_game_event)
        detector.failed.connect(lambda msg: self.log_panel.log(msg, "Error"))

        # Discord updates (Settings page).
        self._log_bridge = _LogBridge(self)
        self._log_bridge.line.connect(self.log_panel.log)
        self.notifier = Notifier(log=lambda msg, level="Info": self._log_bridge.line.emit(msg, level))

        # One controller per mode; only the selected one is ever started.
        self.macros = {}
        for mode in MODES:
            thread_class = with_party(mode.thread_class) if mode.supports_party else mode.thread_class
            thread = with_auto_profile(with_unit_plan(thread_class))(capture, detector, parent=self)
            thread.profile_mode = mode.key      # profiles/<mode>/, picked by map
            thread.names_read.connect(lambda found, key=mode.key: self._save_read_names(key, found))
            if hasattr(thread, "stop_requested"):
                thread.stop_requested.connect(self._mode_asked_to_stop)
            thread.status.connect(self.action_value.setText)
            thread.log.connect(self.log_panel.log)
            thread.finished.connect(self._on_macro_finished)
            thread.drop_found.connect(self.stats.add_drop)
            thread.drop_found.connect(self.notifier.note_drop)
            thread.drop_found.connect(self._post_drop)
            thread.run_recorded.connect(
                lambda record: self.stats.add_pearls(record.pearls) if record.pearls else None)
            thread.run_recorded.connect(self._post_run)
            thread.run_recorded.connect(lambda _record: self.refresh_lifetime())
            thread.log.connect(self._watch_for_alerts)
            if hasattr(thread, "progress"):
                thread.progress.connect(self._on_ic_progress)
            self.macros[mode.key] = thread
        self.behavior = SOLO
        self._set_mode(last_mode())
        self._set_behavior(last_behavior())

        # Start / stop hotkeys (F1 / F3 unless changed in Settings); checked
        # even when Roblox is in front.
        self._keys_down: set[int] = set()
        self._hotkeys = QTimer(self, interval=80, timeout=self._poll_hotkeys)
        self._hotkeys.start()
        # Discord remote control (Settings): commands from the player's phone.
        self.remote = RemoteControl(self)
        self.remote.command.connect(self._on_remote_command)
        self.remote.log.connect(self.log_panel.log)
        # Setup check: the last screen reads (sampled every 2 s).
        self._recent_screens: collections.deque = collections.deque(maxlen=30)
        self._screen_sampler = QTimer(self, interval=2000, timeout=self._sample_screen)
        self._screen_sampler.start()
        # Auto-rejoin (Settings → Roblox): looked at every 3 s.
        self._rejoin_timer = QTimer(self, interval=3000, timeout=self._check_rejoin)
        self._rejoin_timer.start()
        self.apply_app_settings()

        self.log_panel.log(f"MAACRO started. Waiting for Roblox… ({self.app_settings.start_key} = start, "
                           f"{self.app_settings.stop_key} = stop)")
        app = QApplication.instance()
        if app is not None and hasattr(app, "commitDataRequest"):
            # Windows is shutting down / restarting: keep the "running" mark, so we resume.
            app.commitDataRequest.connect(lambda *_: setattr(self, "_session_ending", True))
        QTimer.singleShot(0, self._maybe_resume)

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
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode", objectName="Muted"))
        self.mode_box = QComboBox()
        for mode in MODES:
            self.mode_box.addItem(mode.label, mode.key)
        self.mode_box.setToolTip("Which game mode to automate. Stop the macro to switch.")
        self.mode_box.currentIndexChanged.connect(
            lambda _: self._set_mode(self.mode_box.currentData()))
        mode_row.addWidget(self.mode_box, 1)
        box_layout.addLayout(mode_row)
        role_row = QHBoxLayout()
        role_row.addWidget(QLabel("Role", objectName="Muted"))
        self.behavior_box = QComboBox()
        for key, label in BEHAVIORS.items():
            self.behavior_box.addItem(label, key)
        self.behavior_box.setToolTip(
            "Solo / Leader: MAACRO plays and also picks what's next (Play, Return to lobby, "
            "Next Room…).\nParty Member: MAACRO only plays; the party leader picks portals and "
            "what happens after each match. Stop the macro to switch.")
        self.behavior_box.currentIndexChanged.connect(
            lambda _: self._set_behavior(self.behavior_box.currentData()))
        role_row.addWidget(self.behavior_box, 1)
        box_layout.addLayout(role_row)
        # Summer Event only: how cards are picked (also on Configs → Summer Event).
        self.cards_row = QWidget()
        cards_layout = QHBoxLayout(self.cards_row)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.addWidget(QLabel("Cards", objectName="Muted"))
        self.cards_box = QComboBox()
        self.cards_box.addItem("Easy — green first, red only for Secret Drop Rate", "easy")
        self.cards_box.addItem("Hard — red cards as much as possible", "hard")
        self.cards_box.addItem("Smart — Hard, but Easy for 2 runs after a defeat", "smart")
        self.cards_box.setToolTip(
            "Easy: green cards first; red only for + Secret Drop Rate (and the Star Golem card "
            "during Starfall).\nHard: red cards first (the highest + Secret Drop Rate first, then "
            "the most SummerPearls, the mildest danger among equals).\nSmart: Hard, but Easy for "
            "the 2 runs after a defeat.\nCompare them on the Stats page (By card style). Applies "
            "right away, even while running.")
        self.cards_box.setCurrentIndex(max(0, self.cards_box.findData(SummerConfig.load().card_strategy)))
        self.cards_box.currentIndexChanged.connect(lambda _: self._set_card_strategy(self.cards_box.currentData()))
        cards_layout.addWidget(self.cards_box, 1)
        box_layout.addWidget(self.cards_row)
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
        setup_row = QHBoxLayout()
        setup_row.addWidget(QLabel("Setup", objectName="Muted"))
        setup_row.addStretch()
        self.setup_value = QLabel("—", objectName="Value")
        setup_row.addWidget(self.setup_value)
        check = QPushButton("Check")
        check.setToolTip("Check the Roblox window, screen reading and this mode's unit setup "
                         "(the details go to the log). Also done on every Start.")
        check.clicked.connect(lambda: self.run_setup_check(log_all=True))
        setup_row.addWidget(check)
        box_layout.addLayout(setup_row)
        col.addWidget(box)

        # Current match
        box, box_layout = panel("Current Match")
        row, self.map_value = key_value_row("Map")
        box_layout.addWidget(row)
        row, self.wave_value = key_value_row("Wave")
        box_layout.addWidget(row)
        col.addWidget(box)

        # Infinity Castle progress (shown in that mode only)
        self.ic_box, box_layout = panel("Infinity Castle")
        row, self.ic_room_value = key_value_row("Room", "—")
        box_layout.addWidget(row)
        row, self.ic_cleared_value = key_value_row("Rooms Cleared", "0")
        box_layout.addWidget(row)
        row, self.ic_retries_value = key_value_row("Defeats (retried)", "0")
        box_layout.addWidget(row)
        row, self.ic_note_value = key_value_row("Last Step", "—")
        self.ic_note_value.setWordWrap(True)
        box_layout.addWidget(row)
        col.addWidget(self.ic_box)

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
        row, self.goal_value = key_value_row("Session Goal", "None")
        self.goal_value.setToolTip("Settings → Session goals: stop by itself after N runs, "
                                   "after so long, or after too many losses in a row.")
        box_layout.addWidget(row)
        self.eta_row, self.eta_value = key_value_row("Time to Goal", "—")
        self.eta_row.setToolTip("When the soonest session goal ends the session. A runs goal uses "
                                "this session's pace (the gaps between matches included).")
        self.eta_row.hide()
        box_layout.addWidget(self.eta_row)
        row, self.lifetime_value = key_value_row("All-time Runs", "—")
        row.setToolTip("Every run ever recorded (runs/runs.csv). Details on the Stats page.")
        box_layout.addWidget(row)
        self.pearls_row, self.pearls_value = key_value_row("SummerPearls Earned", "0")
        box_layout.addWidget(self.pearls_row)
        row, self.charms_value = key_value_row("Charms Dropped", "0")
        box_layout.addWidget(row)
        row, self.portals_value = key_value_row("Portals Dropped", "0")
        box_layout.addWidget(row)
        # Every drop by name, most common first.
        self.drops_list = QLabel("No drops yet", objectName="Muted")
        self.drops_list.setWordWrap(True)
        box_layout.addWidget(self.drops_list)

        # Wins/losses are counted automatically; these fix a wrong count.
        manual = QHBoxLayout()
        for text, slot, tip in (
            ("+ Win", self._manual_win, "Add a win by hand (if one was missed)."),
            ("+ Loss", self._manual_loss, "Add a loss by hand (if one was missed)."),
            ("Reset", self._reset_stats, "Set wins, losses, drops and session time back to zero."),
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
        card.setMinimumHeight(72)           # room for the big number
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(2)
        layout.addWidget(QLabel(title, objectName="Muted"))
        value = QLabel("0", objectName=style)
        value.setMinimumHeight(34)
        layout.addWidget(value)
        grid.addWidget(card, 0, column)
        return value

    # --- modes ---------------------------------------------------------
    @property
    def macro(self):
        """The selected mode's controller."""
        return self.macros[self.mode]

    def set_mode(self, key: str) -> None:
        """Switch mode (from the Modes page or the Mode box)."""
        self._set_mode(key)

    def set_behavior(self, key: str) -> None:
        """Switch Solo / Leader ↔ Party Member (Modes page or the Role box)."""
        self._set_behavior(key)

    def mode_label(self) -> str:
        """e.g. "Summer Event" or "Infinity Castle (party member)"."""
        mode = BY_KEY[self.mode]
        return mode.label + (" (party member)" if self.behavior == PARTY and mode.supports_party else "")

    def _set_behavior(self, key: str) -> None:
        if key not in BEHAVIORS:
            return
        if self.stats.running or any(t.isRunning() for t in self.macros.values()):
            # Not while running: put the box back.
            self.behavior_box.setCurrentIndex(self.behavior_box.findData(self.behavior))
            return
        changed = key != self.behavior
        self.behavior = key
        save_behavior(key)
        for thread in self.macros.values():
            if hasattr(thread, "set_behavior"):
                thread.set_behavior(key)
        index = self.behavior_box.findData(key)
        if self.behavior_box.currentIndex() != index:
            self.behavior_box.setCurrentIndex(index)
        if changed:
            self.log_panel.log(f"Role: {BEHAVIORS[key]}." + (
                " MAACRO plays the matches; the party leader picks what's next."
                if key == PARTY else ""))
            self.behavior_changed.emit(key)

    def _post_run(self, record) -> None:
        if getattr(record, "result", "") == "loss" and self.app_settings.loss_replay and len(self.replay) >= 3:
            job = self.replay.detach()

            def save():
                path = job.save()
                if path is not None:
                    self._log_bridge.line.emit(f"Loss replay saved: runs/{path.name} (the last minutes "
                                               "before the defeat; Discord: !replay).", "Info")
            threading.Thread(target=save, daemon=True).start()
        else:
            self.replay.clear()
        # A moment later, so the win/loss is already in the totals.
        mode = self.mode_label()
        room = getattr(self.macro, "room", None) if self.mode == "infinity_castle" else None
        QTimer.singleShot(3000, lambda: self.notifier.run_ended(record, self.stats, mode, room))

    def _post_drop(self, name: str, rarity: str) -> None:
        """Post the drop with the newest picture of the game (the drop popup)."""
        if not (self.notifier.config.valid and self.notifier.config.on_drop):
            return
        path = None
        image = self.capture.latest_qimage()
        if image is None:
            image = getattr(self, "_last_image", None)
        if image is not None:
            path = Path(tempfile.gettempdir()) / f"maacro_drop_{time.time_ns()}.jpg"
            if not image.save(str(path), "JPG", 90):
                path = None
        self.notifier.drop(name, rarity, path, self.mode_label())

    def _watch_for_alerts(self, message: str, level: str) -> None:
        if level == "Error" and ("check the game" in message or "Still stuck" in message):
            self.notifier.stuck(message)

    def _set_mode(self, key: str) -> None:
        if key not in BY_KEY:
            return
        if getattr(self, "mode", None) == key:
            return
        if getattr(self, "mode", None) and (self.stats.running or self.macro.isRunning()):
            # Switching while running: stop the running mode first.
            self.stop_macro()
        self.mode = key
        save_mode(key)
        index = self.mode_box.findData(key)
        if self.mode_box.currentIndex() != index:
            self.mode_box.setCurrentIndex(index)
        self.ic_box.setVisible(key == "infinity_castle")
        if hasattr(self, "pearls_row"):
            self.pearls_row.setVisible(key == "summer" or self.stats.pearls > 0)
        if hasattr(self, "cards_row"):
            self.cards_row.setVisible(key == "summer")
        self.log_panel.log(f"Mode: {BY_KEY[key].label}.")
        if hasattr(self, "behavior_box"):
            # A mode without party support just ignores the role (kept for the others).
            self.behavior_box.setEnabled(BY_KEY[key].supports_party and not self.stats.running)
        self.mode_changed.emit(key)

    def _set_card_strategy(self, value: str) -> None:
        """Save the Summer card-pick style; a running Summer macro uses it from
        the next card pick."""
        config = SummerConfig.load()
        if config.card_strategy != value:
            config.card_strategy = value
            try:
                config.save()
            except OSError as exc:
                self.log_panel.log(f"Couldn't save the card setting: {exc}", "Error")
                return
        summer = self.macros.get("summer")
        if summer is not None and getattr(summer, "settings", None) is not None:
            summer.settings.card_strategy = value
        self.log_panel.log(f"Card picks: {STRATEGIES.get(value, 'Easy')}.")

    def _on_ic_progress(self, info: dict) -> None:
        self.ic_room_value.setText("—" if info.get("room") is None else str(info["room"]))
        self.ic_cleared_value.setText(str(info.get("cleared", 0)))
        self.ic_retries_value.setText(str(info.get("retries", 0)))
        if info.get("note"):
            self.ic_note_value.setText(info["note"])

    # --- macro control -------------------------------------------------
    def start_macro(self) -> None:
        if self.stats.running or any(t.isRunning() for t in self.macros.values()):
            return
        self.macro.settings = BY_KEY[self.mode].config_class.load()
        self.macro.auto_profiles = AppSettings.load().auto_profiles
        runs_module.current_mode = self.mode_label()
        runs_module.current_cards = ""
        if hasattr(self.macro, "set_behavior"):
            self.macro.set_behavior(self.behavior)
        self.app_settings = AppSettings.load()
        reason = goal_reached(self.app_settings, self.stats.runs, self.stats.session_seconds,
                              self.stats.losses_in_row)
        if reason:
            self.log_panel.log(f"Session goal already reached ({reason}) — press Reset under "
                               "Session Results or change the goal in Settings first.", "Warn")
            return
        self.rejoin_watch.reset()
        self._started_at = datetime.now()
        self._reported_at = time.monotonic()
        stop = stop_time(self.app_settings.stop_at, self._started_at)
        if stop is not None:
            tomorrow = " tomorrow" if stop.date() > self._started_at.date() else ""
            self.log_panel.log(f"Stopping at {stop:%H:%M}{tomorrow} (Settings → Session goals).")
        self.run_setup_check(log_all=False)
        self.stats.start()
        self.mode_box.setEnabled(False)
        self.behavior_box.setEnabled(False)
        self.macro.start()
        self._resume_pending = False
        night_guard.mark_running(self.mode)
        if self.app_settings.keep_awake:
            night_guard.keep_awake(True)
        self.fresh.reset()
        self.replay.clear()
        # Bring Roblox to the front right away (not only on the first click).
        hwnd = self.capture.hwnd if hasattr(self, "capture") else None
        if hwnd:
            try:
                inp.focus(hwnd)
            except Exception:
                pass

    def stop_macro(self) -> None:
        if self._resume_pending:
            self._resume_pending = False
            self.log_panel.log("Resuming cancelled.")
        night_guard.clear_running()
        night_guard.keep_awake(False)
        if not self.stats.running and not self.macro.isRunning():
            return
        self.macro.requestInterruption()
        self.stats.stop()
        inp.release_all()
        self.mode_box.setEnabled(True)
        self.behavior_box.setEnabled(BY_KEY[self.mode].supports_party)
        self.log_panel.log("Macro stopped.")

    def _on_macro_finished(self) -> None:
        self.action_value.setText("—")
        reads, reused = getattr(self.detector, "reads", 0), getattr(self.detector, "reused", 0)
        if reads + reused:
            self.log_panel.log(f"Screen reading so far: {reads} reads, {reused} unchanged pictures "
                               f"skipped ({100 * reused // (reads + reused)}% saved).")
        self.mode_box.setEnabled(not self.stats.running)
        self.behavior_box.setEnabled(not self.stats.running and BY_KEY[self.mode].supports_party)
        if self.stats.running:      # loop ended by itself (F3 sets running off first)
            # Restart it, unless it keeps dying (then something needs fixing).
            now = time.monotonic()
            self._restarts = [t for t in getattr(self, "_restarts", []) if now - t < 600] + [now]
            if len(self._restarts) <= 5:
                self.log_panel.log("The macro stopped by itself — restarting it in 3 s.", "Warn")
                QTimer.singleShot(3000, self._restart_macro)
                return
            self.log_panel.log("The macro keeps stopping by itself (6 times in 10 min) — "
                               "leaving it stopped. Check the log above.", "Error")
            self.stats.stop()

    def _restart_macro(self) -> None:
        if self.stats.running and not self.macro.isRunning():
            self.macro.start()

    # --- app settings: hotkeys, goals, rejoin ---------------------------
    def apply_app_settings(self, settings: AppSettings | None = None) -> None:
        """Use new Settings-page values (hotkeys, goals, rejoin) right away."""
        self.app_settings = settings or AppSettings.load()
        s = self.app_settings
        self._start_vk = hotkey_vk(s.start_key) or inp.VK_F1
        self._stop_vk = hotkey_vk(s.stop_key) or inp.VK_F3
        self._keys_down.clear()
        self.start_button.setText(f"Start ({s.start_key})")
        self.stop_button.setText(f"Stop ({s.stop_key})")
        self.remote.configure(s.remote_enabled, s.remote_token, s.remote_channel, s.remote_user)
        for thread in self.macros.values():
            thread.auto_profiles = s.auto_profiles
        self._refresh_stats()
        self.refresh_lifetime()

    def refresh_lifetime(self) -> None:
        """All-time runs from runs.csv (after each run, and when asked)."""
        runs = load_runs()
        wins = sum(1 for r in runs if r.result == "win")
        self.lifetime_value.setText(f"{len(runs):,}" + (f" ({wins * 100 // len(runs)}% won)" if runs else ""))

    def _check_goals(self) -> None:
        if not self.stats.running:
            return
        reason = goal_reached(self.app_settings, self.stats.runs, self.stats.session_seconds,
                              self.stats.losses_in_row, started=getattr(self, "_started_at", None))
        if not reason:
            return
        self.log_panel.log(f"Session goal reached: {reason} — stopping.", "Warn")
        self.stop_macro()
        close = self.app_settings.close_roblox_at_goal
        self.notifier.session_finished(reason, self.stats, self.mode_label(), closed_roblox=close)
        if close:
            self.log_panel.log("Closing Roblox (Settings → Session goals).")
            threading.Thread(target=relaunch.close_roblox, daemon=True).start()

    def _check_rejoin(self) -> None:
        if self._relaunching:
            return
        # Modes that wait for the player on some screens (Any Stage with "leave
        # it to me", Challenge in the lobby) aren't "stuck" there.
        after_words = getattr(self.macro, "_after_words", None)
        allow_stuck = not (self.mode == "challenge" or (after_words is not None and after_words() is None))
        action, why = self.rejoin_watch.check(self.app_settings, self.stats.running,
                                              bool(self.capture.hwnd), self.detector.tracker.screen,
                                              allow_stuck=allow_stuck)
        if not action:
            return
        self.relaunch_roblox(action, why)

    def relaunch_roblox(self, action: str, why: str) -> bool:
        """Open Roblox ("open") or close and reopen it ("restart") on the
        server link. False if it can't (bad link, already relaunching)."""
        if self._relaunching:
            return False
        link = self.app_settings.server_link
        try:
            relaunch.launch_uri(link)
        except ValueError as exc:
            self.log_panel.log(f"Can't rejoin: the server link in Settings is wrong ({exc}).", "Error")
            self.rejoin_watch.note_launch()     # don't repeat this every 3 s
            return False
        where = relaunch.describe(link)
        self.log_panel.log(f"Rejoining: {why} — "
                           + ("closing Roblox and " if action == "restart" else "")
                           + f"opening it on {where}.", "Warn")
        self.notifier.rejoined(why, where)
        self.rejoin_watch.note_launch()
        self.fresh.reset()
        self._relaunching = True
        inp.release_all()

        def work():
            try:
                if action == "restart":
                    relaunch.close_roblox()
                    time.sleep(5)
                relaunch.open_roblox(link)
            except Exception as exc:
                self._log_bridge.line.emit(f"Couldn't open Roblox: {exc}", "Error")
            finally:
                self._relaunching = False
        threading.Thread(target=work, daemon=True).start()
        return True

    def _mode_asked_to_stop(self, reason: str) -> None:
        """A mode decided the session is over (e.g. Story: the last act is cleared)."""
        if not self.stats.running:
            return
        self.log_panel.log(f"Stopping: {reason}.", "Warn")
        self.stop_macro()
        self.notifier.session_finished(reason, self.stats, self.mode_label())

    def _maybe_report(self) -> None:
        """Settings → Discord: a status post every N minutes while running."""
        notifier = getattr(self, "notifier", None)      # the clock ticks once before it exists
        if notifier is None:
            return
        minutes = notifier.config.report_minutes
        if not (minutes and self.stats.running and notifier.config.valid):
            return
        if time.monotonic() - getattr(self, "_reported_at", 0.0) < minutes * 60:
            return
        self._reported_at = time.monotonic()
        image = self.capture.latest_qimage() or getattr(self, "_last_image", None)
        path = None
        if image is not None:
            path = Path(tempfile.gettempdir()) / f"maacro_report_{time.time_ns()}.jpg"
            if not image.save(str(path), "JPG", 85):
                path = None
        status = [f"Screen: {self.screen_value.text()} · Doing: {self.action_value.text()}",
                  f"Map: {self.map_value.text()} · Wave: {self.wave_value.text()}"]
        goal = self._goal_line()
        if goal:
            status.append(f"Goal: {goal}")
        self.notifier.report(self.stats, self.mode_label(), status, path)

    def _save_read_names(self, mode_key: str, found: dict) -> None:
        """Keep names read off the hotbar in the mode's setup (empty ones only)."""
        config = BY_KEY[mode_key].config_class.load()
        names = dict(config.unit_names)
        added = {k: n for k, n in found.items() if not str(names.get(k, "")).strip()}
        if not added:
            return
        names.update(added)
        config.unit_names = names
        try:
            config.save()
        except OSError as exc:
            self.log_panel.log(f"Couldn't save the unit names: {exc}", "Warn")
            return
        self.log_panel.log("Saved on the Configs page: " + ", ".join(f"unit {k} = {n}" for k, n in sorted(added.items())))

    # --- setup check -------------------------------------------------------
    def _sample_screen(self) -> None:
        latest = self.detector.latest
        if latest is not None:
            self._recent_screens.append(latest.screen)
        screen = self.detector.tracker.screen
        s = self.app_settings
        if self.stats.running and s.loss_replay:
            _, frame = self.capture.latest_frame()
            self.replay.add(frame, screen)
        if self.fresh.due(s.fresh_roblox_hours, self.stats.running, screen):
            if self.relaunch_roblox("restart", f"a fresh Roblox (every {s.fresh_roblox_hours} h, "
                                               "between matches)"):
                self.fresh.reset()
        if not self.stats.running and not self._resume_pending and night_guard.start_due(
                s.start_at, datetime.now(), self._start_at_fired):
            self._start_at_fired = datetime.now().date()
            self.log_panel.log(f"It's {s.start_at} — starting (Settings → Overnight).")
            self.start_macro()

    # --- overnight -------------------------------------------------------
    def _maybe_resume(self) -> None:
        """MAACRO closed while the macro ran (a crash, a PC restart): start again."""
        session = night_guard.interrupted_session()
        if session is None:
            return
        if not self.app_settings.resume_after_crash:
            night_guard.clear_running()
            return
        if session.get("mode") in BY_KEY:
            self.set_mode(session["mode"])
        self._resume_pending = True
        self.log_panel.log(f"MAACRO closed while running last time (a crash or a PC restart) — "
                           f"starting {self.mode_label()} again in {night_guard.RESUME_DELAY} s. "
                           f"Press {self.app_settings.stop_key} / Stop to cancel.", "Warn")
        QTimer.singleShot(night_guard.RESUME_DELAY * 1000, self._resume_now)

    def _resume_now(self) -> None:
        if self._resume_pending and not self.stats.running:
            self._resume_pending = False
            self.start_macro()

    def _ocr_error(self) -> str:
        if not hasattr(self, "_ocr_problem"):
            try:
                from ..vision.ocr import OcrReader
                OcrReader()
                self._ocr_problem = ""
            except Exception as exc:
                self._ocr_problem = str(exc)
        return self._ocr_problem

    def run_setup_check(self, log_all: bool = True) -> list[tuple[str, str]]:
        """Check the setup; problems go to the log (everything with log_all)."""
        found, minimized, width, height = window_state(self.capture.hwnd)
        facts = setup_check.Facts(found, minimized, width, height, self._ocr_error(),
                                  list(self._recent_screens), self.mode,
                                  BY_KEY[self.mode].config_class.load(), self.app_settings.rejoin)
        results = setup_check.check(facts)
        text = setup_check.summary(results)
        color = (theme.LOSS if any(l == setup_check.ERROR for l, _ in results)
                 else theme.WARN if any(l == setup_check.WARN for l, _ in results) else theme.WIN)
        self.setup_value.setText(text)
        self.setup_value.setStyleSheet(f"color: {color};")
        for level, line in results:
            if level == setup_check.OK and not log_all:
                continue
            self.log_panel.log(f"Setup: {line}", {"ok": "Info", "warn": "Warn", "error": "Error"}[level])
        return results

    # --- Discord remote control -----------------------------------------
    def _on_remote_command(self, text: str) -> None:
        self.log_panel.log(f"Discord remote: !{text}")
        command, _, argument = text.partition(" ")
        reply = self.remote.reply
        if command == "replay":
            path = latest_replay()
            if path is None:
                reply("No loss replay yet — one is saved after each defeat (Settings → Overnight).")
            else:
                reply(f"Last loss replay ({path.stem[:15]})", path)
        elif command == "mode":
            reply(self._remote_mode(argument))
        elif command == "goal":
            reply(self._remote_goal(argument))
        elif command == "help":
            reply(help_text())
        elif command == "status":
            reply(self._status_text())
        elif command == "stats":
            reply(self._stats_text())
        elif command == "ss":
            image = self.capture.latest_qimage() or getattr(self, "_last_image", None)
            if image is None:
                reply("No picture of the game yet — is Roblox open (not minimized)?")
                return
            path = Path(tempfile.gettempdir()) / f"maacro_ss_{time.time_ns()}.jpg"
            if not image.save(str(path), "JPG", 85):
                reply("Couldn't save the screenshot.")
                return
            reply(f"{self.mode_label()} — {self.screen_value.text()}", path, delete_after=True)
        elif command == "start":
            if self.stats.running:
                reply("Already running.")
                return
            self.start_macro()
            reply("Started." if self.stats.running else "Couldn't start — check the log (session goal reached?).")
        elif command == "stop":
            if not self.stats.running:
                reply("It isn't running.")
                return
            self.stop_macro()
            reply(f"Stopped. {self._session_line()}")
        elif command == "rejoin":
            ok = self.relaunch_roblox("restart", "asked from Discord")
            reply("Restarting Roblox…" if ok else "Can't rejoin right now (check the server link in Settings).")

    def _remote_mode(self, argument: str) -> str:
        names = ", ".join(f"`{m.key}`" for m in MODES)
        if not argument:
            return f"Mode: **{self.mode_label()}**. Switch with `!mode <name>`: {names}."
        key = find_mode(argument)
        if key is None:
            return f"No mode called '{argument}'. Modes: {names}."
        if key == self.mode:
            return f"Already on {self.mode_label()}."
        was_running = self.stats.running
        self.set_mode(key)
        if not was_running:
            return f"Mode: **{self.mode_label()}** (not started — `!start` to run it)."
        self._start_when_stopped(time.monotonic() + 15)
        return f"Switched to **{self.mode_label()}** — starting it as soon as the old mode has stopped."

    def _start_when_stopped(self, give_up_at: float) -> None:
        if any(t.isRunning() for t in self.macros.values()):
            if time.monotonic() < give_up_at:
                QTimer.singleShot(500, lambda: self._start_when_stopped(give_up_at))
            else:
                self.log_panel.log("The old mode didn't stop in 15 s — press Start yourself.", "Warn")
            return
        self.start_macro()

    def _remote_goal(self, argument: str) -> str:
        if not argument.isdigit() or int(argument) > 100000:
            return "Use `!goal 50` (a number of runs; `!goal 0` = no runs goal)."
        settings = AppSettings.load()
        settings.stop_after_runs = int(argument)
        settings.save()
        self.apply_app_settings(settings)
        if not settings.stop_after_runs:
            return "Runs goal off."
        line = f"Stopping after {settings.stop_after_runs} runs (now {self.stats.runs})."
        eta = self._eta()
        return line + (f" {eta}." if eta else "")

    def _eta(self) -> str:
        if not (self.stats.running and hasattr(self, "app_settings")):
            return ""
        return eta_text(self.app_settings, self.stats.runs, self.stats.session_seconds,
                        started=getattr(self, "_started_at", None))

    def _goal_line(self) -> str:
        """"12 / 50 runs — 38 runs left · ≈ 5 h (done ≈ 21:40)"; "" with no goal."""
        goal = goal_text(self.app_settings, self.stats.runs)
        if goal == "None":
            return ""
        eta = self._eta()
        return f"{goal} — {eta}" if eta else goal

    def _session_line(self) -> str:
        s = self.stats
        rate = f" ({s.win_rate:.0f}%)" if s.runs else ""
        return f"Session: {s.wins} wins, {s.losses} losses{rate} in {s.session_time_text()}."

    def _status_text(self) -> str:
        running = "🟢 Running" if self.stats.running else "🔴 Stopped"
        lines = [f"**{self.mode_label()}** — {running}",
                 f"Screen: {self.screen_value.text()} · Doing: {self.action_value.text()}",
                 f"Map: {self.map_value.text()} · Wave: {self.wave_value.text()}",
                 self._session_line()]
        goal = self._goal_line()
        if goal:
            lines.append(f"Goal: {goal}")
        return "\n".join(lines)

    def _stats_text(self) -> str:
        summary = summarize(load_runs())
        t, today = summary.total, summary.today
        lines = [self._session_line(),
                 f"Today: {today.runs} runs, {today.wins} wins" + (f" ({today.win_rate:.0f}%)" if today.runs else ""),
                 f"All time: {t.runs:,} runs, {t.wins:,} wins ({t.win_rate:.1f}%), best streak {summary.best_win_streak}, "
                 f"avg stage {hms(t.avg_seconds)}"]
        top = ", ".join(f"{g.name} {g.runs}" for g in summary.by_map[:3])
        if top:
            lines.append(f"Most played: {top}")
        if self.stats.drops:
            drops = sorted(self.stats.drops.items(), key=lambda kv: -kv[1])[:8]
            lines.append("Drops: " + ", ".join(f"{k} ×{n}" for k, n in drops))
        return "\n".join(lines)

    def _poll_hotkeys(self) -> None:
        for vk, action in ((self._start_vk, self.start_macro), (self._stop_vk, self.stop_macro)):
            if inp.is_pressed(vk):
                if vk not in self._keys_down:
                    self._keys_down.add(vk)
                    action()
            else:
                self._keys_down.discard(vk)

    def shutdown(self) -> None:
        self.remote.stop()
        if not self._session_ending:
            night_guard.clear_running()     # closed on purpose: nothing to resume
        night_guard.keep_awake(False)
        for thread in self.macros.values():
            thread.requestInterruption()
        for thread in self.macros.values():
            thread.wait(3000)

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
        self.pearls_row.setVisible(getattr(self, "mode", "") == "summer" or s.pearls > 0)
        self.charms_value.setText(str(s.drop_count("charm")))
        self.portals_value.setText(str(s.drop_count("portal")))
        drops = sorted(s.drops.items(), key=lambda kv: -kv[1])
        self.drops_list.setText("\n".join(f"{label} ×{n}" for label, n in drops) or "No drops yet")
        color = theme.WIN if s.running else theme.LOSS
        self.status_dot.setStyleSheet(f"color: {color}; background: transparent;")
        self.status_text.setText("Running" if s.running else "Not running")
        self.start_button.setEnabled(not s.running)
        self.stop_button.setEnabled(s.running)
        self._refresh_time()

    def _refresh_time(self) -> None:
        self.time_value.setText(self.stats.session_time_text())
        if hasattr(self, "app_settings") and hasattr(self, "goal_value"):
            self.goal_value.setText(goal_text(self.app_settings, self.stats.runs))
            eta = self._eta()
            self.eta_value.setText(eta.split(" · ", 1)[-1] if eta else "—")
            self.eta_row.setVisible(bool(eta))
            if self.app_settings.stop_after_minutes or self.app_settings.stop_at:
                self._check_goals()
            self._maybe_report()

    def _on_frame(self, image: QImage) -> None:
        self._last_image = image            # for drop posts
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
                self.log_panel.log("Captcha showing — type the number; MAACRO presses Submit once you stop typing.", "Warn")
        elif kind == "wave":
            self.wave_value.setText("—" if value is None else str(value))
        elif kind == "map":
            self.map_value.setText(str(value))
        elif kind == "result":
            self.notifier.note_result(value)
            if value == "win":
                self.stats.add_win()
                self.log_panel.log(f"VICTORY detected — win counted (run {self.stats.runs}).")
            else:
                self.stats.add_loss()
                self.log_panel.log(f"DEFEAT detected — loss counted (run {self.stats.runs}).", "Warn")
            # A moment later, so the end screen is recorded (and posted) first.
            QTimer.singleShot(4000, self._check_goals)
