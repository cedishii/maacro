"""Per-unit timing and upgrade limits, for every mode (Configs → unit cards):

    upgrade_caps       {"1": 2}   upgrade unit 1 only up to upgrade 2
    place_from_wave    {"4": 10}  don't place unit 4 before wave 10
    place_waves        {"5": [1, 2, 2]}  per placement: unit 5's 1st from wave 1,
                                         the 2nd and 3rd from wave 2
    upgrade_from_wave  {"3": 15}  don't upgrade unit 3 before wave 15

(Capy-style macros do this with a scripted list of "at wave N: place / upgrade
to level L" steps at fixed screen spots. MAACRO keeps finding the spots and
buttons on screen, and only adds the when / how far per unit.)

`with_unit_plan(ModeThread)` adds it to any mode's controller without changing
the controller (like party.with_party):

  * placing: units held back by their wave go to the back of the queue; when
    only held units are left, placing pauses (and upgrading goes on);
  * upgrading: _buttons_to_upgrade (PlaceOnlyUnits' hook, used by every mode)
    leaves out units before their wave and units at their cap (the cap is read
    from the bar under the unit's card, see upgrade_levels.py).

The wave is the highest one read this match; before any wave is read, a unit
with a wave set counts as "not yet".
"""
from __future__ import annotations

import functools
import time

from PySide6.QtCore import Signal

from .placement import button_unit
from .upgrade_levels import upgrade_level
from .vision.unit_names import read_slot_names, vote

NAME_READS = 3          # pictures voted on when reading names off the hotbar


def _wave_map(cfg, name: str) -> dict[str, int]:
    out = {}
    for key, value in (getattr(cfg, name, {}) or {}).items():
        try:
            n = int(value)
        except (TypeError, ValueError):
            continue
        if n > 0:
            out[str(key)] = n
    return out


