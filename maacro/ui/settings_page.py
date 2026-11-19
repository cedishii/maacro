"""The Settings page: session goals, Roblox server and auto-rejoin, hotkeys,
Discord updates (webhook) and performance."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .. import relaunch, remote
from ..app_settings import HOTKEYS, AppSettings
from ..goals import parse_time
from ..webhook import WebhookConfig
from . import theme
from .widgets import panel


class _Result(QObject):
    done = Signal(str)


def _spin(low: int, high: int, suffix: str, zero: str = "Off", tip: str = "") -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setSuffix(suffix)
    if zero:
        spin.setSpecialValueText(zero)
    spin.setToolTip(tip)
    spin.setFixedWidth(120)
    return spin


class SettingsPage(QWidget):
    def __init__(self, notifier, on_app_settings=None, parent=None):
        super().__init__(parent)
        self.notifier = notifier
        self.on_app_settings = on_app_settings or (lambda settings: None)

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
        header.addWidget(QLabel("Settings", objectName="PageTitle"))
        header.addStretch()
        self.app_message = QLabel("")
        header.addWidget(self.app_message)
        save_app = QPushButton("Save settings", objectName="StartButton")
        save_app.setToolTip("Save session goals, Roblox and hotkeys (applies right away).")
        save_app.clicked.connect(self.save_app_settings)
        header.addWidget(save_app)
        layout.addLayout(header)

        layout.addWidget(self._goals_box())
        layout.addWidget(self._roblox_box())
        layout.addWidget(self._hotkeys_box())
        layout.addWidget(self._profiles_box())
        layout.addWidget(self._discord_box())
        layout.addWidget(self._remote_box())
        layout.addWidget(self._performance_box())
        layout.addStretch()

        self.show_app_settings(AppSettings.load())

    # --- sections --------------------------------------------------------
    def _goals_box(self) -> QFrame:
        box, box_layout = panel("Session goals")
        box_layout.addWidget(QLabel(
            "Stop by itself once any goal is reached (counted from Start, or from the last Reset "
            "under Session Results). A Discord summary is posted if a webhook is set.",
            objectName="Muted", wordWrap=True))
        box_layout.addWidget(QLabel("Stop after:", objectName="Muted"))
        form = QFormLayout()
        self.stop_runs = _spin(0, 99999, " runs", tip="Stop after this many runs (wins + losses).")
        form.addRow("Runs", self.stop_runs)
        self.stop_minutes = _spin(0, 7 * 24 * 60, " min", tip="Stop after the macro has run this long.")
        self.stop_minutes.setSingleStep(30)
        form.addRow("Time running", self.stop_minutes)
        self.stop_losses = _spin(0, 99, " in a row",
                                 tip="Stop when the setup keeps failing (e.g. 3 losses in a row).")
        form.addRow("Losses in a row", self.stop_losses)
        self.stop_at = QLineEdit(placeholderText="e.g. 07:00 — empty = off")
        self.stop_at.setFixedWidth(170)
        self.stop_at.setToolTip("Stop at this time of day (24-hour clock). Started at 23:00 with "
                                "07:00 → stops at 07:00 the next morning.")
        form.addRow("Clock time", self.stop_at)
        box_layout.addLayout(form)
        self.close_at_goal = QCheckBox("Also close Roblox when a goal stops the macro")
        box_layout.addWidget(self.close_at_goal)
        return box

    def _roblox_box(self) -> QFrame:
        box, box_layout = panel("Roblox — server and auto-rejoin")
        box_layout.addWidget(QLabel(
            "Paste your private server link (Roblox → Servers → Private Servers → ⋯ → Copy Link). "
            "Leave it empty to join a public Anime Adventures server.", objectName="Muted",
            wordWrap=True))
        row = QHBoxLayout()
        self.server_link = QLineEdit(placeholderText="https://www.roblox.com/share?code=…&type=Server")
        self.server_link.setEchoMode(QLineEdit.EchoMode.Password)   # anyone with it can join
        row.addWidget(self.server_link, 1)
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(lambda on: self.server_link.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        row.addWidget(show)
        open_now = QPushButton("Open Roblox now")
        open_now.setToolTip("Open Roblox on this server right away (to check the link).")
        open_now.clicked.connect(self._open_now)
        row.addWidget(open_now)
        box_layout.addLayout(row)
        self.link_note = QLabel("", objectName="Muted")
        box_layout.addWidget(self.link_note)
        self.server_link.textChanged.connect(self._describe_link)

        self.rejoin = QCheckBox("Rejoin by itself while the macro runs")
        self.rejoin.setToolTip("Opens Roblox again on the link above when it closes, crashes or "
                               "stays disconnected. At most 6 times an hour, 3 min apart.")
        box_layout.addWidget(self.rejoin)
        form = QFormLayout()
        self.rejoin_closed = _spin(15, 3600, " s", zero="", tip="Roblox closed or crashed this long → open it.")
        form.addRow("Roblox closed for", self.rejoin_closed)
        self.rejoin_disconnected = _spin(30, 3600, " s", zero="",
                                         tip="The Disconnected box stayed up this long (Reconnect "
                                             "didn't help) → close Roblox and open it again.")
        form.addRow("Disconnected for", self.rejoin_disconnected)
        self.rejoin_stuck = _spin(0, 240, " min", tip="Stuck outside a match on one screen this long "
                                                       "→ restart Roblox. Off by default.")
        form.addRow("Stuck on one screen for", self.rejoin_stuck)
        box_layout.addLayout(form)
        self.rejoin.toggled.connect(self._enable_rejoin)
        return box

    def _hotkeys_box(self) -> QFrame:
        box, box_layout = panel("Hotkeys")
        form = QFormLayout()
        self.start_key = QComboBox()
        self.stop_key = QComboBox()
        for combo in (self.start_key, self.stop_key):
            combo.addItems(HOTKEYS)
            combo.setFixedWidth(120)
        form.addRow("Start", self.start_key)
        form.addRow("Stop", self.stop_key)
        box_layout.addLayout(form)
        box_layout.addWidget(QLabel("They work while Roblox is in front.", objectName="Muted"))
        return box

    def _profiles_box(self) -> QFrame:
        box, box_layout = panel("Profiles by map")
        self.auto_profiles = QCheckBox("Use the profile named after the map by itself")
        box_layout.addWidget(self.auto_profiles)
        box_layout.addWidget(QLabel(
            "Save a profile on the Configs page named after a map — e.g. \"Shibuya District\", or "
            "\"Rain Village Summer Hunt\" for one stage kind only — and that team and plan are used "
            "whenever a match on that map starts (before anything is placed). Other maps use the "
            "mode's own setup.", objectName="Muted", wordWrap=True))
        return box

    def _remote_box(self) -> QFrame:
        box, box_layout = panel("Discord remote control")
        box_layout.addWidget(QLabel(
            "Control MAACRO from your phone: !status, !stats, !ss (screenshot), !start, !stop, "
            "!rejoin, !help — answered only for your user ID.", objectName="Muted", wordWrap=True))
        guide = QLabel(
            "Set up once: discord.com/developers/applications → New Application → Bot → Reset Token "
            "(copy it) and switch on <b>Message Content Intent</b> → OAuth2 → URL Generator: scope "
            "<i>bot</i>, permissions View Channels, Send Messages, Attach Files, Read Message History "
            "→ open the link and add the bot to your server. Channel and user IDs: Discord Settings → "
            "Advanced → Developer Mode, then right-click the channel / your name → Copy ID.",
            objectName="Muted", wordWrap=True)
        guide.setTextFormat(Qt.TextFormat.RichText)
        box_layout.addWidget(guide)
        form = QFormLayout()
        self.remote_token = QLineEdit(placeholderText="Bot token")
        self.remote_token.setEchoMode(QLineEdit.EchoMode.Password)   # it controls the bot
        form.addRow("Bot token", self.remote_token)
        self.remote_channel = QLineEdit(placeholderText="Channel ID (numbers)")
        form.addRow("Channel ID", self.remote_channel)
        self.remote_user = QLineEdit(placeholderText="Your Discord user ID (numbers)")
        form.addRow("Your user ID", self.remote_user)
        box_layout.addLayout(form)
        row = QHBoxLayout()
        self.remote_enabled = QCheckBox("Listen for commands")
        row.addWidget(self.remote_enabled)
        self.remote_test = QPushButton("Test connection")
        self.remote_test.setToolTip("Connects the bot once (a new bot must, before it may post) "
                                    "and posts a hello in the channel.")
        self.remote_test.clicked.connect(self._test_remote)
        row.addWidget(self.remote_test)
        self.remote_message = QLabel("")
        self.remote_message.setWordWrap(True)
        row.addWidget(self.remote_message, 1)
        box_layout.addLayout(row)
        self._remote_result = _Result()
        self._remote_result.done.connect(self._remote_posted)
        return box

    def _test_remote(self) -> None:
        token = self.remote_token.text().strip()
        channel, user = self.remote_channel.text().strip(), self.remote_user.text().strip()
        if not token or not channel.isdigit() or not user.isdigit():
            self._remote_say("Fill in the token, and the channel and user IDs (numbers).", theme.LOSS)
            return
        self.remote_test.setEnabled(False)
        self._remote_say("Connecting…", theme.MUTED)
        self._gateway = remote.GatewayCheck(token, self)
        self._gateway.done.connect(lambda error, name: self._gateway_done(error, name, token, channel))
        self._gateway.start()

    def _gateway_done(self, error: str, name: str, token: str, channel: str) -> None:
        if error:
            self.remote_test.setEnabled(True)
            self._remote_say(f"Couldn't connect: {error}.", theme.LOSS)
            return
        self._remote_say(f"Connected as {name} — posting a hello…", theme.MUTED)

        def work():
            try:
                remote.post_message(token, channel, "👋 MAACRO is connected. Type `!help` for the commands.")
                self._remote_result.done.emit("")
            except remote.DiscordError as exc:
                self._remote_result.done.emit(str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _remote_posted(self, error: str) -> None:
        self.remote_test.setEnabled(True)
        if error:
            self._remote_say(f"Connected, but couldn't post: {error}.", theme.LOSS)
        else:
            self._remote_say("Works — check the channel. Tick 'Listen for commands' and Save settings.",
                             theme.WIN)

    def _remote_say(self, text: str, color: str) -> None:
        self.remote_message.setStyleSheet(f"color: {color};")
        self.remote_message.setText(text)

    def _discord_box(self) -> QFrame:
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
        self.on_drop = QCheckBox("Post each drop (Stage rewards) with a picture of it")
        self.on_stuck = QCheckBox("Alert when MAACRO is stuck or rejoins (at most every 5 min)")
        for widget in (self.on_run_end, self.screenshot, self.on_drop, self.on_stuck):
            box_layout.addWidget(widget)
        report_row = QHBoxLayout()
        report_row.addWidget(QLabel("Status post (picture + results) every"))
        self.report_minutes = _spin(0, 24 * 60, " min", tip="While the macro runs. Off = never.")
        self.report_minutes.setSingleStep(15)
        report_row.addWidget(self.report_minutes)
        report_row.addStretch()
        box_layout.addLayout(report_row)
        row = QHBoxLayout()
        save = QPushButton("Save webhook", objectName="StartButton")
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

        self._result = _Result()
        self._result.done.connect(self._tested)
        config = WebhookConfig.load()
        self.url.setText(config.url)
        self.mention.setText(config.mention)
        self.on_run_end.setChecked(config.on_run_end)
        self.screenshot.setChecked(config.screenshot)
        self.on_drop.setChecked(config.on_drop)
        self.on_stuck.setChecked(config.on_stuck)
        self.report_minutes.setValue(int(config.report_minutes or 0))
        return box

    def _performance_box(self) -> QFrame:
        from ..modes import light_mode, save_light_mode
        perf, perf_layout = panel("Performance")
        self.light = QCheckBox("Light mode — for slower PCs: 3 pictures and 2 screen reads a second "
                               "instead of 5 and 4 (MAACRO reacts a little slower)")
        self.light.setChecked(light_mode())
        self.light.toggled.connect(save_light_mode)
        perf_layout.addWidget(self.light)
        perf_layout.addWidget(QLabel("Applies right away. Off is fine on most PCs.", objectName="Muted"))
        return perf

    # --- app settings ----------------------------------------------------
    def show_app_settings(self, s: AppSettings) -> None:
        self.stop_runs.setValue(s.stop_after_runs)
        self.stop_minutes.setValue(s.stop_after_minutes)
        self.stop_losses.setValue(s.stop_after_losses_in_row)
        self.close_at_goal.setChecked(s.close_roblox_at_goal)
        self.stop_at.setText(s.stop_at)
        self.server_link.setText(s.server_link)
        self.rejoin.setChecked(s.rejoin)
        self.rejoin_closed.setValue(max(15, s.rejoin_closed_seconds))
        self.rejoin_disconnected.setValue(max(30, s.rejoin_disconnected_seconds))
        self.rejoin_stuck.setValue(s.rejoin_stuck_minutes)
        self.start_key.setCurrentText(s.start_key)
        self.stop_key.setCurrentText(s.stop_key)
        self.auto_profiles.setChecked(s.auto_profiles)
        self.remote_enabled.setChecked(s.remote_enabled)
        self.remote_token.setText(s.remote_token)
        self.remote_channel.setText(s.remote_channel)
        self.remote_user.setText(s.remote_user)
        self._enable_rejoin(s.rejoin)
        self._describe_link()

    def app_settings(self) -> AppSettings:
        return AppSettings(
            stop_after_runs=self.stop_runs.value(), stop_after_minutes=self.stop_minutes.value(),
            stop_after_losses_in_row=self.stop_losses.value(),
            close_roblox_at_goal=self.close_at_goal.isChecked(),
            stop_at=self.stop_at.text().strip(),
            start_key=self.start_key.currentText(), stop_key=self.stop_key.currentText(),
            server_link=self.server_link.text().strip(), rejoin=self.rejoin.isChecked(),
            rejoin_closed_seconds=self.rejoin_closed.value(),
            rejoin_disconnected_seconds=self.rejoin_disconnected.value(),
            rejoin_stuck_minutes=self.rejoin_stuck.value(),
            auto_profiles=self.auto_profiles.isChecked(),
            remote_enabled=self.remote_enabled.isChecked(),
            remote_token=self.remote_token.text().strip(),
            remote_channel=self.remote_channel.text().strip(),
            remote_user=self.remote_user.text().strip())

    def save_app_settings(self) -> None:
        settings = self.app_settings()
        if settings.stop_at and parse_time(settings.stop_at) is None:
            self._app_message("Stop time: use the 24-hour clock, like 07:00 or 23:30.", theme.LOSS)
            return
        if settings.start_key == settings.stop_key:
            self._app_message("Start and Stop need different keys.", theme.LOSS)
            return
        try:
            relaunch.launch_uri(settings.server_link)
        except ValueError as exc:
            self._app_message(f"Server link: {exc}", theme.LOSS)
            return
        if settings.remote_enabled and not (settings.remote_token and settings.remote_channel.isdigit()
                                            and settings.remote_user.isdigit()):
            self._app_message("Discord remote: fill in the token, channel ID and your user ID.", theme.LOSS)
            return
        try:
            settings.save()
        except OSError as exc:
            self._app_message(f"Couldn't save: {exc}", theme.LOSS)
            return
        self.on_app_settings(settings)
        self._app_message("Saved — applies right away.", theme.WIN)

    def _enable_rejoin(self, on: bool) -> None:
        for widget in (self.rejoin_closed, self.rejoin_disconnected, self.rejoin_stuck):
            widget.setEnabled(on)

    def _describe_link(self) -> None:
        link = self.server_link.text().strip()
        try:
            relaunch.launch_uri(link)
        except ValueError as exc:
            self.link_note.setStyleSheet(f"color: {theme.LOSS};")
            self.link_note.setText(str(exc))
            return
        self.link_note.setStyleSheet("")
        self.link_note.setText(f"Joins {relaunch.describe(link)}.")

    def _open_now(self) -> None:
        try:
            relaunch.open_roblox(self.server_link.text().strip())
        except (ValueError, OSError) as exc:
            self._app_message(f"Couldn't open Roblox: {exc}", theme.LOSS)
            return
        self._app_message("Opening Roblox…", theme.MUTED)

    def _app_message(self, text: str, color: str) -> None:
        self.app_message.setStyleSheet(f"color: {color};")
        self.app_message.setText(text)

    # --- Discord -----------------------------------------------------------
    def _config(self) -> WebhookConfig:
        return WebhookConfig(url=self.url.text().strip(), on_run_end=self.on_run_end.isChecked(),
                             screenshot=self.screenshot.isChecked(), on_stuck=self.on_stuck.isChecked(),
                             on_drop=self.on_drop.isChecked(),
                             mention=self.mention.text().strip(),
                             report_minutes=self.report_minutes.value())

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
