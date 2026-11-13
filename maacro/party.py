"""Operating behaviours: who makes the party-level decisions.

    Solo / Leader  - MAACRO plays the game AND decides where to go next
                     (lobby, Play, Find Match, Return to lobby, Next Room…).
    Party Member   - MAACRO only plays the game (place, upgrade, cards, vote,
                     close popups, Reconnect). The party leader moves around
                     the lobby, picks portals and presses Return to lobby /
                     Retry / Next Room; MAACRO waits for the next match.

The behaviour is separate from the game mode. `with_party(ModeThread)` adds
it to any mode's controller without changing that controller: the mixin sits
in front of it in the class order and, only while `party_member` is on,
replaces the steps that belong to the leader. With it off, every call goes
straight to the mode's own code, so Solo behaves exactly as before.

What a mode has to provide (the contract):
  * the usual MacroThread screen handlers (`_on_<screen>`), the watchdog
    (`_watchdog`, `_recover`, `_try_buttons`) and `_close_covering_manager`;
  * `PROGRESSION_ACTIONS`: the names of any extra methods of its own that make
    a party-level decision (Infinity Castle: `_continue`, which presses Next
    Room / Retry). In party mode those are replaced by "wait for the leader".
A new mode that does that gets Party Member support for free.
"""
from __future__ import annotations

import functools
import re
import time

SOLO, PARTY = "solo", "party"
BEHAVIORS = {SOLO: "Solo / Leader", PARTY: "Party Member"}

# Screens where the next step is the leader's to take.
LEADER_SCREENS = ("lobby", "join_matchmaking", "after_end")
# Screens that mean "we're in a match": a popup on an unknown screen is ours
# to clear only while in one.
GAME_SCREENS = ("vote_start", "in_match", "unit_manager", "card_pick", "end")
NEW_GAME_SCREENS = ("loading", "vote_start", "card_pick", "unit_manager")
OUT_OF_GAME = ("lobby", "join_matchmaking", "after_end", "match_found", "loading")
# Buttons the "try everything" recovery may still press as a party member:
# reconnecting and dismissing our own results screen. Not Find Match, Yes
# (could confirm a leave/teleport) or Return to lobby.
MEMBER_BUTTONS = ("reconnect", "next")
WAIT_NOTE_EVERY = 600   # s: a calm "still waiting" line in the log, no alarm

PARTY_RE = re.compile(r"@?\s*([A-Za-z0-9_]{3,20})\s*'?\s*s\s+party", re.IGNORECASE)


def party_leader(lines) -> str | None:
    """The leader's name from the party panel ("@Name's Party"), if it shows."""
    for line in lines:
        match = PARTY_RE.search(line.text)
        if match:
            return match.group(1)
    return None


def _leader_owned(name: str):
    """Wrap a mode's own progression action: in party mode, wait instead."""
    def wrap(method):
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            if not self.party_member:
                return method(self, *args, **kwargs)
            self._wait_for_leader("Waiting for the party leader to choose what's next")
            return True     # "handled": the caller doesn't fall back to clicking
        return wrapper
    return wrap


class PartyMemberBehavior:
    """Mixin for a MacroThread subclass. Off by default (Solo / Leader)."""

    party_member = False
    _in_game = False
    _leader_name: str | None = None
    _waiting_since: float | None = None
    _wait_noted = 0.0

    # --- what the shared recovery may do ---------------------------------
    @property
    def ALLOW_LOBBY_PLAY(self):              # noqa: N802 (same name as the class flag)
        return False if self.party_member else super().ALLOW_LOBBY_PLAY

    @property
    def ALLOW_RETURN_TO_LOBBY(self):         # noqa: N802
        return False if self.party_member else super().ALLOW_RETURN_TO_LOBBY

    def set_behavior(self, behavior: str) -> None:
        """Switch Solo / Party Member. Only while stopped (the UI makes sure)."""
        self.party_member = behavior == PARTY
        self._in_game = False
        self._leader_name = None
        self._waiting_since = None
        self._wait_noted = 0.0

    def behavior(self) -> str:
        return PARTY if self.party_member else SOLO

    # --- waiting -----------------------------------------------------------
    def _wait_for_leader(self, text: str) -> None:
        now = time.monotonic()
        if getattr(self, "_waiting_since", None) is None:
            self._waiting_since, self._wait_noted = now, now
            self.log.emit(f"Party member: {text}.", "Info")
        elif now - self._wait_noted >= WAIT_NOTE_EVERY:
            self._wait_noted = now
            self.log.emit(f"Party member: still waiting for the leader "
                          f"({int((now - self._waiting_since) // 60)} min).", "Info")
        self._say(f"Party member — {text}", log=False)

    def _note_screen(self, screen: str) -> None:
        if screen in GAME_SCREENS:
            self._in_game = True
        elif screen in OUT_OF_GAME:
            self._in_game = False
        if screen in NEW_GAME_SCREENS:
            self._waiting_since = None      # a new match: the next wait is a new one

    # --- the leader's screens ---------------------------------------------
    def _on_lobby(self, hwnd: int) -> None:
        if not self.party_member:
            return super()._on_lobby(hwnd)
        det = self.detector.latest
        leader = party_leader(det.lines) if det is not None else None
        if leader and leader != getattr(self, "_leader_name", None):
            self._leader_name = leader
            self.log.emit(f"Party member: in @{leader}'s party.", "Info")
        who = f"@{self._leader_name}" if getattr(self, "_leader_name", None) else "the party leader"
        self._wait_for_leader(f"in the lobby, waiting for {who} to start a game")

    def _on_join_matchmaking(self, hwnd: int) -> None:
        if not self.party_member:
            return super()._on_join_matchmaking(hwnd)
        self._wait_for_leader("at matchmaking, the leader starts the game")

    def _on_after_end(self, hwnd: int) -> None:
        if not self.party_member:
            return super()._on_after_end(hwnd)
        det = self.detector.latest
        # Closing our own unit manager is fine (it only hides the screen).
        if det is not None and det.screen == "after_end" and self._close_covering_manager(hwnd, det):
            return
        self._wait_for_leader("match over, waiting for the leader (Return to lobby / Retry / Next)")

    # --- watchdog: never "unstick" the leader's screens ---------------------
    def _watchdog(self, hwnd: int, screen: str) -> None:
        if not self.party_member:
            return super()._watchdog(hwnd, screen)
        self._note_screen(screen)
        if screen in LEADER_SCREENS:
            return
        if screen == "unknown" and not self._in_game:
            # Out of a match and the screen can't be read (party panel, portal
            # picker, teleport…): stay idle rather than click something.
            self._say("Party member — waiting (screen not recognised)", log=False)
            return
        super()._watchdog(hwnd, screen)

    def _try_buttons(self, hwnd: int, det) -> str:
        if not self.party_member:
            return super()._try_buttons(hwnd, det)
        for name in MEMBER_BUTTONS:
            line = self._line(det, name, exact=True)
            if line is not None:
                self._click_line(hwnd, line, line.text)
                return f"pressed '{line.text}'"
        return ""


@functools.lru_cache(maxsize=None)
def with_party(thread_class: type) -> type:
    """`thread_class` with the Party Member behaviour available (off until
    `set_behavior(PARTY)`). The mode's own class isn't changed."""
    body = {"__doc__": f"{thread_class.__name__} + Party Member behaviour.",
            "__module__": __name__}
    for name in getattr(thread_class, "PROGRESSION_ACTIONS", ()):
        body[name] = _leader_owned(name)(getattr(thread_class, name))
    return type(f"{thread_class.__name__}WithParty", (PartyMemberBehavior, thread_class), body)
