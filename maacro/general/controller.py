"""The General controller: place units, upgrade them, wait. Nothing else.

For anything that isn't Summer Event or Infinity Castle (story, raids,
portals, someone else's lobby…). The player picks the stage and handles
everything before and after the match; MAACRO only plays the match:

    match starts → zoom out → (walk, if the map's zones need it) → place
    → upgrade to Max → wait → … → match over → wait for the next match.

It's a subclass of Summer's MacroThread, so placing, upgrading, closing
popups and drops are the same tested code; macro.py isn't changed. Lobby,
Play, matchmaking, captcha, Next, Return to lobby and Replay are never
touched. Voting Yes and picking cards are off unless switched on.
"""
from __future__ import annotations

from ..control import input as inp
from ..macro import MacroThread
from ..card_first import CardFirst
from ..place_only import PlaceOnlyUnits
from ..upgrades import ScrollingUpgrades
from ..vision.screens import Detection
from .actions import ActionRunner, actions_from_config
from .config import GeneralConfig
from .maps import GeneralMap, maps_for_general

# Screens that are the player's to handle (no recovery clicks on them).
PLAYER_SCREENS = ("lobby", "join_matchmaking", "captcha", "match_found", "loading",
                  "end", "after_end")
GAME_SCREENS = ("vote_start", "in_match", "unit_manager", "card_pick")


class GeneralThread(CardFirst, PlaceOnlyUnits, ScrollingUpgrades, MacroThread):   # ScrollingUpgrades: more than 6 units
    ALLOW_LOBBY_PLAY = False
    ALLOW_RETURN_TO_LOBBY = False

    def __init__(self, capture, detector, settings: GeneralConfig | None = None, parent=None):
        super().__init__(capture, detector, settings or GeneralConfig(), parent)
        self._in_game = False
        self._general_maps = []
        self._rezoomed = False
        self._actions = ActionRunner([])

    def run(self) -> None:
        self._in_game = False
        self._general_maps = maps_for_general()
        self._actions = ActionRunner(actions_from_config(getattr(self.settings, "actions", [])))
        if self._actions.actions:
            self.log.emit(f"{len(self._actions.actions)} action(s) on: "
                          + "; ".join(a.describe() for a in self._actions.actions), "Info")
        self.log.emit("General mode — places units, upgrades them and waits. Start a match "
                      "yourself; MAACRO never clicks Play, Next, Replay or Return to lobby.", "Info")
        super().run()

    def _watch_map(self, det: Detection | None) -> None:
        # General's own zones (maps/general/), then Summer's for other maps.
        wanted = getattr(self, "_general_maps", []) if getattr(self.settings, "use_map_zones", True) else []
        if self._maps is not wanted:
            self._maps = wanted     # [] = automatic spots, no walking
        super()._watch_map(det)

    def _new_match(self) -> None:
        super()._new_match()
        self._rezoomed = False

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
        whole, self._map = self._map, self._map.for_unit(m.pending[0])
        try:
            super()._place_next(hwnd)
        finally:
            self._map = whole

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
        """Count the win/loss (for the totals and Discord), but leave Next to you."""
        det = self._fresh("end")
        if det is None or self._close_covering_manager(hwnd, det):
            return
        if not self.match.recorded and det.result:
            self._record_run(det)
        self._wait("match over")

    def _on_after_end(self, hwnd: int) -> None:
        det = self.detector.latest
        if det is not None and det.screen == "after_end" and self._close_covering_manager(hwnd, det):
            return
        self._wait("match over (Return to lobby / Replay is up to you)")

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
