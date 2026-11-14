"""Actions: your own "on this screen, click this / press this" rules for
General mode (edited on the Actions page, saved in general_config.json).

General never clicks Next, Replay, Return to lobby or Play by itself; an
action lets you choose to, e.g. "Match over → click 'Replay' after 2 s".

Each action: the screen it waits for, how long that screen has to be up
first, then either a click on text read on screen or a key press. It runs
once each time the screen shows, or again every `repeat` seconds while it
stays up. Matchmaking, verification and loading screens can't be used.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass

from ..control import input as inp

# Screens an action can wait for (key → label on the Actions page).
ACTION_SCREENS = {
    "lobby": "Lobby",
    "vote_start": "Vote start",
    "in_match": "In a match",
    "card_pick": "Card vote",
    "end": "Match over (results)",
    "after_end": "After the match",
}
KINDS = {"click": "Click text", "key": "Press key"}
KEYS = tuple(inp.SCAN_CODES)


@dataclass
class Action:
    screen: str = "end"
    kind: str = "click"         # "click" text on screen, or "key"
    target: str = ""            # the text to click, or the key
    wait: float = 1.0           # s the screen must be up first
    repeat: float = 0.0         # s between repeats while the screen stays up (0 = once)
    enabled: bool = True

    def problem(self) -> str:
        """Why this action can't run ('' if it can)."""
        if self.screen not in ACTION_SCREENS:
            return "pick a screen"
        if self.kind not in KINDS:
            return "pick click or key"
        if not self.target.strip():
            return "the text to click is empty" if self.kind == "click" else "pick a key"
        if self.kind == "key" and self.target not in KEYS:
            return f"'{self.target}' isn't a key MAACRO can press"
        return ""

    def describe(self) -> str:
        what = f"click '{self.target}'" if self.kind == "click" else f"press {self.target.upper()}"
        again = f", again every {self.repeat:g} s" if self.repeat > 0 else ""
        return f"{ACTION_SCREENS.get(self.screen, self.screen)} → {what} after {self.wait:g} s{again}"


def actions_from_config(raw) -> list[Action]:
    actions = []
    for item in raw or []:
        try:
            action = Action(**{k: item[k] for k in asdict(Action()) if k in item})
            action.wait, action.repeat = float(action.wait), float(action.repeat)
        except (TypeError, ValueError):
            continue
        actions.append(action)
    return actions


class ActionRunner:
    """Runs the actions for the screen MacroThread is on (at most one per loop)."""

    def __init__(self, actions: list[Action]):
        self.actions = [a for a in actions if a.enabled and not a.problem()]
        self._done: dict[int, tuple[float, float]] = {}   # index → (screen_since, when)
        self._missing: set[tuple[int, float]] = set()

    def step(self, thread, hwnd: int, screen: str) -> bool:
        """True if an action was done this loop."""
        now = time.monotonic()
        since = thread._screen_since
        for index, action in enumerate(self.actions):
            if action.screen != screen or now - since < action.wait:
                continue
            done = self._done.get(index)
            if done is not None and done[0] == since and (action.repeat <= 0 or now - done[1] < action.repeat):
                continue
            if action.kind == "key":
                thread.log.emit(f"Action: {action.describe()}", "Info")
                inp.press(hwnd, action.target)
            else:
                det = thread._fresh(screen)
                line = thread._line(det, action.target) if det is not None else None
                if line is None:
                    if (index, since) not in self._missing:
                        self._missing.add((index, since))
                        thread.log.emit(f"Action: can't see '{action.target}' on screen yet — "
                                        "still looking.", "Info")
                    continue
                thread.log.emit(f"Action: {action.describe()}", "Info")
                inp.click(hwnd, line.x + line.w / 2, line.y + line.h / 2)
            self._done[index] = (since, now)
            return True
        return False
