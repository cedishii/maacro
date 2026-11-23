"""Misty Village mode (update 21.5): Night stages whenever they're open, else Day.

The way in, from the player's screenshots:

  1. Lobby → Play → "Where do you want to Play?" → Misty Village (since the
     Play window; never the Areas window) → teleport.
  2. Walk right (D, 5 s) until the "Misty Village Stages" window pops up; if
     it doesn't, a little down (S, 0.5 s).
  3. Two tiles: "Day Stages" (open day and night) and "Night Stages", whose
     timer tells whether it's open:
        "Dawn breaks in 34:41"  → Night is open (closes in 34:41)
        "Night falls in 57:04"  → Night is closed (opens in 57:04)
     Night is picked whenever it's open, unless "Day stages only" is on.
     Clicking a closed Night tile shows "Night stages only open at night!";
     Day is picked then.
  4. The stage window ("Misty Village (Unit Level: 100+)", the stage already
     chosen) → Select → "Join Matchmaking?" → Find Match and the captcha:
     those are the player's own matchmaking/captcha code (MacroThread's
     _on_join_matchmaking / _on_captcha, used unchanged).
  5. Night: 20 waves, Day: 15. After the match: Replay — but on a Day run,
     when Night has opened meanwhile, Return to lobby to play Night; on a
     Night run that dawn has ended (or is about to), Return to lobby for Day.

Everything else (placing, upgrading, cards, Reconnect…) is Any Stage's.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from .config import MacroConfig
from .general.config import GeneralConfig
from .find_match import FindMatchSpot, matchmaking_title
from .general.controller import LOBBY_WORDS, REPLAY_WORDS, GeneralThread
from .macro import MacroThread
from .close_x import close_button
from .control import input as inp
from .lobby_start import POPUP_REGION, WAIT_FOR_MATCH, LobbyStarter, find_word, parse_steps
from .vision.ocr import OcrLine
from .vision.screens import _norm, fuzzy_in

ROOT = Path(__file__).resolve().parents[1]
MISTY_CONFIG_PATH = ROOT / "misty_config.json"
WAVES = {"night": 20, "day": 15}
REPLAY_TRIES = 4             # after-match tries looking for Replay before Return to lobby will do
FIND_MATCH_EVERY = 6.0       # s between Find Match tries (a missed click isn't repeated every 4 s)
NIGHT_MIN_LEFT = 6 * 60      # s of night needed to start (or replay) a Night run
# Digits are often misread as letters ("51:oq" = 51:09): those letters count as digits.
SELECT_READS = ("select", "belect", "seiect", "selcct", "5elect", "sclect")
_D = "0-9oOqQlIisSgzZB"
TIMER_RE = re.compile(rf"([{_D}]{{1,2}})\s*[:.;,]\s*([{_D}]{{2}})")
_AS_DIGIT = str.maketrans("oOqQlIisSgzZB", "0099111559228")


@dataclass
class MistyConfig(GeneralConfig):
    auto_vote_start: bool = True
    lobby_start: bool = True             # the whole point of this mode: go there by itself
    lobby_walk: str = "d 5"              # from the teleport into the stages window
    lobby_walk_extra: str = "s 0.5"      # if the window didn't pop up after the walk
    walk_sprint: bool = False            # a plain walk (the 5 s was measured without Shift)
    teleport_wait: float = 4.0
    day_only: bool = False               # True: always Day ("spam Day"); False: Night whenever open

    @classmethod
    def load(cls, path: Path = MISTY_CONFIG_PATH) -> "MistyConfig":
        from .stage_modes import _load
        return _load(cls, path)

    def save(self, path: Path = MISTY_CONFIG_PATH) -> None:
        MacroConfig.save(self, path)


def read_night_timer(lines: list[OcrLine]) -> tuple[str, int] | None:
    """("open", seconds until dawn) / ("closed", seconds until night) from the
    Night Stages tile, or None if it can't be read. The timer may be on the
    same line as its words or on the next one."""
    for i, line in enumerate(lines):
        text = _norm(line.text)
        if "dawn" in text or "breaks" in text:
            state = "open"
        elif "fallsin" in text or ("night" in text and "falls" in text):
            state = "closed"
        else:
            continue
        candidates = [line] + [l for l in lines if l is not line and 0 <= l.y - line.y <= 3 * max(line.h, 10)
                               and abs(l.center_x - line.center_x) < 2 * max(line.w, 40)]
        for c in candidates:
            for match in TIMER_RE.finditer(c.text):
                minutes, seconds = (g.translate(_AS_DIGIT) for g in match.groups())
                if minutes.isdigit() and seconds.isdigit() and int(seconds) < 60:
                    return state, int(minutes) * 60 + int(seconds)
    return None


def stages_window(lines: list[OcrLine]) -> OcrLine | None:
    """The "Misty Village Stages" window (its title, or a tile when the title isn't read)."""
    return (find_word(lines, "misty village stages", threshold=0.7)
            or find_word(lines, "day stages", threshold=0.75)
            or find_word(lines, "night stages", threshold=0.75))


def shop_title(lines: list[OcrLine], height: int) -> OcrLine | None:
    """A shop popup's title: "Village Shop" or "Exclusive Shop" (seen live over
    the stage window, with Robux Purchase buttons). Nothing else with "shop" in
    it counts (a false close was seen at an end screen)."""
    for line in lines:
        text = _norm(line.text)
        if any(name in text for name in SHOP_NAMES) or (
                len(text) <= 16 and fuzzy_in("village shop", line.text, 0.85)):
            return line
    return None


SHOP_NAMES = ("villageshop", "exclusiveshop")
# The stage window ("Misty Village (Unit Level: 100+)", Clear Rewards, Friends
# Only, Select / Cancel). It has a "Level Info" button, which the screen reader
# takes for a match: seen live, it placed units on the lobby for 8 minutes.
STAGE_WINDOW_WORDS = ("unitlevel", "friendsonly", "clearrewards")


def stage_window_up(lines: list[OcrLine]) -> bool:
    return sum(any(w in _norm(l.text) for l in lines) for w in STAGE_WINDOW_WORDS) >= 2


def stage_of(map_name: str | None) -> str | None:
    """"Misty Village Night Stage" → "night"; "… Day Stage" → "day"."""
    text = _norm(map_name or "")
    if "night" in text:
        return "night"
    if "day" in text:
        return "day"
    return None


class MistyVillageThread(FindMatchSpot, LobbyStarter, GeneralThread):
    AREA_TILE, LOBBY_KIND = "misty village", "misty"
    PLAY_TILE = "misty village"
    AREAS_FALLBACK = False          # Play only: the Areas window is never opened
    INTRO = ("Misty Village — goes there from the lobby (Play → Misty Village → walk right), plays "
             "Night stages whenever they're open (20 waves), otherwise Day (15 waves), and Replays; "
             "back to the lobby to switch when night opens or ends.")
    # Also asked before the run starts (the main page's rejoin check): defaults here.
    _stage = None
    _night_opens_at = 0.0
    _night_closes_at = 0.0

    def run(self) -> None:
        self._stage = None             # "night" / "day": what was picked last
        self._night_opens_at = 0.0     # wall clock (time.time()); 0 = not known
        self._night_closes_at = 0.0
        if getattr(self.settings, "day_only", False):
            self.log.emit("Misty Village: Day stages only.", "Info")
        super().run()

    # --- which stage ---------------------------------------------------------
    def _night_open_now(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if self._night_closes_at and now < self._night_closes_at - NIGHT_MIN_LEFT:
            return True
        return bool(self._night_opens_at) and now >= self._night_opens_at and not (
            self._night_closes_at and self._night_opens_at < self._night_closes_at <= now)

    def _note_timer(self, timer: tuple[str, int] | None, now: float | None = None) -> None:
        if timer is None:
            return
        now = time.time() if now is None else now
        state, seconds = timer
        if state == "open":
            self._night_closes_at, self._night_opens_at = now + seconds, 0.0
        else:
            self._night_opens_at, self._night_closes_at = now + seconds, 0.0

    def _after_pressed(self, label: str, words) -> None:
        # Logged here, when it's really done (the after-match choice is also
        # asked now and then by the main page, e.g. for the rejoin watch).
        if "lobby" in _norm(label) and getattr(self, "_switch_note", ""):
            self.log.emit(f"Misty Village: {self._switch_note}", "Info")
        self._switch_note = ""
        super()._after_pressed(label, words)

    def _current_stage(self) -> str | None:
        return stage_of(getattr(self.detector.tracker, "map_name", None)) or self._stage

    def _after_words(self):
        words = self._misty_after()
        # Replay first: "Return to lobby" is only the fallback once Replay hasn't
        # been read for a few tries (live: the first read had only "Return to
        # lobby", and it went back to the lobby instead of replaying).
        if words == REPLAY_WORDS + LOBBY_WORDS and getattr(self, "_after_tries", 0) < REPLAY_TRIES:
            return REPLAY_WORDS
        return words

    def _misty_after(self):
        if getattr(self.settings, "day_only", False):
            return REPLAY_WORDS + LOBBY_WORDS
        stage = self._current_stage()
        now = time.time()
        if stage == "day" and self._night_open_now(now):
            self._switch_note = "Night is open now — back to the lobby to play Night."
            return LOBBY_WORDS
        if stage == "night" and self._night_closes_at and now >= self._night_closes_at - NIGHT_MIN_LEFT:
            self._switch_note = "Night is ending — back to the lobby to play Day."
            return LOBBY_WORDS
        return REPLAY_WORDS + LOBBY_WORDS

    # --- not a match: the stage window is still up ---------------------------
    def _on_in_match(self, hwnd: int) -> None:
        if self._still_in_lobby(hwnd):
            return
        super()._on_in_match(hwnd)

    def _on_unit_manager(self, hwnd: int) -> None:
        if self._still_in_lobby(hwnd):
            return
        super()._on_unit_manager(hwnd)

    def _still_in_lobby(self, hwnd: int) -> bool:
        """The stage window is on screen: no placing or upgrading (it would
        click the lobby). Waits for the match; after WAIT_FOR_MATCH s, Cancel
        and start over."""
        det = self.detector.latest
        if det is None or not stage_window_up(det.lines):
            return False
        now = time.monotonic()
        since = getattr(self, "_lobby_started_at", None) or getattr(self, "_stage_window_since", None)
        if since is None:
            self._stage_window_since = since = now
        self._say("Lobby: waiting for matchmaking (the stage window is up)", log=False)
        if now - since > WAIT_FOR_MATCH:
            self._stage_window_since = None
            self._lobby_failed("no match started from the stage window")    # presses Cancel
        return True

    # --- the village shop ----------------------------------------------------
    def _close_chat(self, hwnd: int, det) -> bool:
        """Every loop (before the screen's own step): close the village shop
        if it popped up; "Join Matchmaking?" read as another screen still goes
        to the matchmaking code; then the usual chat check."""
        if self._close_village_shop(hwnd, det):
            return True
        if (det is not None and det.screen != "join_matchmaking" and matchmaking_title(det.lines) is not None
                and not any("enterthistext" in _norm(l.text) for l in det.lines)):
            # Seen live: the window was up, the screen read as "In match" (the
            # stage window's "Level Info" under it), and Find Match was never pressed.
            self._on_join_matchmaking(hwnd)
            return True
        return super()._close_chat(hwnd, det)

    def _fresh(self, screen: str):
        """The player's matchmaking code checks the screen is "join_matchmaking";
        with the window's title on screen, it is (whatever the reader called it)."""
        det = self.detector.latest
        if screen == "join_matchmaking" and det is not None and matchmaking_title(det.lines) is not None:
            return det
        return super()._fresh(screen)

    def _close_village_shop(self, hwnd: int, det) -> bool:
        """The village shop pops up now and then: close it with its X. Only
        the X next to the shop's own title is clicked, and never with the unit
        manager open (its cards have red X buttons that sell the unit)."""
        if det is None or det.screen == "unit_manager":
            return False
        title = shop_title(det.lines, self._frame_wh()[1])
        if title is None or not self._cooldown("village_shop", 2.0):
            return False
        _, frame = self.capture.latest_frame()
        spot = close_button(frame, title)
        if spot is None:
            if self._cooldown("village_shop_note", 120):
                self.log.emit("The village shop is open but its X wasn't found — please close it "
                              "(a picture is saved in logs/lobby/).", "Warn")
                self._save_failure("village shop x not found")
            return False
        shot = self._save_failure("village shop closed")
        self.log.emit("The village shop popped up — closing it"
                      + (f" (picture: logs/lobby/{shot.name})." if shot is not None else "."), "Info")
        inp.focus(hwnd)
        inp.click(hwnd, *spot)
        self._park_mouse(hwnd)
        return True

    # --- the lobby -----------------------------------------------------------
    def _start_from_lobby(self, hwnd: int) -> None:
        # The stages window may already be up (walked into it before, or the
        # game spawned there): straight to the stage.
        if stages_window(self._read()) is not None:
            if self._pick_stage(hwnd):
                self._lobby_started_at = time.monotonic()
                self._say("Lobby: waiting for the match to start")
            return
        super()._start_from_lobby(hwnd)

    def _open_area_tile(self, hwnd: int, title: OcrLine) -> bool:
        """Misty Village is further down the Areas list: scroll until it shows."""
        anchor = (title.x + title.w / 2, title.y + title.h / 2 + 0.6 * title.w)
        tile = self._scroll_find(hwnd, lambda lines: next(
            (l for l in [find_word(lines, "misty village", threshold=0.7)]
             if l is not None and abs(l.y - title.y) > title.h), None), POPUP_REGION, anchor, "Misty Village")
        if tile is None:
            self._lobby_failed("Misty Village isn't in the Areas list")
            return False
        self._click(hwnd, tile, "Misty Village")
        return True

    def _inside_door(self) -> bool:
        det = self.detector.latest
        return det is not None and stages_window(det.lines) is not None

    def _pick_stage(self, hwnd: int) -> bool:
        header = self._wait_for(stages_window, 2)
        if header is None:
            extra = getattr(self.settings, "lobby_walk_extra", "s 0.5").strip()
            if extra:
                self.log.emit(f"Lobby: the stages window didn't pop up — walking a bit more ({extra}).", "Info")
                try:
                    for step in parse_steps(extra):
                        if self._walk_step(step) is not None:
                            break
                except ValueError:
                    pass
                header = self._wait_for(stages_window, 4)
        if header is None:
            self._lobby_failed("the Misty Village Stages window didn't pop up (adjust the walk?)")
            return False
        lines = self._read()
        timer = read_night_timer(lines)
        self._note_timer(timer)
        day_only = getattr(self.settings, "day_only", False)
        want_night = not day_only and (timer[0] == "open" if timer else self._night_open_now())
        if timer is not None:
            minutes, seconds = divmod(timer[1], 60)
            when = "closes" if timer[0] == "open" else "opens"
            self.log.emit(f"Misty Village: Night {when} in {minutes}:{seconds:02d}.", "Info")
        if want_night and timer is not None and timer[0] == "open" and timer[1] < NIGHT_MIN_LEFT:
            want_night = False          # not enough night left for a 20-wave run
            self.log.emit("Misty Village: too little night left for a run — playing Day.", "Info")
        if want_night and self._click_stage(hwnd, lines, "night"):
            self._sleep(0.8)
            if not any("onlyopen" in _norm(l.text) for l in self._read()):
                return True
            self.log.emit("Misty Village: Night is closed — playing Day.", "Info")
            self._night_closes_at = 0.0
        return self._click_stage(hwnd, self._read(), "day")

    def _click_stage(self, hwnd: int, lines: list[OcrLine], stage: str) -> bool:
        tile = find_word(lines, f"{stage} stages", threshold=0.75) or find_word(lines, stage, exact=True)
        if tile is None:
            self._lobby_failed(f"the {stage.title()} Stages tile wasn't read")
            return False
        self._click(hwnd, tile, f"{stage.title()} Stages")
        self._stage = stage
        self.log.emit(f"Misty Village: {stage.title()} stage picked ({WAVES[stage]} waves).", "Info")
        return self._press_select(hwnd)

    def _press_select(self, hwnd: int) -> bool:
        """The stage window: press Select (read as "belect" at times; the
        "Select World" panel on the right is not it). Then "Join Matchmaking?"
        is left to the player's matchmaking/captcha code."""
        window = self._wait_for(lambda lines: find_word(lines, "unit level", threshold=0.7)
                                or find_word(lines, "cancel", exact=True), 6)
        if window is None:
            self._lobby_failed("the stage window didn't open")
            return False
        self._sleep(0.4)
        lines = self._read()
        select = next((l for l in lines if _norm(l.text) in SELECT_READS), None)
        cancel = next((l for l in lines if _norm(l.text) == "cancel"), None)
        if select is None and cancel is not None:
            # Select sits right above Cancel (measured: 2.5 Cancel-heights up).
            select = OcrLine("Select", cancel.x, int(cancel.y - 2.5 * cancel.h), cancel.w, cancel.h)
        if select is None:
            self._lobby_failed("no Select button")
            return False
        self._click(hwnd, select, "Select")
        if self._wait_for(lambda lines: find_word(lines, "join matchmaking", threshold=0.7), 5) is None:
            self.log.emit("Lobby: 'Join Matchmaking?' not seen after Select — waiting for the match.", "Warn")
        return True

    # Matchmaking and the captcha: the player's own code in macro.py, unchanged
    # (Any Stage would leave them to the player).
    def _on_join_matchmaking(self, hwnd: int) -> None:
        # A try that didn't bring the captcha up isn't repeated every 4 s
        # (seen live: ~15 clicks on the title before FindMatchSpot).
        if not self._cooldown("misty_find_match", FIND_MATCH_EVERY):
            self._say("Matchmaking — waiting for the captcha", log=False)
            return
        MacroThread._on_join_matchmaking(self, hwnd)

    def _on_captcha(self, hwnd: int) -> None:
        MacroThread._on_captcha(self, hwnd)
