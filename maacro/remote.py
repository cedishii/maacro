"""Discord remote control: run MAACRO from your phone.

You make a Discord bot (once), invite it to your server, and paste its token,
the channel to listen in and your own Discord user ID in Settings. MAACRO then
reads that channel every few seconds and answers commands from you only:

    !status        what it's doing (mode, screen, session results, runtime)
    !stats         session and all-time results
    !ss            a screenshot of the game
    !start, !stop  start / stop the macro
    !rejoin        close Roblox and open it again on your server link
    !help          this list

How it works: the channel is read with Discord's REST API (no extra library;
messages after the last one seen, every POLL_EVERY s). Replies are posted the
same way. Discord only lets a bot post once it has connected to the live
"gateway" one time, so "Test connection" on the Settings page does that
connection (Qt's WebSocket) and then closes it. Reading message text needs the
bot's "Message Content Intent" switched on in the Discord Developer Portal.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

API = "https://discord.com/api/v10"
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
USER_AGENT = "DiscordBot (MAACRO, 1.0)"
POLL_EVERY = 4.0
PREFIX = "!"
COMMANDS = {
    "status": "what MAACRO is doing right now",
    "stats": "session and all-time results",
    "ss": "a screenshot of the game",
    "start": "start the macro",
    "stop": "stop the macro",
    "rejoin": "close Roblox and open it again on your server link",
    "help": "this list",
}
ALIASES = {"screenshot": "ss", "shot": "ss", "s": "status", "info": "status", "commands": "help",
           "restart": "rejoin"}


def parse_command(content: str) -> str | None:
    """"!ss" → "ss"; anything that isn't a known command → None."""
    text = (content or "").strip().lower()
    if not text.startswith(PREFIX):
        return None
    word = text[len(PREFIX):].split(maxsplit=1)[0] if len(text) > len(PREFIX) else ""
    word = ALIASES.get(word, word)
    return word if word in COMMANDS else None


def new_commands(messages: list[dict], user_id: str, after: int) -> tuple[list[str], int]:
    """Commands from `user_id` in messages newer than `after` (oldest first),
    and the newest message id seen."""
    newest = after
    found = []
    for message in sorted(messages, key=lambda m: int(m.get("id", 0))):
        mid = int(message.get("id", 0))
        if mid <= after:
            continue
        newest = max(newest, mid)
        author = message.get("author") or {}
        if str(author.get("id", "")) != str(user_id) or author.get("bot"):
            continue
        command = parse_command(message.get("content", ""))
        if command:
            found.append(command)
    return found, newest


def help_text() -> str:
    return "**MAACRO commands**\n" + "\n".join(f"`{PREFIX}{name}` — {what}" for name, what in COMMANDS.items())


class DiscordError(Exception):
    pass


def _request(token: str, method: str, path: str, body: bytes | None = None,
             kind: str = "application/json", timeout: float = 15):
    request = urllib.request.Request(API + path, data=body, method=method, headers={
        "Authorization": f"Bot {token}", "User-Agent": USER_AGENT, "Content-Type": kind})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
                return json.loads(data) if data else None
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                try:
                    wait = float(json.loads(exc.read() or b"{}").get("retry_after", 2))
                except ValueError:
                    wait = 2
                time.sleep(min(wait, 30))
                continue
            reason = {401: "the bot token is wrong", 403: "the bot can't see or post in that channel "
                      "(invite it, and give it View Channel / Send Messages / Attach Files)",
                      404: "that channel ID wasn't found"}.get(exc.code, f"{exc.code} {exc.reason}")
            raise DiscordError(reason) from exc
        except (urllib.error.URLError, OSError) as exc:
            if attempt < 2:
                time.sleep(2)
                continue
            raise DiscordError(f"couldn't reach Discord ({exc})") from exc
    raise DiscordError("Discord kept saying 'slow down'")


def post_message(token: str, channel: str, text: str, image: Path | None = None) -> None:
    payload = {"content": text[:1900], "allowed_mentions": {"parse": []}}
    if image is not None and image.exists():
        boundary = uuid.uuid4().hex
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
            f"Content-Type: application/json\r\n\r\n".encode() + json.dumps(payload).encode() + b"\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{image.name}\"\r\n"
            f"Content-Type: image/jpeg\r\n\r\n".encode() + image.read_bytes() + b"\r\n",
            f"--{boundary}--\r\n".encode()])
        _request(token, "POST", f"/channels/{channel}/messages", body,
                 f"multipart/form-data; boundary={boundary}", timeout=30)
    else:
        _request(token, "POST", f"/channels/{channel}/messages", json.dumps(payload).encode())


