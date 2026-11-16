"""The MAACRO window: sidebar on the left, pages on the right."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from ..capture import CaptureThread
from ..detector import DetectorThread
from ..modes import light_mode
from ..stats import SessionStats
from .actions_page import ActionsPage
from .configs_page import ConfigsPage
from .detection_page import DetectionPage
from .main_page import MainPage
from .modes_page import ModesPage
from .recorder_page import RecorderPage
from .settings_page import SettingsPage

# (icon, label, when it gets built)
PAGES = [
    ("▦", "Main", None),
    ("◈", "Modes", None),
    ("☰", "Actions", None),
    ("◉", "Recorder", None),
    ("⚙", "Configs", None),
    ("⌕", "Detection", None),
    ("✦", "Settings", None),
]


NORMAL_CAPTURE_MS, LIGHT_CAPTURE_MS = 200, 333    # 5 or 3 pictures a second
NORMAL_READ_MS, LIGHT_READ_MS = 250, 500          # 4 or 2 screen reads a second


def lower_priority() -> None:
    """Run MAACRO below normal priority, so Roblox gets the CPU first."""
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x4000)   # BELOW_NORMAL
    except (OSError, AttributeError):
        pass


def placeholder_page(title: str, note: str) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.addWidget(QLabel(title, objectName="PageTitle"))
    layout.addWidget(QLabel(f"Coming soon. {note}", objectName="Muted"))
    layout.addStretch()
    return page


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"MAACRO v{__version__}")
        self.resize(1280, 760)
        self.setMinimumSize(1000, 600)

        self.stats = SessionStats(self)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        sidebar = QWidget(objectName="Sidebar")
        sidebar.setFixedWidth(84)
        sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(8, 0, 8, 12)
        side.setSpacing(4)
        brand = QLabel("MAACRO", objectName="Brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(brand)
        root.addWidget(sidebar)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        self.capture = CaptureThread(fps=5, parent=self)
        self.detector = DetectorThread(self.capture, parent=self)
        self.main_page = MainPage(self.stats, self.capture, self.detector)
        self.recorder_page = RecorderPage(self.capture, self.detector)
        self.detection_page = DetectionPage(self.capture, self.detector)
        built = {
            "Main": self.main_page,
            "Detection": self.detection_page,
            "Configs": ConfigsPage(),
            "Modes": ModesPage(self.main_page),
            "Settings": SettingsPage(self.main_page.notifier),
            "Actions": ActionsPage(),
            "Recorder": self.recorder_page,
        }

        group = QButtonGroup(self)
        group.setExclusive(True)
        for index, (icon, label, note) in enumerate(PAGES):
            page = built[label] if note is None else placeholder_page(label, note)
            self.pages.addWidget(page)
            button = QToolButton(objectName="NavButton")
            button.setText(f"{icon}\n{label}")
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setFixedSize(68, 54)
            button.clicked.connect(lambda _=False, i=index: self.pages.setCurrentIndex(i))
            group.addButton(button)
            side.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)
            if index == 0:
                button.setChecked(True)
        side.addStretch()

        # Show the window first, then start watching the game; lower MAACRO's
        # priority once it's open (while starting it needs the CPU).
        self._closing = False
        QTimer.singleShot(200, self._start_watching)
        QTimer.singleShot(5000, lower_priority)
        self._load_timer = QTimer(self, interval=500, timeout=self._set_load)
        self._load_timer.start()
        # Watchdog: if the capture or screen-reading thread ever ends by
        # itself, start it again (they're meant to run until MAACRO closes).
        self._closing = False
        self._thread_watch = QTimer(self, interval=5000, timeout=self._restart_dead_threads)
        self._thread_watch.start()

    def _start_watching(self) -> None:
        if not self._closing:
            self._set_load()
            self.capture.start()
            self.detector.start()

    def _set_load(self) -> None:
        """Full speed only while it's needed: the macro running, or a page that
        shows the game (Main, Detection, Recorder) on screen. Otherwise one
        picture and one read a second."""
        page = self.pages.currentWidget()
        visible = self.isVisible() and not self.isMinimized()
        running = self.main_page.stats.running or any(t.isRunning() for t in self.main_page.macros.values())
        shows_game = visible and page in (self.main_page, self.recorder_page, self.detection_page)
        self.capture.idle = self.detector.idle = not (running or shows_game)
        light = self._light_mode()
        self.capture.interval_ms = LIGHT_CAPTURE_MS if light else NORMAL_CAPTURE_MS
        self.detector.interval_ms = LIGHT_READ_MS if light else NORMAL_READ_MS
        # Everything placed and maxed, just watching the match: read less often.
        macro = self.main_page.macro
        m = getattr(macro, "match", None)
        self.detector.relaxed = bool(running and m is not None and m.upgrades_done and not m.pending
                                     and self.detector.tracker.screen == "in_match")
        self.capture.preview_wanted = visible and page in (self.main_page, self.recorder_page)

    def _light_mode(self) -> bool:
        """Settings → Light mode (read from mode.json at most every 2 s)."""
        now = time.monotonic()
        if now - getattr(self, "_light_read_at", -1e9) > 2:
            self._light_read_at, self._light = now, light_mode()
        return self._light

    def _restart_dead_threads(self) -> None:
        if self._closing:
            return
        for name, thread in (("Window capture", self.capture), ("Screen reading", self.detector)):
            if not thread.isRunning():
                self.main_page.log_panel.log(f"{name} stopped unexpectedly — restarting it.", "Warn")
                thread.start()

    def closeEvent(self, event) -> None:
        self._closing = True
        self.main_page.shutdown()
        self.recorder_page.shutdown()
        for thread in (self.detector, self.capture):
            thread.requestInterruption()
        for thread in (self.detector, self.capture):
            thread.wait(3000)
        super().closeEvent(event)
