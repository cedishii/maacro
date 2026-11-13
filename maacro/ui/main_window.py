"""The MAACRO window: sidebar on the left, pages on the right."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from ..capture import CaptureThread
from ..detector import DetectorThread
from ..stats import SessionStats
from .configs_page import ConfigsPage
from .detection_page import DetectionPage
from .main_page import MainPage

# (icon, label, when it gets built)
PAGES = [
    ("▦", "Main", None),
    ("◈", "Modes", "Step 3: pick the gamemode and map."),
    ("☰", "Actions", "Step 4: what to click and when."),
    ("◉", "Recorder", "Step 4: record unit placement."),
    ("⚙", "Configs", None),
    ("⌕", "Detection", None),
    ("✦", "Settings", "Step 5: hotkeys, Discord updates and more."),
]


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

        self.capture = CaptureThread(fps=8, parent=self)
        self.detector = DetectorThread(self.capture, parent=self)
        self.main_page = MainPage(self.stats, self.capture, self.detector)
        built = {
            "Main": self.main_page,
            "Detection": DetectionPage(self.capture, self.detector),
            "Configs": ConfigsPage(),
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

        # Pages are connected; start watching the game.
        self.capture.start()
        self.detector.start()
        # Watchdog: if the capture or screen-reading thread ever ends by
        # itself, start it again (they're meant to run until MAACRO closes).
        self._closing = False
        self._thread_watch = QTimer(self, interval=5000, timeout=self._restart_dead_threads)
        self._thread_watch.start()

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
        for thread in (self.detector, self.capture):
            thread.requestInterruption()
        for thread in (self.detector, self.capture):
            thread.wait(3000)
        super().closeEvent(event)
