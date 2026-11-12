"""The Detection page: what MAACRO reads from the screen right now.

Useful for checking detection, and for saving frames when something is
detected wrong (send those to fix it).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..capture import CaptureThread
from ..detector import DetectorThread
from ..vision.screens import SCREEN_LABELS, Detection
from .widgets import key_value_row, panel

CAPTURES_DIR = Path(__file__).resolve().parents[2] / "screens" / "captures"


class DetectionPage(QWidget):
    def __init__(self, capture: CaptureThread, detector: DetectorThread, parent=None):
        super().__init__(parent)
        self.capture = capture

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Detection", objectName="PageTitle"))
        layout.addWidget(QLabel(
            "What MAACRO reads from the Roblox window, updated a few times a second.",
            objectName="Muted"))

        top = QHBoxLayout()
        box, box_layout = panel("Right now")
        rows = {}
        for key in ("Screen (raw)", "Screen (steady)", "Wave", "Map", "Result",
                    "Placing menu", "Not enough money", "Read time"):
            row, rows[key] = key_value_row(key)
            box_layout.addWidget(row)
        self.rows = rows
        box_layout.addStretch()
        box.setFixedWidth(360)
        top.addWidget(box)

        box, box_layout = panel("Text on screen")
        self.text = QPlainTextEdit(readOnly=True)
        box_layout.addWidget(self.text)
        top.addWidget(box, 1)
        layout.addLayout(top, 1)

        actions = QHBoxLayout()
        save = QPushButton("Save current frame")
        save.setToolTip(f"Saves a screenshot of the game to {CAPTURES_DIR}")
        save.clicked.connect(self._save_frame)
        actions.addWidget(save)
        self.saved_label = QLabel("", objectName="Muted")
        actions.addWidget(self.saved_label)
        actions.addStretch()
        layout.addLayout(actions)

        detector.detection.connect(self._on_detection)
        detector.event.connect(self._on_event)

    def _on_detection(self, det: Detection, ms: float) -> None:
        self.rows["Screen (raw)"].setText(det.label)
        self.rows["Wave"].setText("—" if det.wave is None else str(det.wave))
        self.rows["Map"].setText(det.map_name or "—")
        self.rows["Result"].setText({"win": "Victory", "loss": "Defeat"}.get(det.result, "—"))
        self.rows["Placing menu"].setText("Yes" if det.placing else "No")
        self.rows["Not enough money"].setText("Yes" if det.no_money else "No")
        self.rows["Read time"].setText(f"{ms:.0f} ms")
        if self.isVisible():
            self.text.setPlainText("\n".join(line.text for line in det.lines))

    def _on_event(self, kind: str, value: object) -> None:
        if kind == "screen":
            self.rows["Screen (steady)"].setText(SCREEN_LABELS.get(value, str(value)))

    def _save_frame(self) -> None:
        _, frame = self.capture.latest_frame()
        if frame is None:
            self.saved_label.setText("No frame yet — is Roblox open?")
            return
        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        path = CAPTURES_DIR / f"{datetime.now():%Y%m%d_%H%M%S}.png"
        cv2.imwrite(str(path), cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR))
        self.saved_label.setText(f"Saved {path.name}")
