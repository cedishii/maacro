"""The General ("Any Stage") controller: place units, upgrade them, wait —
and, if you choose, replay the stage or go on to the next one.

For anything that isn't Summer Event or Infinity Castle (story, legend
stages, raids, challenges, portals, someone else's lobby…). The player picks
the stage; MAACRO plays the match:

    match starts → zoom out → (walk, if the map's zones need it) → place
    → upgrade to Max → wait → … → match over → (Replay / Next Stage, if
    switched on) → wait for the next match.

It's a subclass of Summer's MacroThread, so placing, upgrading, closing
popups and drops are the same tested code; macro.py isn't changed. Lobby,
Play, matchmaking, captcha, Next, Return to lobby and Replay are never
touched unless "After the match" asks for them (then only Next on the
results screen and Replay / Next Stage after it — never Return to lobby).
Voting Yes and picking cards are off unless switched on.
"""
from __future__ import annotations

from ..control import input as inp
from ..macro import MacroThread, narrow_to_words
from ..card_first import CardFirst
from ..place_only import PlaceOnlyUnits
from ..upgrades import ScrollingUpgrades
from ..vision.screens import Detection, _norm, fuzzy_in
from .actions import ActionRunner, actions_from_config
from .config import GeneralConfig
from .maps import GeneralMap, maps_for_general

# Screens that are the player's to handle (no recovery clicks on them).
PLAYER_SCREENS = ("lobby", "join_matchmaking", "captcha", "match_found", "loading",
                  "end", "after_end")
GAME_SCREENS = ("vote_start", "in_match", "unit_manager", "card_pick")

# Buttons after a match, by the "After the match" setting (first found wins).
REPLAY_WORDS = ("replay", "retry", "play again")
NEXT_WORDS = ("next stage", "next level", "next act", "next room")
AFTER_MATCH = {"replay": REPLAY_WORDS, "next": NEXT_WORDS + REPLAY_WORDS}
AFTER_MATCH_EVERY = 20      # s between presses (a second press could cancel a vote)
SPOT_AFTER_TRIES = 3        # presses without the button read → its usual spot


