"""The Settings page: Discord updates (webhook)."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..webhook import WebhookConfig
from . import theme
from .widgets import panel


class _Result(QObject):
    done = Signal(str)


class SettingsPage(QWidget):
    def __init__(self, notifier, parent=None):
        super().__init__(parent)
        self.notifier = notifier
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Settings", objectName="PageTitle"))

        box, box_layout = panel("Discord updates")
        box_layout.addWidget(QLabel(
            "Paste a Discord webhook URL (channel → Edit Channel → Integrations → Webhooks → "
            "New Webhook → Copy Webhook URL). It's saved only on this PC.", objectName="Muted",
            wordWrap=True))
        form = QFormLayout()
        self.url = QLineEdit(placeholderText="https://discord.com/api/webhooks/…")
        self.url.setEchoMode(QLineEdit.EchoMode.Password)       # it works like a password
        form.addRow("Webhook URL", self.url)
        self.mention = QLineEdit(placeholderText="optional — your Discord user ID, to be pinged on alerts")
        form.addRow("Ping on alerts", self.mention)
        box_layout.addLayout(form)
        self.on_run_end = QCheckBox("Post every win/loss (times, streak, map/mode, totals, drops)")
        self.screenshot = QCheckBox("Attach the end-screen picture")
        self.on_stuck = QCheckBox("Alert when MAACRO is stuck and needs you (at most every 5 min)")
        for widget in (self.on_run_end, self.screenshot, self.on_stuck):
            box_layout.addWidget(widget)
        row = QHBoxLayout()
        save = QPushButton("Save", objectName="StartButton")
        save.clicked.connect(self.save)
        self.test_button = QPushButton("Send test message")
        self.test_button.clicked.connect(self.test)
        show = QPushButton("Show URL")
        show.setCheckable(True)
        show.toggled.connect(lambda on: self.url.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        row.addWidget(save)
        row.addWidget(self.test_button)
        row.addWidget(show)
        self.message = QLabel("")
        row.addWidget(self.message)
        row.addStretch()
        box_layout.addLayout(row)
        layout.addWidget(box)
        layout.addStretch()

        self._result = _Result()
        self._result.done.connect(self._tested)
        config = WebhookConfig.load()
        self.url.setText(config.url)
        self.mention.setText(config.mention)
        self.on_run_end.setChecked(config.on_run_end)
        self.screenshot.setChecked(config.screenshot)
        self.on_stuck.setChecked(config.on_stuck)

    def _config(self) -> WebhookConfig:
        return WebhookConfig(url=self.url.text().strip(), on_run_end=self.on_run_end.isChecked(),
                             screenshot=self.screenshot.isChecked(), on_stuck=self.on_stuck.isChecked(),
                             mention=self.mention.text().strip())

    def save(self) -> None:
        config = self._config()
        if config.url and not config.valid:
            self._message("That doesn't look like a Discord webhook URL.", theme.LOSS)
            return
        try:
            config.save()
        except OSError as exc:
            self._message(f"Couldn't save: {exc}", theme.LOSS)
            return
        self.notifier.reload()
        self._message("Saved." if config.url else "Saved (no webhook: Discord updates off).", theme.WIN)

    def test(self) -> None:
        config = self._config()
        if not config.valid:
            self._message("Paste a Discord webhook URL first.", theme.LOSS)
            return
        self.test_button.setEnabled(False)
        self._message("Sending…", theme.MUTED)
        threading.Thread(target=lambda: self._result.done.emit(self.notifier.test(config.url)),
                         daemon=True).start()

    def _tested(self, error: str) -> None:
        self.test_button.setEnabled(True)
        if error:
            self._message(error, theme.LOSS)
        else:
            self._message("Test message sent — check the channel. Press Save to keep it.", theme.WIN)

    def _message(self, text: str, color: str) -> None:
        self.message.setStyleSheet(f"color: {color};")
        self.message.setText(text)
