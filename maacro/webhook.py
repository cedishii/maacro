"""Discord webhook updates: a message when a run ends (result, times, streak,
map/mode, totals, drops, end-screen picture) and an alert when MAACRO is
stuck and needs the player.

The webhook URL is the player's own, saved in webhook.json next to the app
(kept out of git). Messages are sent on a background thread so a slow or
failing connection never holds up the macro or the window.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBHOOK_PATH = ROOT / "webhook.json"
RUNS_DIR = ROOT / "runs"
GREEN, RED, AMBER, BLUE = 0x4ADE80, 0xF87171, 0xFBBF24, 0x8B5CF6
ALERT_EVERY = 300       # seconds: at most one stuck alert per 5 minutes


@dataclass
class WebhookConfig:
    url: str = ""
    on_run_end: bool = True         # a message after every win/loss
    screenshot: bool = True         # attach the end screen
    on_stuck: bool = True           # alert when MAACRO says it needs you
    mention: str = ""               # optional Discord user ID to ping on alerts

    @classmethod
    def load(cls, path: Path = WEBHOOK_PATH) -> "WebhookConfig":
        config = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return config
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config

    def save(self, path: Path = WEBHOOK_PATH) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @property
    def valid(self) -> bool:
        return self.url.startswith(("https://discord.com/api/webhooks/",
                                    "https://discordapp.com/api/webhooks/",
                                    "https://ptb.discord.com/api/webhooks/",
                                    "https://canary.discord.com/api/webhooks/"))


def _post(url: str, payload: dict, image: Path | None = None, timeout: float = 15) -> str:
    """Send one webhook message. Returns "" on success, else the error."""
    if image is not None and image.exists():
        boundary = uuid.uuid4().hex
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
            f"Content-Type: application/json\r\n\r\n".encode() + json.dumps(payload).encode() + b"\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{image.name}\"\r\n"
            f"Content-Type: image/png\r\n\r\n".encode() + image.read_bytes() + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        body, kind = b"".join(parts), f"multipart/form-data; boundary={boundary}"
    else:
        body, kind = json.dumps(payload).encode(), "application/json"
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": kind, "User-Agent": "MAACRO"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout):
                return ""
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:          # rate limited: wait and retry
                time.sleep(2 + attempt * 3)
                continue
            return f"Discord said {exc.code} {exc.reason}"
        except (urllib.error.URLError, OSError) as exc:
            if attempt < 2:
                time.sleep(2)
                continue
            return f"Couldn't reach Discord: {exc}"
    return "Couldn't send"


def _hms(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class Notifier:
    """Builds and sends the messages. `log(message, level)` reports failures."""

    def __init__(self, log=None):
        self.log = log or (lambda message, level="Info": None)
        self.config = WebhookConfig.load()
        self.streak = 0                 # +n wins in a row, -n losses in a row
        self.drops: list[str] = []      # since the last run message
        self._last_alert = 0.0

    def reload(self) -> None:
        self.config = WebhookConfig.load()

    def note_result(self, result: str) -> None:
        if result == "win":
            self.streak = self.streak + 1 if self.streak > 0 else 1
        else:
            self.streak = self.streak - 1 if self.streak < 0 else -1

    def note_drop(self, name: str, rarity: str) -> None:
        label = (name or "Item") + (f" ({rarity})" if rarity else "")
        self.drops.append(label)

    def _send(self, payload: dict, image: Path | None = None) -> None:
        url = self.config.url
        def work():
            error = _post(url, payload, image)
            if error:
                self.log(f"Discord update not sent: {error}", "Warn")
        threading.Thread(target=work, daemon=True).start()

    def run_ended(self, record, stats, mode_label: str, room: int | None = None) -> None:
        """The message after a win or loss (record: runs.RunRecord)."""
        if not (self.config.valid and self.config.on_run_end):
            self.drops.clear()
            return
        win = record.result == "win"
        title = ("✅ Stage Complete" if win else "❌ Stage Failed")
        if room is not None:
            title = f"✅ Room {room} cleared" if win else f"❌ Room {room} lost — retrying"
        streak = (f"{self.streak} win streak" if self.streak > 0
                  else f"{-self.streak} loss streak" if self.streak < 0 else "—")
        fields = [
            {"name": "⏱ Runtime", "value": f"`{_hms(stats.session_seconds)}`", "inline": True},
            {"name": "⏱ Stage time", "value": f"`{record.duration or '?'}`", "inline": True},
            {"name": "🔥 Streak", "value": f"`{streak}`", "inline": True},
            {"name": "🗺 Map / Mode", "value": f"`{record.map_name or '?'}` • `{mode_label}`", "inline": False},
            {"name": "📊 Results", "value": f"✅ `{stats.wins}`  ❌ `{stats.losses}`  📈 `{stats.runs}` "
                                           f"(`{stats.win_rate:.1f}%`)", "inline": False},
        ]
        if record.waves:
            fields.insert(3, {"name": "🌊 Waves", "value": f"`{record.waves}`", "inline": True})
        if record.pearls:
            fields.append({"name": "🐚 Earned", "value": f"`+{record.pearls:,}` (session `{stats.pearls:,}`)",
                           "inline": False})
        if self.drops:
            fields.append({"name": "🎁 Drops", "value": "\n".join(f"• {d}" for d in self.drops)[:1000],
                           "inline": False})
        embed = {"title": title, "color": GREEN if win else RED, "fields": fields,
                 "footer": {"text": "MAACRO"}, "timestamp": datetime.now(timezone.utc).isoformat()}
        image = None
        if self.config.screenshot and record.screenshot:
            image = RUNS_DIR / record.screenshot
            embed["image"] = {"url": f"attachment://{image.name}"}
        self.drops.clear()
        self._send({"username": "MAACRO", "embeds": [embed]}, image)

    def stuck(self, message: str) -> None:
        """An alert when MAACRO asks the player to check the game."""
        if not (self.config.valid and self.config.on_stuck):
            return
        now = time.monotonic()
        if now - self._last_alert < ALERT_EVERY:
            return
        self._last_alert = now
        ping = f"<@{self.config.mention.strip()}> " if self.config.mention.strip().isdigit() else ""
        self._send({"username": "MAACRO", "content": ping or None,
                    "embeds": [{"title": "⚠ MAACRO needs you", "description": message[:1500],
                                "color": AMBER, "timestamp": datetime.now(timezone.utc).isoformat()}]})

    def test(self, url: str) -> str:
        """Send a test message right away (called from the Settings page).
        Returns "" on success, else the error."""
        return _post(url, {"username": "MAACRO", "embeds": [{
            "title": "MAACRO is connected", "color": BLUE,
            "description": "Run results and alerts will be posted here.",
            "timestamp": datetime.now(timezone.utc).isoformat()}]})
