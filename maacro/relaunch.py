"""Opening Roblox on Anime Adventures by itself, and deciding when to.

`launch_uri` turns whatever server link the player pasted into a roblox://
link the Roblox app opens directly (no browser, no "Open Roblox?" prompt):

    https://www.roblox.com/share?code=XYZ&type=Server        (share link)
    https://www.roblox.com/games/8304191830/...?privateServerLinkCode=123
    roblox://...                                              (used as is)
    (empty)                                                   → a public AA server

`RejoinWatch` decides, from what the macro sees every few seconds, when to
open Roblox again: Roblox closed or crashed, the "Disconnected" box staying
up although Reconnect was pressed, or (optional) stuck on one screen for a
long time. It never fires more than MAX_PER_HOUR times an hour, so a broken
setup can't keep restarting Roblox forever.
"""
from __future__ import annotations

import os
import subprocess
import time
from urllib.parse import parse_qs, urlparse

AA_PLACE_ID = "8304191830"          # Anime Adventures
ROBLOX_EXE = "RobloxPlayerBeta.exe"
COOLDOWN = 180                      # s after a launch before another one
MAX_PER_HOUR = 6
CREATE_NO_WINDOW = 0x08000000


def launch_uri(link: str) -> str:
    """The roblox:// link to open for this server link. Raises ValueError
    if it isn't a Roblox server link."""
    link = (link or "").strip()
    if not link:
        return f"roblox://placeId={AA_PLACE_ID}"
    if link.lower().startswith("roblox://"):
        return link
    if link.isdigit():
        return f"roblox://placeId={link}"
    if "://" not in link:
        link = "https://" + link
    url = urlparse(link)
    host = (url.hostname or "").lower()
    if not (host == "roblox.com" or host.endswith(".roblox.com")):
        raise ValueError("That isn't a roblox.com link.")
    query = {k.lower(): v[0] for k, v in parse_qs(url.query).items() if v}
    if "code" in query and url.path.rstrip("/").lower().endswith("/share"):
        kind = query.get("type", "Server")
        return f"roblox://navigation/share_links?code={query['code']}&type={kind}"
    parts = [p for p in url.path.split("/") if p]
    place = next((p for p in parts if p.isdigit()), None)
    if place is None:
        raise ValueError("No game in that link (expected roblox.com/games/<id>/… or a share link).")
    code = query.get("privateserverlinkcode")
    if code:
        return f"roblox://placeId={place}&linkCode={code}"
    return f"roblox://placeId={place}"


def describe(link: str) -> str:
    """"private server (share link)" / "public server" — for the log."""
    try:
        uri = launch_uri(link)
    except ValueError:
        return "an invalid link"
    if "share_links" in uri:
        return "your private server (share link)"
    if "linkCode=" in uri:
        return "your private server"
    if link.strip().lower().startswith("roblox://"):
        return "your roblox:// link"
    return "a public server"


def roblox_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {ROBLOX_EXE}", "/NH"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return ROBLOX_EXE.lower() in out.lower()


def close_roblox() -> None:
    try:
        subprocess.run(["taskkill", "/IM", ROBLOX_EXE, "/F"], capture_output=True, timeout=15,
                       creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        pass


def open_roblox(link: str) -> None:
    """Open Roblox on the server link (raises ValueError for a bad link)."""
    os.startfile(launch_uri(link))      # handled by the Roblox app (roblox:// protocol)


class RejoinWatch:
    """Fed every few seconds by the Main page; says when to (re)open Roblox."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.reset()

    def reset(self) -> None:
        self._missing_since: float | None = None
        self._disconnected_since: float | None = None
        self._screen = ""
        self._screen_since = self.clock()
        self._launches: list[float] = []

    def note_launch(self) -> None:
        now = self.clock()
        self._launches.append(now)
        self._missing_since = self._disconnected_since = None
        self._screen_since = now

    def _allowed(self, now: float) -> bool:
        self._launches = [t for t in self._launches if now - t < 3600]
        if len(self._launches) >= MAX_PER_HOUR:
            return False
        return not self._launches or now - self._launches[-1] >= COOLDOWN

    def check(self, settings, running: bool, window_found: bool, screen: str,
              allow_stuck: bool = True) -> tuple[str, str]:
        """(action, why): action is "" (nothing), "open" (Roblox is closed:
        just open it) or "restart" (close Roblox, then open it).
        `allow_stuck` False: a mode that waits for the player on some screens
        (Any Stage) — the "stuck on one screen" rule is skipped."""
        now = self.clock()
        if screen != self._screen:
            self._screen, self._screen_since = screen, now
        if not window_found:
            if self._missing_since is None:
                self._missing_since = now
        else:
            self._missing_since = None
        if window_found and screen == "disconnected":
            if self._disconnected_since is None:
                self._disconnected_since = now
        else:
            self._disconnected_since = None
        if not (running and settings.rejoin) or not self._allowed(now):
            return "", ""
        if self._missing_since is not None and now - self._missing_since >= settings.rejoin_closed_seconds:
            return "open", f"Roblox has been closed for {int(now - self._missing_since)} s"
        if (self._disconnected_since is not None
                and now - self._disconnected_since >= settings.rejoin_disconnected_seconds):
            return "restart", f"disconnected for {int(now - self._disconnected_since)} s"
        stuck = settings.rejoin_stuck_minutes * 60
        if stuck and allow_stuck and window_found and screen not in ("in_match", "unit_manager", "card_pick") \
                and now - self._screen_since >= stuck:
            return "restart", f"stuck on the same screen for {int((now - self._screen_since) // 60)} min"
        return "", ""