@functools.lru_cache(maxsize=None)
def with_unit_plan(cls):
    if getattr(cls, "_unit_plan", False):
        return cls
    # Sky Portal has its own caps (with its rush wave); don't apply them twice.
    own_caps = hasattr(cls, "_capped_out")

    class UnitPlanThread(cls):
        _unit_plan = True
        # Names read off the hotbar for units that had none ({key: name}); only
        # when no map profile is in use (the Main page saves them).
        names_read = Signal(dict)

        def _new_match(self) -> None:
            super()._new_match()
            self._plan_wave = 0
            self._plan_logged: set[str] = set()
            self._names_checked = False

        # --- unit names from the hotbar -------------------------------------
        def _on_in_match(self, hwnd: int) -> None:
            if not getattr(self, "_names_checked", True):
                self._names_checked = True
                try:
                    self._read_missing_names()
                except Exception as exc:        # never let this stop the macro
                    self.log.emit(f"Couldn't read unit names from the hotbar: {exc}", "Warn")
            super()._on_in_match(hwnd)

        def _read_missing_names(self) -> None:
            cfg = self.settings
            names = dict(getattr(cfg, "unit_names", {}) or {})
            missing = [k for k in dict.fromkeys(cfg.placement_order) if not str(names.get(k, "")).strip()]
            if not missing or getattr(self, "_ocr", None) is None:
                return
            readings, last = [], None
            for _ in range(NAME_READS * 3):
                frame_id, frame = self.capture.latest_frame()
                if frame is not None and frame_id != last:
                    last = frame_id
                    readings.append(read_slot_names(frame, self._ocr))
                    if len(readings) >= NAME_READS:
                        break
                time.sleep(0.25)
            found = {k: n for k, n in vote(readings).items() if k in missing} if readings else {}
            if not found:
                self.log.emit(f"Unit(s) {', '.join(missing)} have no name and it couldn't be read off "
                              "the hotbar — fill it in on the Configs page.", "Warn")
                return
            names.update(found)
            cfg.unit_names = names
            self.log.emit("Unit names read off the hotbar: "
                          + ", ".join(f"{k} = {n}" for k, n in sorted(found.items())) + ".", "Info")
            still = [k for k in missing if k not in found]
            if still:
                self.log.emit(f"Unit(s) {', '.join(still)} still have no name — fill it in on the "
                              "Configs page.", "Warn")
            if getattr(self, "_profile_name", None) is None:
                self.names_read.emit(found)

        def _plan_current_wave(self) -> int:
            wave = getattr(getattr(self.detector, "tracker", None), "wave", None)
            if isinstance(wave, int) and wave > getattr(self, "_plan_wave", 0):
                self._plan_wave = wave
            return getattr(self, "_plan_wave", 0)

        def _plan_note(self, tag: str, text: str) -> None:
            logged = getattr(self, "_plan_logged", None)
            if logged is None:
                logged = self._plan_logged = set()
            if tag not in logged:
                logged.add(tag)
                self.log.emit(text, "Info")

        # --- placing -------------------------------------------------------
        def _next_waits(self) -> dict[str, int]:
            """{key: wave} the next placement of each pending unit waits for."""
            cfg, m = self.settings, self.match
            waits = _wave_map(cfg, "place_from_wave")
            per = getattr(cfg, "place_waves", {}) or {}
            for key, waves in per.items():
                key = str(key)
                if key not in m.pending or not isinstance(waves, (list, tuple)):
                    continue
                done = cfg.placement_order.count(key) - m.pending.count(key)    # placed so far
                try:
                    n = int(waves[min(done, len(waves) - 1)]) if waves else 0
                except (TypeError, ValueError):
                    continue
                if n > 0:
                    waits[key] = n
                else:
                    waits.pop(key, None)
            return waits

        def _place_paused(self) -> bool:
            if super()._place_paused():
                return True
            waits = self._next_waits()
            m = self.match
            if not waits or not m.pending:
                return False
            wave = self._plan_current_wave()
            held = {k for k, n in waits.items() if wave < n}
            if not held:
                return False
            ready = [k for k in m.pending if k not in held]
            later = [k for k in m.pending if k in held]
            for key in dict.fromkeys(later):
                self._plan_note(f"place_{key}_{waits[key]}", f"{self._unit_label(key)}: next one from wave "
                                                             f"{waits[key]} (now {wave or '—'}).")
            if not ready:
                return True             # only held units left: upgrade meanwhile
            m.pending[:] = ready + later
            return False

        # --- upgrading -----------------------------------------------------
        def _buttons_to_upgrade(self, lines, buttons):
            kept = super()._buttons_to_upgrade(lines, buttons)
            if not kept:
                return kept
            cfg = self.settings
            waits = _wave_map(cfg, "upgrade_from_wave")
            caps = {} if own_caps else _wave_map(cfg, "upgrade_caps")
            if not waits and not caps:
                return kept
            wave = self._plan_current_wave() if waits else 0
            frame = None
            if caps:
                _, frame = self.capture.latest_frame()
            names = cfg.unit_names
            out = []
            for button in kept:
                key = button_unit(button, lines, names)
                if key in waits and wave < waits[key]:
                    self._plan_note(f"upg_{key}", f"{self._unit_label(key)}: upgraded from wave "
                                                  f"{waits[key]} (now {wave or '—'}).")
                    continue
                if key in caps and frame is not None:
                    level = upgrade_level(frame, button)
                    if level is not None and level[0] >= caps[key]:
                        self._plan_note(f"cap_{key}", f"{self._unit_label(key)} is at upgrade "
                                                      f"{level[0]}/{level[1]} (limit {caps[key]}) — "
                                                      "not upgrading it further.")
                        continue
                out.append(button)
            return out

    UnitPlanThread.__name__ = f"UnitPlan{cls.__name__}"
    UnitPlanThread.__qualname__ = UnitPlanThread.__name__
    return UnitPlanThread
