"""Starting a stage from the lobby by itself (Story, Infinite, Challenge).

The way in, from the player's screenshots (update 21):

  1. Lobby → the "Areas" button (right side, under Profile) → the "Areas (Click
     to Teleport)" window → "Play Area" (Story / Infinite / Legend) or
     "Challenges".
  2. After the teleport the doors are ahead: walk a little forward and to the
     right (W+D by default, editable) into one.
  3. Story / Infinite: a "Select World" list (it scrolls) → the map → a stage
     list "Infinite, Act 1 … Act 6" (it scrolls too) → difficulty (Normal /
     Hard; Infinite is Hard only) → "Select". Challenge: the door takes you in.
  4. A "Start" button, if one shows, is pressed; then MAACRO waits for the match.

Text is read on zoomed crops (the full picture reads "Areas" as "A-eas" or not
at all), matched loosely, and where it still can't be read the button's usual
place is used (the Areas button on the right edge; the area tiles from the
window's title). If a step fails, the picture MAACRO saw is saved
(logs/lobby/, the newest KEEP_SHOTS) so the step can be fixed, Cancel is
pressed when it shows, and the next try waits a while (FAIL_WAIT), so a
changed lobby can't make it loop fast.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .control import input as inp
from .vision.ocr import OcrLine
from .vision.screens import _norm, fuzzy_in

# Usual places (fractions of the window), for when the text can't be read.
AREAS_SPOT = (0.966, 0.856)
AREAS_REGION = (0.88, 0.62, 1.0, 0.96)             # x0, y0, x1, y1: the right-hand buttons
POPUP_REGION = (0.15, 0.05, 0.85, 0.95)            # the middle: popups and the world / stage windows
# The area tiles, from the "Areas (Click to Teleport)" title: (dx, dy) × the title's width.
TILE_FROM_TITLE = {"challenges": (-0.15, 0.93), "play area": (0.53, 0.56)}
WAIT_FOR_MATCH = 90      # s after the last step before the try counts as failed
FAIL_WAIT = {"story": 30, "infinite": 30, "challenge": 300}   # s before trying again after a failure
SCROLL_TRIES = 12        # scrolls of a list looking for the map / act
SHOTS_DIR = Path(__file__).resolve().parents[1] / "logs" / "lobby"
KEEP_SHOTS = 20
_DIGITS = str.maketrans({"l": "1", "i": "1", "o": "0", "s": "5"})


@dataclass(frozen=True)
class Step:
    """One step of a walk: hold keys for seconds (or until a text shows, with
    seconds as the limit), turn the camera, or wait."""
    keys: tuple[str, ...] = ()
    seconds: float = 0.0
    until: str = ""         # stop this step early once this text is on screen
    turn: int = 0           # camera turn: mouse counts with the right button held (+ right, - left)

    def text(self) -> str:
        if self.turn:
            return f"turn {self.turn}"
        if not self.keys:
            return f"wait {self.seconds:g}"
        keys = "+".join(self.keys)
        return f"{keys} until {self.until} {self.seconds:g}" if self.until else f"{keys} {self.seconds:g}"


UNTIL_LIMIT = 8.0       # s: an "until" step without its own limit


def parse_steps(text: str) -> list[Step]:
    """"w+d 2, turn 300, w until select world 6, wait 0.5" → Steps. Raises ValueError.

      w+d 2                    hold W and D together for 2 s
      w until select world 6   hold W until "Select World" shows (at most 6 s)
      turn 300 / turn -150     turn the camera right / left (mouse counts)
      wait 0.5                 do nothing for 0.5 s
    """
    steps = []
    for part in (text or "").split(","):
        part = " ".join(part.strip().lower().split())
        if not part:
            continue
        turn = re.fullmatch(r"turn\s+(-?\d+)", part)
        if turn:
            counts = int(turn.group(1))
            if not 0 < abs(counts) <= 5000:
                raise ValueError(f"'{part}': a turn is 1 to 5000 counts (negative = left)")
            steps.append(Step(turn=counts))
            continue
        wait = re.fullmatch(r"wait\s+(\d+(?:\.\d+)?)\s*s?", part)
        if wait:
            seconds = float(wait.group(1))
            if not 0 < seconds <= 20:
                raise ValueError(f"'{part}': between 0.1 and 20 seconds")
            steps.append(Step(seconds=seconds))
            continue
        until = re.fullmatch(r"([a-z+ ]+?)\s+until\s+(.+?)(?:\s+(\d+(?:\.\d+)?)\s*s?)?", part)
        if until:
            keys_text, target, limit = until.group(1), until.group(2).strip(), until.group(3)
            seconds = float(limit) if limit else UNTIL_LIMIT
        else:
            match = re.fullmatch(r"([a-z+ ]+?)\s+(\d+(?:\.\d+)?)\s*s?", part)
            if not match:
                raise ValueError(f"'{part}' should look like 'w+d 2' (keys, then seconds), "
                                 "'w until select world', 'turn 300' or 'wait 0.5'")
            keys_text, target, seconds = match.group(1), "", float(match.group(2))
        keys = tuple(k.strip() for k in keys_text.split("+") if k.strip())
        bad = [k for k in keys if k not in inp.SCAN_CODES]
        if not keys or bad:
            raise ValueError(f"unknown key(s) {', '.join(bad) or '?'} in '{part}'")
        if not 0 < seconds <= 20:
            raise ValueError(f"'{part}': between 0.1 and 20 seconds")
        steps.append(Step(keys, seconds, target))
    return steps


def parse_route(text: str) -> list[tuple[tuple[str, ...], float]]:
    """The key steps only: "w+d 2, w 1.5" → [(("w", "d"), 2.0), (("w",), 1.5)]. Raises ValueError."""
    return [(s.keys, s.seconds) for s in parse_steps(text) if s.keys]


def find_word(lines: list[OcrLine], word: str, exact: bool = False, threshold: float = 0.75):
    """The line showing `word`: the same text (letters and digits only) first,
    then containing it, then a close read (unless `exact`)."""
    key = _norm(word)
    same = [l for l in lines if _norm(l.text) == key]
    if same or exact:
        return same[0] if same else None
    within = [l for l in lines if key in _norm(l.text)]
    if within:
        return min(within, key=lambda l: len(l.text))
    close = [l for l in lines if fuzzy_in(word, l.text, threshold)]
    return min(close, key=lambda l: len(l.text)) if close else None


def find_act(lines: list[OcrLine], act: str):
    """The "Act 3" / "Infinite" button. Act numbers are matched exactly (a
    close read of "Act 3" would also match "Act 8"), with l/o/s read as 1/0/5."""
    if act == "infinite":
        return find_word(lines, "infinite", threshold=0.8)
    want = f"act{act}"
    for line in lines:
        text = _norm(line.text)
        fixed = text[:3] + text[3:].translate(_DIGITS)
        if fixed == want or (fixed.startswith(want) and not fixed[len(want):len(want) + 1].isdigit()
                             and len(fixed) <= len(want) + 6):
            return line
    return None


def tile_spot(title: OcrLine, tile: str) -> tuple[float, float]:
    dx, dy = TILE_FROM_TITLE[tile]
    return title.x + title.w / 2 + dx * title.w, title.y + title.h / 2 + dy * title.w


class LobbyStarter:
    """Mixin for Story / Infinite / Challenge (GeneralThread subclasses).
    Subclasses set AREA_TILE and LOBBY_KIND and, for Story / Infinite, the
    stage to pick (`_stage_choice`)."""
    AREA_TILE = "play area"
    LOBBY_KIND = "story"

    # --- reading the screen ------------------------------------------------
    def _read(self, region=POPUP_REGION, zoom: float = 2.0) -> list[OcrLine]:
        """Lines read on a zoomed crop of the newest picture, in window pixels."""
        _, frame = self.capture.latest_frame()
        if frame is None or self._ocr is None:
            return []
        height, width = frame.shape[:2]
        x0, y0, x1, y1 = (int(region[0] * width), int(region[1] * height),
                          int(region[2] * width), int(region[3] * height))
        crop = np.ascontiguousarray(frame[y0:y1, x0:x1, :3])
        if crop.size == 0:
            return []
        big = cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC)
        return [OcrLine(l.text, int(x0 + l.x / zoom), int(y0 + l.y / zoom), int(l.w / zoom), int(l.h / zoom))
                for l in self._ocr.read(big)]

    def _wait_for(self, finder, timeout: float, region=POPUP_REGION):
        """Read the screen until finder(lines) gives something (or time runs out)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end and not self.isInterruptionRequested():
            found = finder(self._read(region))
            if found is not None:
                return found
            self._sleep(0.3)
        return None

    def _click(self, hwnd: int, line: OcrLine, what: str) -> None:
        self.log.emit(f"Lobby: clicking {what}", "Info")
        inp.focus(hwnd)
        inp.click(hwnd, line.x + line.w / 2, line.y + line.h / 2)
        self._park_mouse(hwnd)

    def _frame_wh(self) -> tuple[int, int]:
        _, frame = self.capture.latest_frame()
        return (frame.shape[1], frame.shape[0]) if frame is not None else (1920, 991)

    # --- the lobby ---------------------------------------------------------
    def _lobby_ready(self) -> bool:
        """Starting from the lobby is on (and set up enough to try)."""
        return bool(getattr(self.settings, "lobby_start", False))

    def _on_lobby(self, hwnd: int) -> None:
        if not self._lobby_ready():
            super()._on_lobby(hwnd)
            return
        now = time.monotonic()
        started = getattr(self, "_lobby_started_at", None)
        if started is not None and now - started < WAIT_FOR_MATCH:
            self._say("Lobby: waiting for the match to start", log=False)
            return
        if started is not None:
            self._lobby_failed("the match didn't start")
            return
        if now < getattr(self, "_lobby_retry_at", 0.0):
            left = int(self._lobby_retry_at - now)
            self._say(f"Lobby: trying again in {left} s", log=False)
            return
        try:
            self._start_from_lobby(hwnd)
        finally:
            inp.release_all()

    def _new_match(self) -> None:
        super()._new_match()
        screen = self.detector.tracker.screen
        if screen in ("loading", "vote_start") and getattr(self, "_lobby_started_at", None) is not None:
            self._lobby_started_at = None
            self._lobby_fails = 0

    def _lobby_failed(self, why: str) -> None:
        self._lobby_started_at = None
        self._lobby_fails = getattr(self, "_lobby_fails", 0) + 1
        wait = FAIL_WAIT.get(self.LOBBY_KIND, 60)
        self._lobby_retry_at = time.monotonic() + wait
        level = "Error" if self._lobby_fails >= 3 else "Warn"
        extra = " — please check the game" if self._lobby_fails >= 3 else ""
        self.log.emit(f"Lobby: {why} (try {self._lobby_fails}); trying again in {wait} s{extra}.", level)
        shot = self._save_failure(why)
        if shot is not None:
            self.log.emit(f"Lobby: what MAACRO saw is saved as logs/lobby/{shot.name}", "Info")
        cancel = find_word(self._read(), "cancel", exact=True)
        if cancel is not None:
            self._click(self._hwnd_now(), cancel, "Cancel")

    def _save_failure(self, why: str) -> Path | None:
        """The current picture → logs/lobby/<time>_<why>.png (the newest KEEP_SHOTS kept)."""
        try:
            _, frame = self.capture.latest_frame()
            if frame is None:
                return None
            SHOTS_DIR.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^a-z0-9]+", "_", why.lower()).strip("_")[:40] or "failed"
            path = SHOTS_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{slug}.png"
            if not cv2.imwrite(str(path), frame[..., :3]):
                return None
            for old in sorted(SHOTS_DIR.glob("*.png"))[:-KEEP_SHOTS]:
                old.unlink(missing_ok=True)
            return path
        except (OSError, cv2.error):
            return None

    def _hwnd_now(self) -> int:
        return self.capture.hwnd or 0

    def _start_from_lobby(self, hwnd: int) -> None:
        width, height = self._frame_wh()
        # 1. Areas → the area tile.
        title = find_word(self._read(), "areas click to teleport", threshold=0.7)
        if title is None:
            button = find_word(self._read(AREAS_REGION), "areas", exact=False, threshold=0.6)
            if button is not None:
                self._click(hwnd, button, "Areas")
            else:
                self.log.emit("Lobby: clicking Areas (its usual place — the text wasn't read)", "Info")
                inp.focus(hwnd)
                inp.click(hwnd, AREAS_SPOT[0] * width, AREAS_SPOT[1] * height)
                self._park_mouse(hwnd)
            title = self._wait_for(lambda lines: find_word(lines, "areas click to teleport", threshold=0.7), 5)
        if title is None:
            self._lobby_failed("the Areas window didn't open")
            return
        tile = find_word(self._read(), self.AREA_TILE, threshold=0.6)
        if tile is not None and abs(tile.y - title.y) > title.h:      # not the title itself
            self._click(hwnd, tile, self.AREA_TILE.title())
        else:
            x, y = tile_spot(title, self.AREA_TILE)
            self.log.emit(f"Lobby: clicking {self.AREA_TILE.title()} (its usual place)", "Info")
            inp.focus(hwnd)
            inp.click(hwnd, x, y)
            self._park_mouse(hwnd)
        # 2. The teleport, then the walk into a door.
        if not self._sleep(max(2.5, getattr(self.settings, "teleport_wait", 2.5) + 1.0)):
            return
        if not self._walk_in(hwnd):
            return
        # 3. The stage (Story / Infinite).
        if not self._pick_stage(hwnd):
            return
        # 4. Start, if there's a button for it; then wait for the match.
        start = self._wait_for(lambda lines: find_word(lines, "start", exact=True), 6)
        if start is not None:
            self._click(hwnd, start, "Start")
        self._lobby_started_at = time.monotonic()
        self._say("Lobby: waiting for the match to start")

    def _walk_in(self, hwnd: int) -> bool:
        try:
            steps = parse_steps(getattr(self.settings, "lobby_walk", "w+d 2"))
        except ValueError as exc:
            self.log.emit(f"Lobby: the walk in Configs is wrong ({exc}).", "Error")
            self._lobby_failed("no walk")
            return False
        self.log.emit(f"Lobby: walking into the door ({', '.join(s.text() for s in steps)})", "Info")
        inp.focus(hwnd)
        sprint = getattr(self.settings, "walk_sprint", True)
        if sprint:
            inp.key_down("shift")
        try:
            for step in steps:
                result = self._walk_step(step)
                if result is not None:
                    return result
        finally:
            if sprint:
                inp.key_up("shift")
        return True

    def _walk_step(self, step: Step) -> bool | None:
        """Play one step, timed to the millisecond. True = in (the stage window
        is up), False = stopped, None = go on with the next step."""
        if step.turn:
            inp.turn_camera(step.turn)
            return None
        for key in step.keys:
            inp.key_down(key)
        try:
            end = time.perf_counter() + step.seconds
            while True:
                left = end - time.perf_counter()
                if left <= 0:
                    return None
                if self.isInterruptionRequested():
                    return False
                if self._inside_door():
                    self.log.emit("Lobby: in — the stage window is up.", "Info")
                    return True
                if step.until and self._text_on_screen(step.until):
                    return None
                # Short naps; the last one ends exactly on time.
                inp.precise_sleep(min(0.05, left))
        finally:
            for key in step.keys:
                inp.key_up(key)

    def _text_on_screen(self, text: str) -> bool:
        det = self.detector.latest
        return det is not None and any(fuzzy_in(text, l.text, 0.8) for l in det.lines)

    def _inside_door(self) -> bool:
        """The world window is up (read by the screen reader, no extra work)."""
        det = self.detector.latest
        return det is not None and any(fuzzy_in("select world", l.text, 0.8) for l in det.lines)

    def _pick_stage(self, hwnd: int) -> bool:
        return True          # Challenge: the door is the stage


