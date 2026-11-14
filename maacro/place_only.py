"""Place-only units: placed, never upgraded ("Upgrade" unticked on the
Configs page).

No new setting is stored: a unit that is in the placement order but not in
the upgrade priority is place-only. (The Configs page always put every
enabled unit in the upgrade priority, so configs saved before this keep
upgrading everything.) The unit needs its name filled in: an Upg button is
matched to a unit by the name next to it.

PlaceOnlyUnits is a mixin for MacroThread and its subclasses (after CardFirst,
before ScrollingUpgrades). macro.py's source isn't changed; its upgrade_order
lookup is wrapped here, and the wrapper only filters while a PlaceOnlyUnits
thread is upgrading (everything else, e.g. a plain MacroThread, gets the
original result).
"""
from __future__ import annotations

import threading
import time

from . import macro as _macro
from .control import input as inp
from .placement import button_unit

_local = threading.local()


def place_only_keys(cfg) -> set[str]:
    return set(cfg.placement_order) - set(cfg.upgrade_priority)


def _wrap(original):
    def upgrade_order(lines, unit_names, priority, buttons=None):
        ordered = original(lines, unit_names, priority, buttons)
        skip = getattr(_local, "skip", None)
        if not skip:
            return ordered
        kept = [b for b in ordered if button_unit(b, lines, unit_names) not in skip]
        _local.only_skipped = bool(ordered) and not kept
        return kept
    upgrade_order._place_only = True
    return upgrade_order


if not getattr(_macro.upgrade_order, "_place_only", False):
    _macro.upgrade_order = _wrap(_macro.upgrade_order)


class PlaceOnlyUnits:
    """Mixin: units with "Upgrade" unticked are never upgraded."""

    def _buttons_to_upgrade(self, lines, buttons):
        # Used by ScrollingUpgrades to tell a part of the list with work left.
        skip = place_only_keys(self.settings)
        return [b for b in buttons if button_unit(b, lines, self.settings.unit_names) not in skip]

    def _on_unit_manager(self, hwnd: int) -> None:
        skip = place_only_keys(self.settings)
        if not skip:
            super()._on_unit_manager(hwnd)
            return
        m = self.match
        before = m.no_upgrade_reads
        _local.skip, _local.only_skipped = skip, False
        try:
            super()._on_unit_manager(hwnd)
        finally:
            only_skipped = _local.only_skipped
            _local.skip, _local.only_skipped = None, False
        if not only_skipped or m.upgrades_done:
            return
        # Upgrade buttons are up, but only on place-only units: MacroThread
        # would wait for money forever. Count it as nothing to upgrade.
        m.no_upgrade_reads = before + 1
        if m.no_upgrade_reads >= 6:
            m.upgrades_done = True
            m.upgrades_done_at = time.monotonic()
            m.no_upgrade_reads = 0
            if not m.maxed_logged:
                m.maxed_logged = True
                self.log.emit(f"Upgrading done (the rest are place-only units) — checking again "
                              f"every {_macro.UPGRADE_RECHECK} s.", "Info")
            self._say("Upgrading done — watching the match")
            inp.press(hwnd, "f")
