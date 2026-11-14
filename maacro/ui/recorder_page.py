"""The Recorder page: place units by hand, MAACRO saves the spots as General
mode zones for that map (see maacro/recorder.py)."""
from __future__ import annotations

from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget,
)

from ..capture import CaptureThread
from ..detector import DetectorThread
from ..general.maps import maps_for_general
from ..maps import find_map, name_box
from ..recorder import ClickWatcher, Recording, draw_spots, save_recording, usable
from . import theme
from .widgets import LiveView, panel

HOW_TO = (
    "1. Start a match and zoom all the way out (hold O), like MAACRO does — the spots are "
    "saved for that camera view, so don't move the camera while recording.\n"
    "2. Press Record, then place your units as usual: press the unit's key (1–6) or click its "
    "card, then click where it goes. Each spot shows up below. Right click or Esc cancels.\n"
    "3. Check the map name and press Save. General mode then places each recorded unit in "
    "its spots on that map (\"Use saved map zones\" on). Units you didn't record keep their "
    "old zones, or get automatic spots."
)


def to_qimage(image) -> QImage:
    height, width = image.shape[:2]
    return QImage(image.data, width, height, image.strides[0], QImage.Format.Format_BGR888).copy()


class RecorderPage(QWidget):
    def __init__(self, capture: CaptureThread, detector: DetectorThread, parent=None):
        super().__init__(parent)
        self.capture, self.detector = capture, detector
        self.recording = Recording()
        self.watcher: ClickWatcher | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Recorder", objectName="PageTitle"))
        how = QLabel(HOW_TO, objectName="Muted")
        how.setWordWrap(True)
        layout.addWidget(how)

        top = QHBoxLayout()
        top.addWidget(QLabel("Map"))
        self.map_name = QLineEdit(placeholderText="Map name, as in the title at the top of the match")
        top.addWidget(self.map_name, 1)
        detect = QPushButton("Detect")
        detect.setToolTip("Read the map name from the game.")
        detect.clicked.connect(self._detect_map)
        top.addWidget(detect)
        self.record_button = QPushButton("Record", objectName="StartButton")
        self.record_button.clicked.connect(self._toggle)
        top.addWidget(self.record_button)
        layout.addLayout(top)

        self.status = QLabel("Not recording.", objectName="Muted")
        layout.addWidget(self.status)

        body = QHBoxLayout()
        self.view = LiveView()
        body.addWidget(self.view, 3)
        box, side = panel("Recorded spots")
        self.spots = QListWidget()
        side.addWidget(self.spots, 1)
        buttons = QHBoxLayout()
        undo = QPushButton("Undo last")
        undo.clicked.connect(self._undo)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)
        buttons.addWidget(undo)
        buttons.addWidget(clear)
        side.addLayout(buttons)
        save = QPushButton("Save", objectName="StartButton")
        save.clicked.connect(self._save)
        side.addWidget(save)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        side.addWidget(self.message)
        box.setMinimumWidth(260)
        body.addWidget(box, 1)
        layout.addLayout(body, 1)

        capture.frame_ready.connect(self._on_frame)

    # --- live view ---------------------------------------------------------
    def _on_frame(self, _image) -> None:
        if not self.isVisible():
            return
        _, frame = self.capture.latest_frame()
        if frame is not None:
            self.view.set_frame(to_qimage(draw_spots(frame, self.recording)))

    # --- recording ---------------------------------------------------------
    def _toggle(self) -> None:
        if self.watcher is not None:
            self._stop()
            return
        if not self.capture.hwnd:
            self._say("Roblox isn't open.", theme.LOSS)
            return
        if not self.map_name.text().strip():
            self._detect_map()
        self.watcher = ClickWatcher(lambda: self.capture.hwnd, self)
        self.watcher.picked.connect(lambda key: self.status.setText(
            f"Recording — unit {key} picked, click where it goes (right click / Esc cancels)."))
        self.watcher.cancelled.connect(lambda: self.status.setText("Recording — pick cancelled."))
        self.watcher.placed.connect(self._placed)
        self.watcher.start()
        self.record_button.setText("Stop")
        self.status.setText("Recording — pick a unit (1–6 or its card), then click where it goes.")

    def _stop(self) -> None:
        if self.watcher is not None:
            self.watcher.requestInterruption()
            self.watcher.wait(1000)
            self.watcher = None
        self.record_button.setText("Record")
        self.status.setText(f"Not recording. {len(self.recording.spots)} spot(s) recorded.")

    def _placed(self, key: str, x: float, y: float) -> None:
        _, frame = self.capture.latest_frame()
        if frame is None:
            return
        height, width = frame.shape[:2]
        if self.recording.size != (width, height):
            if self.recording.spots:
                self._say("The Roblox window changed size — recording again from here.", theme.LOSS)
            self.recording = Recording(size=(width, height))
            self.spots.clear()
        self._read_anchor(height)
        self.recording.add(key, x, y)
        note = "" if usable(x, y, width, height) else "  ⚠ too close to the edge — MAACRO won't use it"
        self.spots.addItem(f"Unit {key} at ({int(x)}, {int(y)}){note}")
        self.spots.scrollToBottom()
        self.status.setText(f"Recording — unit {key} placed. Pick the next unit.")

    def _read_anchor(self, height: int) -> None:
        """Where the map title is, to line the spots up with later matches."""
        det, name = self.detector.latest, self.map_name.text().strip()
        if det is not None and name:
            box = name_box(det.lines, name, height)
            if box is not None:
                self.recording.anchor = box

    def _detect_map(self) -> None:
        det = self.detector.latest
        found = find_map(maps_for_general(), det.lines) if det is not None else None
        if found is not None:
            self.map_name.setText(found.name)
            self._say(f"Map: {found.name}.", theme.WIN)
        else:
            self._say("Couldn't tell the map — type its name as shown at the top of the match.",
                      theme.LOSS)

    def _undo(self) -> None:
        self.recording.undo()
        if self.spots.count():
            self.spots.takeItem(self.spots.count() - 1)

    def _clear(self) -> None:
        self.recording = Recording(size=self.recording.size, anchor=self.recording.anchor)
        self.spots.clear()

    def _save(self) -> None:
        _, frame = self.capture.latest_frame()
        if self.recording.anchor is None and frame is not None:
            self._read_anchor(frame.shape[0])
        try:
            path = save_recording(self.map_name.text(), self.recording, frame)
        except (ValueError, OSError) as exc:
            self._say(str(exc), theme.LOSS)
            return
        units = " ".join(sorted(self.recording.by_unit()))
        lined_up = "" if self.recording.anchor else (
            " (the map title wasn't readable, so the spots are lined up from the window size)")
        self._say(f"Saved {len(self.recording.spots)} spot(s) for unit(s) {units} to "
                  f"maps/general/{path.name}{lined_up}. Press Start again in General mode to use them.", theme.WIN)

    def _say(self, text: str, color: str) -> None:
        self.message.setStyleSheet(f"color: {color};")
        self.message.setText(text)

    def shutdown(self) -> None:
        self._stop()