class StagePicker(LobbyStarter):
    """Story / Infinite: Select World → map → Act N / Infinite → difficulty → Select."""

    def _stage_choice(self) -> tuple[str, str, str]:
        """(world, act "1"–"6" or "infinite", difficulty "normal" / "hard")."""
        raise NotImplementedError

    def _scroll_find(self, hwnd: int, finder, region, anchor_xy, what: str):
        """Find with finder(lines), scrolling down over anchor_xy between reads."""
        for attempt in range(SCROLL_TRIES + 1):
            found = finder(self._read(region))
            if found is not None:
                return found
            if attempt == SCROLL_TRIES or self.isInterruptionRequested():
                break
            inp.scroll(hwnd, anchor_xy[0], anchor_xy[1], 3)
            self._sleep(0.5)
        self.log.emit(f"Lobby: couldn't find {what} in the list.", "Warn")
        return None

    def _lobby_ready(self) -> bool:
        if not super()._lobby_ready():
            return False
        if not self._stage_choice()[0].strip():
            if self._cooldown("no_world_note", 600):
                self.log.emit("Lobby: 'Start from the lobby' is on but no map is set (Configs → this "
                              "mode → Map) — waiting for you to start the stage.", "Warn")
            return False
        return True

    def _pick_stage(self, hwnd: int) -> bool:
        world, act, difficulty = self._stage_choice()
        header = self._wait_for(lambda lines: find_word(lines, "select world", threshold=0.8), 8)
        if header is None:
            self._lobby_failed("the Select World window didn't show (walk into a door — adjust the walk?)")
            return False
        width, height = self._frame_wh()
        list_xy = (header.x + header.w / 2, header.y + 4 * header.h)
        entry = self._scroll_find(hwnd, lambda lines: find_word(lines, world, threshold=0.8), POPUP_REGION,
                                  list_xy, f"the map '{world}'")
        if entry is None:
            self._lobby_failed(f"'{world}' isn't in the Select World list (check the spelling)")
            return False
        self._click(hwnd, entry, world)
        # The stage window: "<World> (Unit Level…)", Infinite / Act 1–6 on the left.
        first = self._wait_for(lambda lines: find_act(lines, "1") or find_act(lines, "infinite"), 6)
        if first is None:
            self._lobby_failed("the act list didn't show")
            return False
        label = "Infinite" if act == "infinite" else f"Act {act}"
        button = self._scroll_find(hwnd, lambda lines: find_act(lines, act), POPUP_REGION,
                                   (first.x + first.w / 2, first.y + 2 * first.h), label)
        if button is None:
            self._lobby_failed(f"{label} isn't in the list (not unlocked yet?)")
            return False
        self._click(hwnd, button, label)
        self._sleep(0.6)
        if act != "infinite":
            level = self._wait_for(lambda lines: find_word(lines, difficulty, exact=True), 3)
            if level is not None:
                self._click(hwnd, level, difficulty.title())
                self._sleep(0.4)
            else:
                self.log.emit(f"Lobby: '{difficulty.title()}' not seen — keeping the difficulty shown.", "Warn")
        select = self._wait_for(lambda lines: find_word(lines, "select", exact=True), 4)
        if select is None:
            self._lobby_failed("no Select button")
            return False
        self._click(hwnd, select, "Select")
        self.log.emit(f"Lobby: {world} — {label}" + ("" if act == "infinite" else f" ({difficulty.title()})")
                      + " picked.", "Info")
        return True
