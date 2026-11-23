"""The game's own auto upgrade (update 21.5): T turns it on.

With it on, the Unit Overview shows "Auto Upgs Active" at the bottom and each
unit's Upg button reads "Auto [P1]". GameAutoUpgrade is a mixin (first in the
bases) for when the player ticks "Use the game's auto upgrade" on Configs:

- in the unit manager, "Auto Upgs Active" on screen = on: MAACRO closes the
  manager and leaves upgrading to the game for the rest of the match (no
  scrolling, no Upg clicks);
- not on screen: press T, look again (T toggles, so it's only pressed while
  the text isn't there), at most AUTO_TRIES times a match; then MAACRO
  upgrades by itself as before, and says so.

Placing is unchanged. Off (the default): nothing changes.
"""
from __future__ import annotations

import time

from .control import input as inp
from .vision.screens import _norm

AUTO_TRIES = 3          # T presses a match before giving up and upgrading by itself
T_EVERY = 3.0           # s between T presses (let the overview update)
ACTIVE_WORDS = ("autoupgsactive", "autoupgradesactive", "autoupgactive")


def auto_upgrade_on(lines) -> bool:
    return any(any(w in _norm(l.text) for w in ACTIVE_WORDS) for l in lines)


class GameAutoUpgrade:
    _auto_state = "off"         # off / active / gave_up
    _auto_tries = 0

    def _new_match(self) -> None:
        super()._new_match()
        self._auto_state, self._auto_tries = "off", 0

    def _on_unit_manager(self, hwnd: int) -> None:
        cfg, m = self.settings, self.match
        if not getattr(cfg, "game_auto_upgrade", False) or not cfg.upgrade_units or self._auto_state == "gave_up":
            super()._on_unit_manager(hwnd)
            return
        if cfg.place_units and m.pending and not self._place_paused():
            super()._on_unit_manager(hwnd)          # closes it to place units first
            return
        det = self.detector.latest
        if det is None or det.screen != "unit_manager":
            return
        if auto_upgrade_on(det.lines):
            if self._auto_state != "active":
                self.log.emit("The game's auto upgrade is on — MAACRO leaves upgrading to it.", "Info")
            self._auto_state = "active"
            m.upgrades_done = True
            m.upgrades_done_at = time.monotonic() + 1e9     # no "maxed?" rechecks: the game upgrades
            if self._cooldown("auto_upgrade_close", 3):
                self._say("Auto upgrade on — closing the unit manager")
                inp.press(hwnd, "f")
            return
        if self._auto_tries >= AUTO_TRIES:
            self._auto_state = "gave_up"
            self.log.emit("The game's auto upgrade didn't turn on (no 'Auto Upgs Active' after pressing T) "
                          "— MAACRO upgrades by itself this match.", "Warn")
            super()._on_unit_manager(hwnd)
            return
        if self._cooldown("auto_upgrade_t", T_EVERY):
            self._auto_tries += 1
            self.log.emit("Turning on the game's auto upgrade (T).", "Info")
            inp.press(hwnd, "t")
