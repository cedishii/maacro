"""Farm first: farm units are upgraded to Max before any other unit.

The farm units (e.g. Bulby and the C.E.O.s, which make money) are listed in
the mode's `farm_units` ("Farm unit" ticked on the Configs page). While any
of them can still be upgraded, only farm units' Upg buttons are clicked:
the money isn't spent on damage units until the farm is done. Then every
other unit is upgraded as usual (in upgrade-priority order, as often as
money allows).

The farm counts as done once the unit manager shows "Max" for every farm
unit placed, or once no farm unit has had an Upg button for FARM_CLEAR_READS
reads in a row (with a list that doesn't scroll, so none can be hidden
below). Done stays done for the rest of the match.

FarmFirst is a mixin for MacroThread subclasses that also have
PlaceOnlyUnits (it goes in front of it): it narrows _buttons_to_upgrade.
"""
from __future__ import annotations

from .placement import button_unit
from .vision.screens import _norm

FARM_CLEAR_READS = 3


class FarmFirst:
    _farm_done = False
    _farm_holding = False
    _farm_read = -1
    _no_farm_reads = 0

    def _new_match(self) -> None:
        super()._new_match()
        self._farm_done, self._farm_holding, self._farm_read, self._no_farm_reads = False, False, -1, 0

    def _farm_keys(self) -> set[str]:
        return set(getattr(self.settings, "farm_units", []) or []) & set(self.settings.placement_order)

    def _buttons_to_upgrade(self, lines, buttons):
        kept = super()._buttons_to_upgrade(lines, buttons)
        farm = self._farm_keys()
        self._farm_holding = False
        if not farm or self._farm_done:
            return kept
        names = self.settings.unit_names
        farm_buttons = [b for b in kept if button_unit(b, lines, names) in farm]
        self._note_farm_read(lines, farm, bool(farm_buttons))
        if self._farm_done:
            return kept
        if farm_buttons:
            return farm_buttons
        # No farm button this read: maybe a misread. Hold the rest back until
        # the farm is known to be done.
        self._farm_holding = bool(kept)
        return []

    def _note_farm_read(self, lines, farm: set[str], farm_button: bool) -> None:
        """Once per screen read: is the farm done?"""
        read = getattr(self.detector, "latest_count", 0)
        if read == self._farm_read:
            return
        self._farm_read = read
        names = self.settings.unit_names
        maxed = sum(1 for l in lines if _norm(l.text) == "max" and button_unit(l, lines, names) in farm)
        planned = sum(self.settings.placement_order.count(k) for k in farm)
        if maxed >= planned:
            self._finish_farm(f"every farm unit shows Max ({maxed}/{planned})")
            return
        self._no_farm_reads = 0 if farm_button else self._no_farm_reads + 1
        scroll = getattr(self, "_scroll", None)
        if self._no_farm_reads >= FARM_CLEAR_READS and not (scroll is not None and scroll.scrollable):
            self._finish_farm("no farm unit has an upgrade left")

    def _finish_farm(self, why: str) -> None:
        self._farm_done = True
        self._farm_holding = False
        self.log.emit(f"Farm units maxed ({why}) — upgrading the damage units now.", "Info")
