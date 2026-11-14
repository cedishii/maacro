"""Sky Portal, as a party member: someone else hosts the portal.

    lobby / vote: wait (never votes — the party votes or the timer runs out)
    → zoom out → place EVERY unit on its spot (maps/sky_portal/) → max the
    farm units (Bulby, C.E.O.) → then upgrade the damage units as fast as
    money allows → wait for the next match.

Like General mode it never clicks Play, Next, Replay or Return to lobby.
Placing comes first, always: there is no "upgrade a while" break when a unit
can't be placed yet (not enough money), and no walking forward to find
room (the spots are drawn for the spawn camera).

Smart placing:
- when every spot of a unit is taken or has failed, rings of spots around
  them are tried ("somewhere close"), one ring further each time, before
  MacroThread's automatic spots;
- the Unit Overview is counted: if it shows fewer of a unit than planned
  (sold, lost, or a placement that didn't really happen), that unit goes
  back on the to-place list and is placed again.
"""
from __future__ import annotations

import math
import time
from dataclasses import replace
from pathlib import Path

from ..farm_first import FarmFirst
from ..general.controller import GeneralThread
from ..general.maps import MAPS_DIR, PointZones, load_general_maps
from ..upgrades import card_marks, overview_title
from ..vision.screens import fuzzy_in
from .config import SkyPortalConfig

SKY_MAPS_DIR = MAPS_DIR / "sky_portal"
MAX_RING = 3            # rings of "close by" spots around a unit's points
MISSING_READS = 3       # reads in a row showing a unit missing before re-placing it
REFILL_COOLDOWN = 30.0  # s between re-placing the same unit
MAX_PLACEMENTS_GUARD = 10   # "Max" placements (configs_page.MAX_PLACEMENTS)


class SkyPortalThread(FarmFirst, GeneralThread):
    INTRO = ("Sky Portal (party member) — waits for the vote to finish, then places every unit, "
             "maxes the farm units, then the damage units. Never votes or clicks Play, Next, "
             "Replay or Return to lobby.")

    def __init__(self, capture, detector, settings: SkyPortalConfig | None = None, parent=None):
        super().__init__(capture, detector, settings or SkyPortalConfig(), parent)
        self._sky_map = None

    def run(self) -> None:
        self.settings.auto_vote_start = False
        maps = load_general_maps(Path(SKY_MAPS_DIR))
        self._sky_map = maps[0] if maps else None
        super().run()

    def _new_match(self) -> None:
        super()._new_match()
        self.match.nudged = True        # never walk forward for room
        self._missing_reads: dict[str, int] = {}
        self._refilled_at: dict[str, float] = {}

    # --- somewhere close ---------------------------------------------------
    def _unit_zones(self, whole, key: str):
        zones = super()._unit_zones(whole, key)
        if not isinstance(zones, PointZones) or self.detector.latest is None:
            return zones
        frame_w, frame_h = self._frame_size()
        m, lines = self.match, self.detector.latest.lines
        gap = 0.04 * frame_h
        used = list(m.failed_spots) + list(m.spots)
        for ring in range(MAX_RING + 1):
            ringed = replace(zones, ring=ring)
            if any(all(math.hypot(x - ux, y - uy) > gap for ux, uy in used)
                   for x, y in ringed.spots(lines, frame_w, frame_h)):
                if ring and self._cooldown(f"ring_log_{key}_{ring}", 30):
                    self.log.emit(f"{self._unit_label(key)}: its spots are taken — trying "
                                  f"close by (ring {ring}).", "Info")
                return ringed
        return replace(zones, ring=MAX_RING)

    # --- re-placing missing units -------------------------------------------
    def _on_unit_manager(self, hwnd: int) -> None:
        self._check_missing()
        super()._on_unit_manager(hwnd)

    def _check_missing(self) -> None:
        """Count each unit in the Unit Overview; put missing ones back to place."""
        m, cfg = self.match, self.settings
        det = self.detector.latest
        if not cfg.place_units or m.pending or det is None or det.screen != "unit_manager":
            return
        title = overview_title(det.lines)
        scroll = getattr(self, "_scroll", None)
        if title is None or (scroll is not None and scroll.scrollable):
            return          # part of the list is hidden: can't count
        _, names = card_marks(det.lines, title)
        now = time.monotonic()
        for key in dict.fromkeys(cfg.placement_order):
            name = cfg.unit_names.get(key, "").strip()
            planned = cfg.placement_order.count(key)
            if not name or planned >= MAX_PLACEMENTS_GUARD:
                continue    # unnamed, or "Max" (the real number isn't known)
            seen = sum(1 for n in names if fuzzy_in(name, n, 0.75))
            if seen >= planned or seen == 0:
                # (none at all is more likely a misread than every copy gone)
                self._missing_reads[key] = 0
                continue
            self._missing_reads[key] = self._missing_reads.get(key, 0) + 1
            if self._missing_reads[key] < MISSING_READS:
                continue
            if now - self._refilled_at.get(key, -1e9) < REFILL_COOLDOWN:
                continue
            self._missing_reads[key] = 0
            self._refilled_at[key] = now
            m.pending += [key] * (planned - seen)
            m.counts.pop(key, None)     # read the hotbar counter afresh
            self.log.emit(f"The Unit Overview shows {seen}/{planned} {name} — placing "
                          f"{planned - seen} again.", "Info")

    def _place_paused(self) -> bool:
        return False                    # every unit is placed before upgrading

    def _watch_map(self, det) -> None:
        """The Sky Portal spots are used on every match (whatever the map
        title); without them, General's zones by map name."""
        sky = self._sky_map if getattr(self.settings, "use_map_zones", True) else None
        if sky is None:
            super()._watch_map(det)
            return
        screen = self.detector.tracker.screen
        if screen in ("lobby", "match_found", "loading"):
            self._map_walked = False
        if screen == "lobby":
            self._map = None
        elif self._map is None and screen in ("vote_start", "in_match", "unit_manager", "card_pick"):
            self._map = sky
            self.log.emit("Sky Portal spots loaded.", "Info")

    def _on_vote_start(self, hwnd: int) -> None:
        self._wait("vote start (the party votes, or the timer runs out)")

    def _on_lobby(self, hwnd: int) -> None:
        self._wait("in the lobby (the party leader starts the portal)")
