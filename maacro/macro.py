"""The run loop: looks at the current screen and does the next step.

Lobby → Play → walk into the ring → Find Match → (captcha: player types, macro submits)
→ vote Yes → match (place units → upgrade to Max, pick cards) → Next
→ Return to lobby → repeat.
"""
from __future__ import annotations

import math

import cv2
import time
import pyautogui
import traceback
from pathlib import Path
import winsound
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from PySide6.QtCore import QThread, Signal

from .capture import CaptureThread
from .config import MacroConfig
from .control import input as inp
from .detector import DetectorThread
from .maps import MapZones, find_map, load_maps, spread
from .runs import read_run, save_run
from screen_numbers import read_number, type_text
from .placement import drop_red_spots, find_green_buttons, placeable_spots, spots_to_try, upgrade_order

SPOTS_PER_TRY = 12      # then give up for now, so card picks etc. aren't blocked
CAPTCHA_SUBMIT_AFTER = 1.5   # seconds the typed answer must stay the same before Submit
from .vision.cards import (choose_card, find_cards, needs_votes, predicted_vote_button, read_card_texts,
                           read_votes, vote_button)
from .vision.numbers import GuardedNumberReader, make_number_reader
from .vision.hotbar import read_unit_count
from .vision.ocr import OcrLine, OcrReader
from .vision.screens import Detection, _norm, fuzzy_in

# Seeing one of these means a new match is coming: start its plan fresh.
NEW_MATCH_SCREENS = {"lobby", "match_found", "loading", "vote_start"}


def narrow_to_words(line: OcrLine, keyword: str) -> OcrLine:
    """The part of `line` whose words best match `keyword`."""
    n = len(keyword.split())
    if not line.words or len(line.words) <= n:
        return line
    key = _norm(keyword)
    best, best_ratio = None, -1.0
    for start in range(len(line.words) - n + 1):
        window = line.words[start:start + n]
        ratio = SequenceMatcher(None, key, _norm("".join(w.text for w in window))).ratio()
        if ratio > best_ratio:
            best, best_ratio = window, ratio
    left = min(w.x for w in best)
    top = min(w.y for w in best)
    right = max(w.x + w.w for w in best)
    bottom = max(w.y + w.h for w in best)
    return OcrLine(" ".join(w.text for w in best), left, top, right - left, bottom - top, best)


UPGRADE_RECHECK = 40     # seconds before looking at a "maxed" manager again


@dataclass
class MatchState:
    """What's been done in the current match."""
    pending: list[str] = field(default_factory=list)    # hotbar keys still to place
    placed: int = 0
    failures: dict[str, int] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)  # last placed-count read per key
    failed_spots: list[tuple[float, float]] = field(default_factory=list)
    zoomed: bool = False
    spots: list[tuple[float, float]] = field(default_factory=list)
    spot_cursor: int = 0            # where the next placing try continues in the spot list
    upgrades_done: bool = False
    upgrades_done_at: float = 0.0   # when it last looked maxed (checked again later)
    maxed_logged: bool = False
    no_upgrade_reads: int = 0
    close_tries: int = 0            # F presses to close a manager that's in the way
    card_voted: bool = False
    card_clicked: bool = False
    vote_target: tuple[float, float] | None = None
    recorded: bool = False          # this run's rewards are noted
    card_seen_at: float = 0.0       # when the current card pick appeared
    voted_start: bool = False