class RemoteControl(QObject):
    """Reads the channel on a background thread; `command` is emitted (on the
    window's thread) for each command from the player."""
    command = Signal(str)
    log = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.token = self.channel = self.user = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def configure(self, enabled: bool, token: str, channel: str, user: str) -> None:
        """Start, restart or stop listening for these settings."""
        changed = (token, channel, user) != (self.token, self.channel, self.user)
        if self.running and (changed or not enabled):
            self.stop()
        self.token, self.channel, self.user = token.strip(), channel.strip(), user.strip()
        if enabled and not self.running and self.token and self.channel.isdigit() and self.user.isdigit():
            self._stop = threading.Event()
            self._thread = threading.Thread(target=self._poll, args=(self._stop,), daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def reply(self, text: str, image: Path | None = None, delete_after: bool = False) -> None:
        token, channel = self.token, self.channel

        def work():
            try:
                post_message(token, channel, text, image)
            except DiscordError as exc:
                self.log.emit(f"Discord remote: reply not sent — {exc}.", "Warn")
            finally:
                if delete_after and image is not None:
                    try:
                        image.unlink(missing_ok=True)
                    except OSError:
                        pass
        threading.Thread(target=work, daemon=True).start()

    def _poll(self, stop: threading.Event) -> None:
        token, channel, user = self.token, self.channel, self.user
        after = None
        failures = 0
        while not stop.is_set():
            try:
                if after is None:
                    latest = _request(token, "GET", f"/channels/{channel}/messages?limit=1") or []
                    after = int(latest[0]["id"]) if latest else 0
                    self.log.emit("Discord remote: listening — type !help in the channel.", "Info")
                else:
                    messages = _request(token, "GET", f"/channels/{channel}/messages?limit=20&after={after}") or []
                    commands, after = new_commands(messages, user, after)
                    for command in commands:
                        self.command.emit(command)
                failures = 0
            except DiscordError as exc:
                failures += 1
                if failures in (1, 5) or failures % 50 == 0:
                    self.log.emit(f"Discord remote: {exc}.", "Warn")
                if "token is wrong" in str(exc) or "wasn't found" in str(exc):
                    self.log.emit("Discord remote stopped — fix it in Settings.", "Error")
                    return
            except (ValueError, KeyError, TypeError) as exc:
                self.log.emit(f"Discord remote: odd reply from Discord ({exc}).", "Warn")
            stop.wait(POLL_EVERY * (1 if failures < 3 else 4))


class GatewayCheck(QObject):
    """Connects the bot to Discord's gateway once (required before a new bot
    may post) and reports the bot's name. `done(error, bot_name)`."""
    done = Signal(str, str)

    def __init__(self, token: str, parent=None):
        super().__init__(parent)
        from PySide6.QtWebSockets import QWebSocket
        self.token = token.strip()
        self.socket = QWebSocket()
        self.socket.textMessageReceived.connect(self._on_text)
        self.socket.errorOccurred.connect(lambda _e: self._finish(f"couldn't connect ({self.socket.errorString()})"))
        self.socket.disconnected.connect(self._on_closed)
        self._finished = False
        self._timer = QTimer(self, singleShot=True, interval=15000,
                         timeout=lambda: self._finish("Discord didn't answer in 15 s"))

    def start(self) -> None:
        self._timer.start()
        self.socket.open(QUrl(GATEWAY))

    def _on_text(self, text: str) -> None:
        try:
            data = json.loads(text)
        except ValueError:
            return
        if data.get("op") == 10:            # Hello → identify
            self.socket.sendTextMessage(json.dumps({"op": 2, "d": {
                "token": self.token, "intents": 0,
                "properties": {"os": "windows", "browser": "MAACRO", "device": "MAACRO"}}}))
        elif data.get("op") == 0 and data.get("t") == "READY":
            user = (data.get("d") or {}).get("user") or {}
            self._finish("", user.get("username", "your bot"))

    def _on_closed(self) -> None:
        code = self.socket.closeCode()
        code = int(code.value) if hasattr(code, "value") else int(code)
        reason = {4004: "the bot token is wrong", 4014: "a privileged intent isn't allowed"}.get(
            code, f"the connection closed (code {code})")
        self._finish(reason)

    def _finish(self, error: str, name: str = "") -> None:
        if self._finished:
            return
        self._finished = True
        self._timer.stop()
        self.done.emit(error, name)
        self.socket.close()