class GeneralThread(CardFirst, PlaceOnlyUnits, ScrollingUpgrades, MacroThread):   # ScrollingUpgrades: more than 8 units
    ALLOW_LOBBY_PLAY = False
    ALLOW_RETURN_TO_LOBBY = False
    INTRO = ("Any Stage mode — places units, upgrades them and waits. Start a stage "
             "yourself; MAACRO never clicks Play or Return to lobby.")

    def __init__(self, capture, detector, settings: GeneralConfig | None = None, parent=None):
        super().__init__(capture, detector, settings or GeneralConfig(), parent)
        self._in_game = False
        self._general_maps = []
        self._rezoomed = False
        self._actions = ActionRunner([])
        self._after_tries = 0

    def run(self) -> None:
        self._in_game = False
        self._after_tries = 0
        self._general_maps = maps_for_general()
        self._actions = ActionRunner(actions_from_config(getattr(self.settings, "actions", [])))
        if self._actions.actions:
            self.log.emit(f"{len(self._actions.actions)} action(s) on: "
                          + "; ".join(a.describe() for a in self._actions.actions), "Info")
        self.log.emit(self.INTRO, "Info")
        after = self._after_match()
        if after != "none":
            self.log.emit("After each match: " + ("Replay." if after == "replay"
                          else "Next Stage (Replay when there's no next stage)."), "Info")
        super().run()

    def _after_match(self) -> str:
        value = getattr(self.settings, "after_match", "none")
        return value if value in AFTER_MATCH else "none"

    def _watch_map(self, det: Detection | None) -> None:
        # General's own zones (maps/general/), then Summer's for other maps.
        wanted = getattr(self, "_general_maps", []) if getattr(self.settings, "use_map_zones", True) else []
        if self._maps is not wanted:
            self._maps = wanted     # [] = automatic spots, no walking
        super()._watch_map(det)

    def _new_match(self) -> None:
        super()._new_match()
        self._rezoomed = False
        self._after_tries = 0

    def _on_in_match(self, hwnd: int) -> None:
        """Zoom out at the start of every match (MacroThread does that), and
        again once the first wave is up: the countdown ending can reset the
        camera, and the zones are drawn from the zoomed-out view."""
        seconds = getattr(self.settings, "zoom_out_seconds", 0)
        if (self.match.zoomed and not getattr(self, "_rezoomed", False) and seconds > 0
                and self.detector.tracker.wave is not None):
            self._rezoomed = True
            self._say("Wave started — zooming out again (O)")
            inp.press(hwnd, "o", hold=seconds)
            self._sleep(0.5)
            return
        super()._on_in_match(hwnd)

    def _place_next(self, hwnd: int) -> None:
        """On a General map, each unit uses its own zones (e.g. Phoenix on
        Shibuya's green patches); a unit with none uses automatic spots."""
        m = self.match
        if not isinstance(self._map, GeneralMap) or not m.pending:
            super()._place_next(hwnd)
            return
        whole, self._map = self._map, self._unit_zones(self._map, m.pending[0])
        try:
            super()._place_next(hwnd)
        finally:
            self._map = whole

    def _unit_zones(self, whole: GeneralMap, key: str):
        """The zones (or exact spots) to place unit `key` in; None = automatic."""
        return whole.for_unit(key)

    # --- the player's screens: just wait ---------------------------------
    def _wait(self, text: str) -> None:
        self._say(f"Waiting — {text}", log=False)

    def _on_lobby(self, hwnd: int) -> None:
        self._wait("in the lobby (start a match and MAACRO plays it)")

    def _on_join_matchmaking(self, hwnd: int) -> None:
        self._wait("matchmaking is up to you")

    def _on_captcha(self, hwnd: int) -> None:
        self._wait("verification is up to you")

    def _on_vote_start(self, hwnd: int) -> None:
        if self.settings.auto_vote_start:
            super()._on_vote_start(hwnd)
        else:
            self._wait("vote start (voting is off in General's settings)")

    def _on_card_pick(self, hwnd: int) -> None:
        if self.settings.auto_card_pick:
            super()._on_card_pick(hwnd)
        else:
            self._wait("card vote (picking is off in General's settings)")

    def _on_end(self, hwnd: int) -> None:
        """Count the win/loss (for the totals and Discord); press Next only if
        "After the match" is set to Replay / Next Stage."""
        if self._after_match() != "none":
            super()._on_end(hwnd)
            return
        det = self._fresh("end")
        if det is None or self._close_covering_manager(hwnd, det):
            return
        if not self.match.recorded and det.result:
            self._record_run(det)
        self._wait("match over")

    def _on_after_end(self, hwnd: int) -> None:
        det = self.detector.latest
        if det is None or det.screen != "after_end":
            return
        if self._close_covering_manager(hwnd, det):
            return
        after = self._after_match()
        if after == "none":
            self._wait("match over (Return to lobby / Replay is up to you)")
            return
        if not self._cooldown("after_match", AFTER_MATCH_EVERY):
            return
        line = self._after_button(det, AFTER_MATCH[after])
        if line is not None:
            self._after_tries += 1
            name = line.text.strip() or "Replay"
            self._say(f"Match over → pressing {name}")
            self._click_line(hwnd, line, name)
            return
        self._after_tries += 1
        spot = self._replay_spot(det)
        if spot is not None and self._after_tries > SPOT_AFTER_TRIES:
            self._say("Match over → pressing Replay (button text not read — using its usual spot)")
            inp.click(hwnd, *spot)
            return
        self._say("Match over — looking for the Replay / Next Stage button", log=False)

    @staticmethod
    def _after_button(det: Detection, words):
        """The first of `words` on screen: exact text first (in order), then a
        close read. Never "Waiting for Players" (reads a lot like "replay") or
        Return to lobby."""
        lines = [l for l in det.lines
                 if not any(w in _norm(l.text) for w in ("waiting", "player", "lobby"))]
        for word in words:
            for line in lines:
                if _norm(word) in _norm(line.text):
                    return narrow_to_words(line, word)
        for word in words:
            for line in lines:
                if fuzzy_in(word, line.text, 0.8):
                    return narrow_to_words(line, word)
        return None

    def _replay_spot(self, det: Detection):
        """Replay sits right of the middle of "Waiting for Players" (Return to
        lobby is left of it, see MacroThread._return_spot)."""
        waiting = self._line(det, "waiting for players")
        if waiting is None:
            return None
        return waiting.center_x + 0.29 * waiting.w, waiting.y - 0.125 * waiting.w

    # --- watchdog: only unstick things inside a match ----------------------
    def _watchdog(self, hwnd: int, screen: str) -> None:
        # Your own actions (the Actions page) come first, on any screen they're for.
        actions = getattr(self, "_actions", None)
        if actions is not None and actions.step(self, hwnd, screen):
            return
        if screen in GAME_SCREENS:
            self._in_game = True
        elif screen in PLAYER_SCREENS:
            self._in_game = False
        if screen in PLAYER_SCREENS or (screen == "unknown" and not self._in_game):
            return
        if screen == "vote_start" and not self.settings.auto_vote_start:
            return
        if screen == "card_pick" and not self.settings.auto_card_pick:
            return
        super()._watchdog(hwnd, screen)

    def _try_buttons(self, hwnd: int, det: Detection) -> str:
        line = self._line(det, "reconnect", exact=True)
        if line is not None:
            self._click_line(hwnd, line, line.text)
            return f"pressed '{line.text}'"
        return ""