class MacroThread(QThread):
    status = Signal(str)            # what the macro is doing right now
    log = Signal(str, str)          # message, level
    run_recorded = Signal(object)   # RunRecord, when a run ends
    drop_found = Signal(str, str)   # item name, rarity (either may be "")

    def __init__(self, capture: CaptureThread, detector: DetectorThread,
                 settings: MacroConfig | None = None, parent=None):
        super().__init__(parent)
        self.capture = capture
        self.detector = detector
        self.settings = settings or MacroConfig()
        self.numbers: GuardedNumberReader | None = None
        self._ocr: OcrReader | None = None      # for the hotbar counter (this thread's own)
        self.match = MatchState()
        self._last_done: dict[str, float] = {}
        self._status = ""
        self._screen = "unknown"
        self._manager_seen_at = 0.0     # last time any read showed the unit manager
        self._maps: list[MapZones] = []
        self._map: MapZones | None = None     # current map, if the player saved zones for it
        self._map_warned = False
        self._map_walked = False        # this match's map walk is done
        self._matchmaking_at = -1e9     # last time matchmaking / verification / match found showed
        self._upgrade_clicks = 0
        self._last_error = ""           # last crash logged by _report_error
        self._last_error_at = 0.0
        self._error_repeats = 0

    # --- helpers -------------------------------------------------------
    def _say(self, status: str, log: bool = True, level: str = "Info") -> None:
        if status != self._status:
            self._status = status
            self.status.emit(status)
            if log:
                self.log.emit(status, level)

    def _report_error(self, exc: Exception) -> None:
        """Log a crash from one loop step without stopping the macro.

        The full traceback is logged the first time; if the same error keeps
        repeating, only a short line is logged every 30 seconds."""
        details = traceback.format_exception(exc)
        where = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
        place = f" ({Path(where.filename).name} line {where.lineno}, in {where.name})" if where else ""
        summary = f"Error on screen '{self._screen}': {type(exc).__name__}: {exc}{place}"
        now = time.monotonic()
        if summary == self._last_error:
            self._error_repeats += 1
            if now - self._last_error_at >= 30:
                self._last_error_at = now
                self.log.emit(f"{summary} — still happening ({self._error_repeats}x)", "Error")
            return
        self._last_error, self._last_error_at, self._error_repeats = summary, now, 1
        self.log.emit(summary + " — macro keeps running.", "Error")
        self.log.emit("".join(details).rstrip(), "Error")

    def _cooldown(self, key: str, seconds: float) -> bool:
        """True (and starts the timer) if `key` wasn't done in the last `seconds`."""
        now = time.monotonic()
        if now - self._last_done.get(key, -1e9) < seconds:
            return False
        self._last_done[key] = now
        return True

    def _sleep(self, seconds: float) -> bool:
        """Sleep, but wake early if stopped. Returns False if stopped."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.isInterruptionRequested():
                return False
            self.msleep(30)
        return True

    def _fresh(self, screen: str) -> Detection | None:
        """Latest detection, only if it agrees with the steady screen."""
        det = self.detector.latest
        if det is not None and det.screen == screen:
            return det
        return None

    @staticmethod
    def _line(det: Detection, keyword: str, exact: bool = False, threshold: float = 0.8) -> OcrLine | None:
        """Find `keyword` on screen. Returns just the matching words, not the
        whole line — e.g. "Find Match" out of "Play Here Find Match"."""
        key = _norm(keyword)
        if exact:
            matches = [l for l in det.lines if _norm(l.text) == key]
        else:
            # Exact text first, so "find match" never lands on "Join Matchmaking?".
            matches = [l for l in det.lines if key in _norm(l.text)] or \
                      [l for l in det.lines if fuzzy_in(keyword, l.text, threshold)]
        return narrow_to_words(matches[0], keyword) if matches else None

    def _click_line(self, hwnd: int, line: OcrLine, what: str) -> None:
        self.log.emit(f"Clicking {what}", "Info")
        inp.click(hwnd, line.x + line.w / 2, line.y + line.h / 2)

    # --- main loop -----------------------------------------------------
    def _new_match(self) -> None:
        self.match = MatchState(pending=list(self.settings.placement_order))

    def _wait_fresh(self, reads: int = 2, timeout: float = 2.0) -> Detection | None:
        """Wait for `reads` new detections (so they show the screen *after* an action)."""
        target = self.detector.latest_count + reads
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.isInterruptionRequested():
                return None
            if self.detector.latest_count >= target:
                return self.detector.latest
            self.msleep(30)
        return self.detector.latest

    def _wait_after(self, moment: float, timeout: float = 2.0) -> Detection | None:
        """Wait for a detection of a frame captured after `moment` (+ time for the game to react)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.isInterruptionRequested():
                return None
            if self.detector.latest_time > moment + 0.12:
                return self.detector.latest
            self.msleep(20)
        return self.detector.latest

    def run(self) -> None:
        self.log.emit("Run loop started. Press F3 to stop.", "Info")
        if self.numbers is None:
            self.numbers = make_number_reader(lambda: self.detector.tracker.screen,
                                              log=self.log.emit)
        if self._ocr is None:
            self._ocr = OcrReader()
        self._new_match()
        self._maps = load_maps()
        self._map = None
        self._map_walked = False    # the thread is reused on every F1: start fresh
        if self._maps:
            self.log.emit(f"Placement zones saved for: {', '.join(m.name for m in self._maps)}.", "Info")
        wave = self.detector.tracker.wave
        if (self.settings.skip_placing_mid_match and wave and wave >= 2
                and self.detector.tracker.screen in ("in_match", "unit_manager", "card_pick")):
            self.match.pending = []
            self.log.emit(f"Started mid-match (wave {wave}): assuming units are already "
                          "placed, so only upgrading and picking cards.", "Info")
        try:
            while not self.isInterruptionRequested():
                try:
                    latest = self.detector.latest
                    if latest is not None and latest.screen == "unit_manager":
                        self._manager_seen_at = time.monotonic()
                    if self.detector.tracker.screen in ("captcha", "match_found"):
                        self._matchmaking_at = time.monotonic()
                    elif self.detector.tracker.screen in ("in_match", "vote_start"):
                        self._matchmaking_at = -1e9
                    hwnd = self.capture.hwnd
                    if not hwnd:
                        self._say("Waiting for Roblox…")
                        self._sleep(1)
                        continue
                    self._watch_map(latest)
                    if self._dismiss_drop(hwnd, latest):
                        self._sleep(0.2)
                        continue
                    if self._close_leaderboard(hwnd, latest):
                        self._sleep(0.2)
                        continue
                    if self._close_chat(hwnd, latest):
                        self._sleep(0.2)
                        continue
                    screen = self.detector.tracker.screen
                    # A card pick is time-limited: act on the first read of it
                    # instead of waiting for it to be confirmed.
                    if latest is not None and latest.screen == "card_pick":
                        screen = "card_pick"
                    if screen != self._screen:
                        if screen in NEW_MATCH_SCREENS:
                            self._new_match()
                        if self._screen == "card_pick":
                            self.match.card_voted = self.match.card_clicked = False
                        if screen == "card_pick":
                            self.match.card_seen_at = time.monotonic()
                        self._screen = screen
                    handler = getattr(self, f"_on_{screen}", None)
                    if handler:
                        handler(hwnd)
                except Exception as exc:
                    # Keep the macro running: log the error and try again next loop.
                    inp.release_all()
                    self._report_error(exc)
                    self._sleep(1)
                    continue
                self._sleep(0.2)
        finally:
            inp.release_all()
            self.status.emit("Stopped")

    def _dismiss_drop(self, hwnd: int, det: Detection | None) -> bool:
        """Click away item drops ("Click anywhere to continue"). One to three
        can come in a row, so keep clicking while the prompt is up. Returns
        True if it clicked."""
        if det is None or det.drop is None:
            self._drop_clicks = 0
            self._drop_seen = None
            return False
        if det.drop != getattr(self, "_drop_seen", None) and any(det.drop):
            self._drop_seen = det.drop
            name, rarity = det.drop
            self.log.emit(f"Drop: {name or 'item'}{f' ({rarity})' if rarity else ''}", "Info")
            self.drop_found.emit(name, rarity)
        if not self._cooldown("drop", 0.8):
            return False
        self._drop_clicks = getattr(self, "_drop_clicks", 0) + 1
        if self._drop_clicks > 10:
            if self._drop_clicks == 11:
                self.log.emit("The drop popup won't go away — leaving it.", "Warn")
            return False
        # Top middle (the HUD bar): if the popup is already gone, a click
        # there doesn't select a unit on the map.
        width, height = self._frame_size()
        inp.click(hwnd, width * 0.5, height * 0.12)
        return True

    def _close_leaderboard(self, hwnd: int, det: Detection | None) -> bool:
        """Close the damage leaderboard if it opened (it covers the screen).
        Returns True if it clicked."""
        if det is None or det.leaderboard_close is None:
            self._leaderboard_tries = 0
            return False
        if not self._cooldown("leaderboard", 2.0):
            return False
        self._leaderboard_tries = getattr(self, "_leaderboard_tries", 0) + 1
        if self._leaderboard_tries > 4:
            if self._leaderboard_tries == 5:
                self.log.emit("The leaderboard won't close — leaving it open.", "Warn")
            return False
        self.log.emit("Closing the leaderboard.", "Info")
        inp.click(hwnd, *det.leaderboard_close)
        self._park_mouse(hwnd)
        return True

    def _close_chat(self, hwnd: int, det: Detection | None) -> bool:
        """Close the chat window if it's open: it covers the left card (and
        its text, e.g. the Star Golem card). Returns True if it clicked."""
        if det is None or det.chat_toggle is None:
            self._chat_tries = 0
            return False
        if not self._cooldown("chat", 3.0):
            return False
        self._chat_tries = getattr(self, "_chat_tries", 0) + 1
        if self._chat_tries > 3:
            if self._chat_tries == 4:
                self.log.emit("The chat won't close — leaving it open.", "Warn")
            return False
        self.log.emit("Closing the chat.", "Info")
        inp.click(hwnd, *det.chat_toggle)
        self._park_mouse(hwnd)
        return True

    def _card_pick_up(self) -> bool:
        """True as soon as a card pick is on screen (so placing/upgrading stop)."""
        det = self.detector.latest
        return det is not None and det.screen == "card_pick"

    def _watch_map(self, det: Detection | None) -> None:
        """Recognise the map from the loading screen or the match title, and
        load the player's placement zones for it."""
        screen = self.detector.tracker.screen
        if screen in ("lobby", "match_found", "loading"):
            self._map_walked = False    # back at the spawn: walk again next match
        if screen == "lobby":
            self._map, self._map_warned = None, False
            return
        if det is None or self._map is not None or screen not in ("loading", "vote_start", "in_match"):
            return
        found = find_map(self._maps, det.lines)
        if found is not None:
            self._map = found
            self.log.emit(f"Map: {found.name} — placement zones loaded.", "Info")
        elif screen == "in_match" and det.map_name and not getattr(self, "_map_warned", False):
            self._map_warned = True
            self.log.emit(f"Map '{det.map_name}': no placement zones saved yet "
                          "(using automatic spots).", "Info")

    # --- one handler per screen ----------------------------------------
    def _on_lobby(self, hwnd: int) -> None:
        # After the verification / "Match found", the lobby shows again for a
        # few seconds before the teleport: don't click Play then.
        if time.monotonic() - self._matchmaking_at < 30:
            self._say("Matchmaking — waiting for the teleport")
            return
        det = self._fresh("lobby")
        if det is None or not self._cooldown("play", 12):
            return
        clicked_at = time.monotonic()
        if not self.click_play(hwnd, det):
            if not self.isInterruptionRequested():
                self._last_done["play"] = time.monotonic() - 12 + 1.5   # retry in 1.5 s
            return
        if not self._sleep(max(0.0, self.settings.teleport_wait - (time.monotonic() - clicked_at))):
            return
        self._walk_to_ring(hwnd)

    def click_play(self, hwnd: int, det: Detection | None = None) -> bool:
        """Find the lobby's Play button, click it, and check that it worked.

        `det` is a lobby detection to find the button in (the newest one if
        not given). Returns True once the lobby menu has gone (the game is
        teleporting you), False if the button wasn't found or the click missed.
        """
        det = det or self.detector.latest
        if det is None:
            return False
        play = self._line(det, "play", exact=True)
        if play is None:
            # Fall back to the menu layout: Play sits right of Items, like Store sits right of Units.
            items = self._line(det, "items", exact=True)
            units = self._line(det, "units", exact=True)
            store = self._line(det, "store", exact=True)
            if not (items and units and store):
                self._say("In lobby — can't find the Play button", level="Warn")
                return False
            play = OcrLine("Play", int(items.x + store.center_x - units.center_x), items.y, items.w, items.h)
        self._say("In lobby → clicking Play")
        self._click_line(hwnd, play, "Play")
        # Only count it once the lobby menu is gone: a click can miss (often the
        # first one just brings Roblox to the front).
        if self._left_lobby(time.monotonic(), timeout=self.settings.teleport_wait + 3):
            return True
        if not self.isInterruptionRequested():
            self.log.emit("Play click didn't register — clicking again.", "Warn")
        return False

    def _left_lobby(self, after: float, timeout: float) -> bool:
        """True once two reads of frames taken after `after` aren't the lobby
        (two, so one bad text read doesn't count as leaving)."""
        end = time.monotonic() + timeout
        seen, misses = -1, 0
        while time.monotonic() < end:
            if self.isInterruptionRequested():
                return False
            count, det = self.detector.latest_count, self.detector.latest
            if count != seen and det is not None and self.detector.latest_time > after + 0.12:
                seen = count
                misses = misses + 1 if det.screen != "lobby" else 0
                if misses >= 2:
                    return True
            self.msleep(30)
        return False

    def _walk_to_ring(self, hwnd: int) -> None:
        self._say("Walking to matchmaking")
        start_count = self.detector.latest_count
        inp.focus(hwnd)
        sprint = self.settings.walk_sprint
        if sprint:
            inp.key_down("shift")       # run instead of walk
        inp.key_down(self.settings.walk_key)
        try:
            end = time.monotonic() + self.settings.walk_timeout
            while time.monotonic() < end:
                if self.isInterruptionRequested():
                    return
                det = self.detector.latest
                if (self.detector.latest_count > start_count and det is not None
                        and det.screen in ("join_matchmaking", "captcha")):
                    self.log.emit("Reached the matchmaking ring", "Info")
                    return
                self.msleep(30)
            self.log.emit("Didn't reach the ring in time — will try again", "Warn")
        finally:
            inp.key_up(self.settings.walk_key)
            if sprint:
                inp.key_up("shift")


    def _on_join_matchmaking(self, hwnd: int) -> None:
        det = self._fresh("join_matchmaking")
        if det is None or not self._cooldown("find_match", 4):
            return

        button = self._line(det, "find match")
        if button is None:
            return

        self._say("Joining matchmaking")
        self._click_line(hwnd, button, "Find Match")

        time.sleep(1)

        screenshot = pyautogui.screenshot(
            region=(470, 335, 600, 300)
        )

        number = read_number(image=screenshot)

        if not number:
            self._say("Failed to read number")
            return

        self._say(f"Read number: {number}")

        type_text(
            number,
            click_at=(770, 470)
        )

        time.sleep(0.5)

        det = self._fresh("captcha")
        if det is None:
            self._say("Captcha not found")
            return

        submit = self._line(det, "submit", exact=True)

        if submit is None:
            self._say("Submit button not found")
            return

        self._say("Verification typed → clicking Submit")
        self._click_line(hwnd, submit, "Submit")

    def _on_captcha(self, hwnd: int) -> None:
        """The verification is the player's to type. Once they've typed
        something and stopped for a moment, press Submit for them."""
        det = self._fresh("captcha")
        if det is None:
            return
        submit = self._line(det, "submit", exact=True)
        typed = self._typed_answer(det, submit)
        now = time.monotonic()
        if typed != getattr(self, "_captcha_typed", None):
            self._captcha_typed, self._captcha_typed_at = typed, now
        if not typed:
            self._say("Verification — your turn: type the number")
            return
        if submit is None or typed == getattr(self, "_captcha_submitted", None):
            return
        if now - self._captcha_typed_at < CAPTCHA_SUBMIT_AFTER:
            self._say("Verification — waiting for you to finish typing", log=False)
            return
        self._say("Verification typed → clicking Submit")
        self._click_line(hwnd, submit, "Submit")
        self._captcha_submitted = typed     # retype (e.g. a typo) and it submits again

    @staticmethod
    def _typed_answer(det: Detection, submit: OcrLine | None) -> str:
        """What's in the answer box: the lower of the digit lines above the
        Submit button (the upper, bigger one is the number to copy)."""
        if submit is None:
            return ""
        digit_lines = [l for l in det.lines
                       if l.y + l.h <= submit.y and submit.y - l.y < 6 * submit.h
                       and any(c.isdigit() for c in l.text)
                       and sum(c.isdigit() for c in l.text) >= len(l.text.replace(" ", "")) / 2]
        if len(digit_lines) < 2:
            return ""       # only the number to copy is showing: nothing typed yet
        box = max(digit_lines, key=lambda l: l.y)
        return "".join(c for c in box.text if c.isdigit())

    def _on_match_found(self, hwnd: int) -> None:
        self._say("Match found — teleporting")

    def _on_loading(self, hwnd: int) -> None:
        self._say("Loading…")

    def _on_vote_start(self, hwnd: int) -> None:
        if not self.settings.auto_vote_start:
            self._say("Vote start — waiting for the countdown")
            return
        det = self._fresh("vote_start")
        if det is None:
            return
        yes = self._line(det, "yes", exact=True)
        if yes is not None and not self.match.voted_start and self._cooldown("vote_yes", 6):
            self._say("Vote start — voting Yes")
            self._click_line(hwnd, yes, "Yes")
            self.match.voted_start = True
        else:
            self._say("Vote start — waiting for the countdown")

    # --- in the match: place → upgrade → watch -------------------------
    def _on_in_match(self, hwnd: int) -> None:
        m, cfg = self.match, self.settings
        if cfg.place_units and m.pending and not m.zoomed:
            m.zoomed = True
            if cfg.zoom_out_seconds > 0:
                self._say("Zooming out (O)")
                inp.press(hwnd, "o", hold=cfg.zoom_out_seconds)
                self._sleep(0.5)
            return
        # Not kept in MatchState: vote start resets that, and the walk must
        # happen only once per match.
        # If the map isn't recognised yet, keep checking until the first unit
        # goes down (walking after that would leave placed units behind).
        if cfg.place_units and m.pending and not self._map_walked and (self._map is not None or m.placed):
            self._map_walked = True
            if self._map is not None and self._map.walk:
                self._walk_map(hwnd, self._map.walk)
                return
        m.close_tries = 0
        # "Maxed" is only a guess from a few reads (grey buttons + "Upg" not
        # read look the same as Max), so check the manager again now and then.
        if m.upgrades_done and time.monotonic() - m.upgrades_done_at > UPGRADE_RECHECK:
            m.upgrades_done = False
        if cfg.place_units and m.pending:
            self._place_next(hwnd)
        elif cfg.upgrade_units and not m.upgrades_done:
            # F toggles the manager, so don't press it if the manager was on
            # screen a moment ago (detection can flicker while it's open).
            if time.monotonic() - self._manager_seen_at > 6 and self._cooldown("open_manager", 6):
                self._say("Opening the unit manager to upgrade")
                inp.press(hwnd, "f")
                self._last_done["card_peek"] = time.monotonic()   # first peek in 5 s
        else:
            wave = self.detector.tracker.wave
            det = self.detector.latest
            yen = f" — {det.yen}¥" if det is not None and det.yen is not None else ""
            self._say((f"In match — wave {wave}" if wave else "In match") + yen, log=False)

    def _walk_map(self, hwnd: int, walk: dict) -> None:
        """Walk to the spot the map's zones were drawn from: hold the key for
        `seconds`, then (still holding it) jump `jumps` times. `"jump": true`
        instead taps Space all the way."""
        key = str(walk.get("key", "d")).lower()
        seconds = float(walk.get("seconds", 4.0))
        jumps = int(walk.get("jumps", 0))
        spam = bool(walk.get("jump", False))
        extra = f", then jump {jumps}x" if jumps else (" + jumping" if spam else "")
        self._say(f"Walking to the {self._map.name} spot ({key.upper()} for {seconds:g}s{extra})")
        inp.focus(hwnd)
        inp.key_down(key)
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end and not self.isInterruptionRequested():
                if spam:
                    self._tap_space()
                    self.msleep(190)
                else:
                    self.msleep(50)
            for _ in range(jumps):
                if self.isInterruptionRequested():
                    break
                self._tap_space()
                self.msleep(500)    # land before the next jump
        finally:
            inp.key_up(key)
        self._sleep(0.6)    # let the camera settle before reading the screen

    def _tap_space(self) -> None:
        inp.key_down("space")
        self.msleep(60)
        inp.key_up("space")

    def _unit_label(self, key: str) -> str:
        name = self.settings.unit_names.get(key, "").strip()
        return f"key {key}" + (f" ({name})" if name else "")

    def _read_count(self, after: float, slot: int | None = None, attempts: int = 4, timeout: float = 1.2) -> tuple[int, int] | None:
        """The hotbar placed/total counter, from frames captured after `after`.

        Banners ("Wave Completed!") and money pop-ups float over the counter
        now and then, so several frames are tried.
        """
        end = time.monotonic() + timeout
        last_id = -1
        while time.monotonic() < end and attempts > 0 and not self.isInterruptionRequested():
            frame_id, frame, frame_time = self.capture.latest_frame_info()
            if frame is not None and frame_time > after and frame_id != last_id:
                last_id = frame_id
                attempts -= 1
                count = read_unit_count(frame, self._ocr, slot)
                if count is not None:
                    return count
            self.msleep(20)
        return None

    def _park_mouse(self, hwnd: int) -> None:
        """Move the mouse to the top of the map, so the Place/Rotate/Cancel
        menu (which follows the mouse) doesn't cover the hotbar counter."""
        width, height = self._frame_size()
        inp.move_to(hwnd, width * 0.5, height * 0.22)

    def _in_placement_mode(self, after: float, slot: int | None = None) -> tuple[bool, tuple[int, int] | None]:
        """(placing?, counter) after pressing a unit key. Placing shows either as
        the counter or as the Place / Rotate / Cancel menu."""
        count = self._read_count(after, slot)
        if count is not None:
            return True, count
        det = self._wait_after(after, timeout=1.0)
        return bool(det is not None and det.placing), None

    def _apply_count(self, key: str, placed: int, total: int, spot=None) -> None:
        """Bring the plan in line with the game's counter for `key`.

        The counter going up is the only thing that counts as a placement.
        A unit that's full (e.g. 2/2), or already partly placed by the player,
        only keeps the placements it still needs.
        """
        m = self.match
        planned = self.settings.placement_order.count(key)
        needed = max(0, min(planned, total) - placed)
        before = m.counts.get(key)
        m.counts[key] = placed
        if before is not None and placed > before:
            m.placed += placed - before
            if spot is not None:
                m.spots.append(spot)
            self.log.emit(f"Placed {self._unit_label(key)} ({placed}/{total})", "Info")
        have = m.pending.count(key)
        for _ in range(have - needed):
            m.pending.remove(key)
        if needed == 0 and have:
            self.log.emit(f"{self._unit_label(key)} is done ({placed}/{total}).", "Info")

    def _place_next(self, hwnd: int) -> None:
        m = self.match
        if not self._cooldown("place", 0.8):
            return
        key = m.pending[0]
        label = self._unit_label(key)
        self._say(f"Placing {label} — {len(m.pending)} left")

        inp.press(hwnd, key)
        self._park_mouse(hwnd)
        pressed_at = time.monotonic()
        placing, count = self._in_placement_mode(pressed_at + 0.1, int(key))
        det = self.detector.latest
        if not placing:
            if det is not None and det.no_money:
                self._say(f"Waiting for money for {label}", log=False)
                self._last_done["place"] = time.monotonic() + 1.5
            else:
                m.failures[key] = m.failures.get(key, 0) + 1
                if m.failures[key] >= 6:
                    self.log.emit(f"{label}: no placement counter after 6 tries — skipping it.", "Warn")
                    while key in m.pending:
                        m.pending.remove(key)
            inp.press(hwnd, "q")
            return
        m.failures.pop(key, None)
        if count is not None:
            self._apply_count(key, *count)
            if key not in m.pending:
                inp.press(hwnd, "q")
                return

        # In placement mode the game paints everywhere you can't place red, so
        # candidates come from a frame taken now. Order: beside units already
        # placed, then non-red ground (near the road first), then the general
        # rings. Spots that already failed this match are skipped.
        frame_w, frame_h = self._frame_size()
        _, frame = self.capture.latest_frame()
        # The player's zones for this map come first (next to placed units first).
        zone = []
        if self._map is not None and self.detector.latest is not None:
            all_zone = spread(self._map.spots(self.detector.latest.lines, frame_w, frame_h),
                              m.spots, 0.04 * frame_h)
            # Other players' units often already fill part of a zone (around
            # the spawn especially): the game paints those spots red, so skip
            # them without clicking.
            zone = drop_red_spots(frame, all_zone) if frame is not None else all_zone
            if all_zone and not zone and self._cooldown("zone_full_log", 30):
                self.log.emit(f"The {self._map.name} zones look full — trying other spots.", "Info")
            if not all_zone and self._cooldown("zone_fit_log", 30):
                self.log.emit(f"Couldn't line up the {self._map.name} zones with the screen "
                              "(map title not read) — using automatic spots.", "Warn")
        ground = placeable_spots(frame) if frame is not None else []
        near, general = spots_to_try(frame_w, frame_h, m.spots)
        if m.spot_cursor >= len(general):
            m.spot_cursor = 0
        order = zone + near + ground + general[m.spot_cursor:] + general[:m.spot_cursor]
        # A failed spot is often taken by someone else's unit: skip the area
        # around it too, not just the exact point.
        tolerance = 0.04 * frame_h
        order = [(x, y) for x, y in order
                 if all(math.hypot(x - fx, y - fy) > tolerance for fx, fy in m.failed_spots)]
        tries = order[:SPOTS_PER_TRY]
        m.spot_cursor += max(0, len(tries) - len(zone) - len(near) - len(ground))
        # If the counter didn't read when the key was pressed, there's nothing
        # to compare against and a placement (0/2 → 1/2) would go unnoticed.
        # MAACRO places from the start of the match, so unread means none yet.
        m.counts.setdefault(key, 0)
        for x, y in tries:
            if self.isInterruptionRequested() or key not in m.pending or self._card_pick_up():
                break
            inp.click(hwnd, x, y)
            self._park_mouse(hwnd)
            clicked_at = time.monotonic()
            count = self._read_count(clicked_at + 0.15, int(key))
            det = self.detector.latest
            if det is not None and det.screen not in ("in_match", "unknown"):
                break   # a card pick or the end screen came up
            if det is not None and det.no_money:
                self._say(f"Waiting for money for {label}", log=False)
                break
            if count is not None:
                placed_before = m.placed
                self._apply_count(key, *count, spot=(x, y))
                if m.placed > placed_before:
                    break   # placed one; start the next placement fresh
                m.failed_spots.append((x, y))
            elif det is not None and not det.placing:
                # Out of placement mode without a counter read: the unit most
                # likely went down. Stop clicking — more clicks would land on
                # placed units and open their panels. The next pass re-reads
                # the counter and picks up the placement.
                break
        # Leave placement mode; the next pass continues with whatever is left.
        inp.press(hwnd, "q")

    def _frame_size(self) -> tuple[int, int]:
        _, frame = self.capture.latest_frame()
        if frame is None:
            return 1920, 1080
        return frame.shape[1], frame.shape[0]

    def _peek_for_card_pick(self, hwnd: int) -> bool:
        """The unit manager hides a card pick (its text can't be read), so
        every few seconds close it and look. A card pick → leave it closed
        (the card comes first; upgrading resumes after). None → reopen.
        Returns True if it pressed F."""
        if not self._cooldown("card_peek", 5.0):
            return False
        inp.press(hwnd, "f")            # F toggles the manager: close
        self.msleep(350)                # let it slide away
        det = self._wait_after(time.monotonic(), timeout=1.5)
        if det is not None and det.screen == "card_pick":
            self.log.emit("Card pick behind the unit manager — picking first.", "Info")
            return True
        inp.press(hwnd, "f")            # nothing: open it again
        self._manager_seen_at = time.monotonic()
        self.msleep(300)
        return True

    def _on_unit_manager(self, hwnd: int) -> None:
        m, cfg = self.match, self.settings
        if cfg.upgrade_units and not m.upgrades_done and cfg.place_units and m.pending \
                and m.close_tries >= 3:
            # Started with the manager open (F3 → F1 mid-match) and it won't
            # close: the units are most likely placed already, so upgrade.
            self.log.emit("The unit manager won't close — assuming the units are "
                          "already placed and upgrading.", "Warn")
            m.pending.clear()
        if not cfg.upgrade_units or m.upgrades_done or (cfg.place_units and m.pending):
            if self._cooldown("close_manager", 3):
                m.close_tries += 1
                if m.close_tries == 1 and m.pending:
                    self.log.emit("Closing the unit manager to place units first.", "Info")
                inp.press(hwnd, "f")     # F toggles the unit manager
            return
        if self._peek_for_card_pick(hwnd):
            return
        det = self._fresh("unit_manager")
        _, frame = self.capture.latest_frame()
        if det is None or frame is None or not self._cooldown("upgrade", 1.0):
            return
        # Green buttons by colour, plus any "Upg" text that isn't on one of them
        # (gold last-upgrade buttons, or ones the colour search missed).
        green = find_green_buttons(frame)
        text_buttons = [l for l in det.lines if _norm(l.text).startswith("upg")
                        and not any(g.x - 10 <= l.center_x <= g.x + g.w + 10
                                    and g.y - 10 <= l.y + l.h / 2 <= g.y + g.h + 10 for g in green)]
        buttons = upgrade_order(det.lines, cfg.unit_names, cfg.upgrade_priority, green + text_buttons)
        upg_text = bool(text_buttons) or any(_norm(l.text).startswith("upg") for l in det.lines)
        if not buttons:
            # No green button and no "Upg" text (grey = can't afford yet) on
            # several reads in a row → probably everything is Max. Checked
            # again every UPGRADE_RECHECK seconds in case it was a misread.
            m.no_upgrade_reads = 0 if upg_text else m.no_upgrade_reads + 1
            if upg_text:
                self._say("Upgrading — waiting for money", log=False)
            if m.no_upgrade_reads >= 6:
                m.upgrades_done = True
                m.upgrades_done_at = time.monotonic()
                m.no_upgrade_reads = 0
                if not m.maxed_logged:
                    m.maxed_logged = True
                    self.log.emit(f"All units look maxed out — checking again every "
                                  f"{UPGRADE_RECHECK} s.", "Info")
                self._say("All units maxed — watching the match")
                inp.press(hwnd, "f")
            return
        m.no_upgrade_reads = 0
        self._say(f"Upgrading ({len(buttons)} not maxed yet)", log=False)
        for button in buttons:      # clicking one we can't afford does nothing
            if self.isInterruptionRequested() or self._card_pick_up():
                return
            inp.click(hwnd, button.center_x, button.y + button.h / 2)
            self._upgrade_clicks += 1
            self.msleep(120)
        if self._cooldown("upgrade_log", 20):
            self.log.emit(f"Upgrading: {len(buttons)} unit(s) not maxed yet "
                          f"({self._upgrade_clicks} upgrade clicks so far).", "Info")

    def _on_card_pick(self, hwnd: int) -> None:
        m = self.match
        if not self.settings.auto_card_pick:
            self._say("Card pick — left to you", log=False)
            return
        if m.card_voted:
            self._say("Card pick — voted, waiting", log=False)
            return
        if time.monotonic() - m.card_seen_at < 0.6:
            return      # the cards are still sliding in
        det = self.detector.latest
        if det is None or det.screen != "card_pick":
            return
        # Use the newest frame, but the layout comes from the text already read.
        _, frame = self.capture.latest_frame()
        if frame is None or not self._cooldown("card", 0.5):
            return

        # Step 1 (once per card pick): choose and click a card. Clicking it a
        # second time could un-select it, so it's never clicked again.
        if not m.card_clicked:
            cards = find_cards(frame, det.lines)
            title_read = any(fuzzy_in("choose a card", l.text) for l in det.lines)
            if not title_read and self._cooldown("card_layout_log", 30):
                # Keep a picture: the title being unreadable is what used to
                # stop card picks, and the cause isn't known yet.
                shot = Path(__file__).resolve().parents[1] / "logs" / f"card_pick_{time.strftime('%Y%m%d_%H%M%S')}.png"
                shot.parent.mkdir(exist_ok=True)
                cv2.imwrite(str(shot), frame)
                self.log.emit(f"Card pick: title not read — using the usual card spots "
                              f"(screenshot: {shot}).", "Warn")
            read_card_texts(cards, det.lines)      # uses text already read: no extra time
            if needs_votes(cards):                 # only when the best red cards tie
                read_votes(frame, cards, self.numbers)
            card, reason = choose_card(cards)
            colors = ", ".join(f"{c.color}{'' if c.votes is None else f' ({c.votes})'}" for c in cards)
            self.log.emit(f"Card pick: [{colors}] → card {card.index + 1}, {reason}", "Info")
            self._say(f"Card pick — card {card.index + 1} ({reason})", log=False)
            inp.click(hwnd, *card.center)
            m.card_clicked = True
            m.vote_target = vote_button(det.lines) or predicted_vote_button(det.lines, frame)
            self.msleep(300)                # let the Vote button appear

        # Step 2: press Vote. Its spot is known from the layout, so there's no
        # need to wait for it to be read; a read position wins if there is one.
        target = vote_button(det.lines) if m.card_clicked and det is not None else None
        target = target or m.vote_target
        if target is None:
            if self._cooldown("vote_button_log", 10):
                self.log.emit("Card pick: waiting for the Vote button.", "Info")
            return
        inp.click(hwnd, *target)
        m.card_voted = True
        self.log.emit("Card pick: voted.", "Info")

    def _on_end(self, hwnd: int) -> None:
        det = self._fresh("end")
        if det is None:
            return
        if not self.match.recorded and det.result:
            self._record_run(det)
        if not self._cooldown("next", 4):
            return
        button = self._line(det, "next", threshold=0.75)
        if button is None:
            return
        self._say("Match over → clicking Next")
        self._click_line(hwnd, button, "Next")

    def _record_run(self, det: Detection) -> None:
        """Note the run's result, waves, time and SummerPearls (once per run)."""
        _, frame = self.capture.latest_frame()
        if frame is None:
            return
        self.match.recorded = True
        map_name = self._map.name if self._map else (self.detector.tracker.map_name or "")
        try:
            record = read_run(frame, det.lines, self._ocr, det.result, map_name)
            save_run(record, frame)
        except Exception as exc:
            self.log.emit(f"Couldn't record the run: {exc}", "Warn")
            return
        pearls = f"+{record.pearls:,} SummerPearls" if record.pearls is not None else "pearls unread"
        self.log.emit(f"Run: {'Victory' if record.result == 'win' else 'Defeat'}"
                      f"{' on ' + record.map_name if record.map_name else ''} — "
                      f"{record.waves or '?'} waves, {record.duration or '?'} — {pearls}", "Info")
        self.run_recorded.emit(record)

    def _on_after_end(self, hwnd: int) -> None:
        det = self._fresh("after_end")
        if det is None or not self._cooldown("return", 5):
            return
        button = self._line(det, "return to lobby")
        if button is None:
            return
        self._say("Returning to lobby")
        self._click_line(hwnd, button, "Return to lobby")
