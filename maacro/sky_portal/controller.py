"""Sky Portal, as a party member: someone else hosts the portal.

    lobby: wait → vote start: zoom out, vote Yes (everyone votes, not just
    the leader), walk to the placing spot (forward, left, forward)
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
- the spots follow the spawn: the character doesn't always spawn on the
  same spot, so the view is lined up with the reference picture once per
  match (align.py) and every spot is shifted by the same amount;
- the Unit Overview is counted: if it shows fewer of a unit than planned
  (sold, lost, or a placement that didn't really happen), that unit goes
  back on the to-place list and is placed again.
"""
from __future__ import annotations

import math
import time
from dataclasses import replace
from pathlib import Path

import cv2

from ..farm_first import FarmFirst
from ..general.controller import GeneralThread
from ..general.maps import MAPS_DIR, PointZones, load_general_maps
from ..upgrades import card_marks, overview_title
from ..control import input as inp
from ..vision.screens import fuzzy_in
from ..placement import button_unit
from ..upgrade_levels import upgrade_level
from .align import spawn_shift
from .config import SkyPortalConfig

SKY_MAPS_DIR = MAPS_DIR / "sky_portal"
MAX_RING = 3            # rings of "close by" spots around a unit's points
MISSING_READS = 3       # reads in a row showing a unit missing before re-placing it
REFILL_COOLDOWN = 30.0  # s between re-placing the same unit
PLACE_SPEED = 0.4       # × MacroThread's pause between placements (others race for the spots)
ALIGN_TRIES = 3         # line-up attempts per match before using the spots as drawn
MAX_PLACEMENTS_GUARD = 10   # "Max" placements (configs_page.MAX_PLACEMENTS)


class SkyPortalThread(FarmFirst, GeneralThread):
    INTRO = ("Sky Portal (party member) — votes Yes, walks to the spot, places every unit, "
             "maxes the farm units, then the damage units. Never clicks Play, Next, Replay or Return to lobby.")

    _shift = None
    _align_tries = 0
    _reference = None
    _vote_zoomed = False
    _vote_seen = False
    _route_walked = False

    def __init__(self, capture, detector, settings: SkyPortalConfig | None = None, parent=None):
        super().__init__(capture, detector, settings or SkyPortalConfig(), parent)
        self._sky_map = None

    def run(self) -> None:
        maps = load_general_maps(Path(SKY_MAPS_DIR))
        self._sky_map = maps[0] if maps else None
        self._reference = cv2.imread(str(SKY_MAPS_DIR / "sky_portal_reference.png"))
        super().run()

    def _new_match(self) -> None:
        super()._new_match()
        self.match.nudged = True        # never walk forward for room
        self._missing_reads: dict[str, int] = {}
        self._refilled_at: dict[str, float] = {}
        self._shift = None              # spawn offset in live pixels, once measured
        self._vote_seen = False
        self._route_walked = False
        self._rush_logged = False
        self._align_tries = 0
        self._vote_zoomed = False

    def _cooldown(self, key: str, seconds: float) -> bool:
        if key == "place":
            seconds *= PLACE_SPEED
        return super()._cooldown(key, seconds)

    # --- following the spawn ---------------------------------------------------
    def _spawn_offset(self, zones) -> tuple[float, float]:
        """The spawn offset in screenshot pixels (measured once per match)."""
        if self._shift is None and self._align_tries < ALIGN_TRIES and self._reference is not None:
            self._align_tries += 1
            _, frame = self.capture.latest_frame()
            found = spawn_shift(self._reference, zones.titlebar or 0, frame) if frame is not None else None
            if found is not None:
                self._shift = found[:2]
                self.log.emit(f"Lined up with the Sky Portal picture: spawn offset "
                              f"{found[0]:+.0f}, {found[1]:+.0f} px ({found[2]} landmarks).", "Info")
            elif self._align_tries == 1 and getattr(self.settings, "zoom_out_seconds", 0) > 0:
                # Probably not zoomed out (yet): zoom out and look again.
                self.log.emit("Couldn't line up with the Sky Portal picture — zooming out again.", "Info")
                inp.press(self.capture.hwnd, "o", hold=self.settings.zoom_out_seconds)
                self._sleep(0.4)
            elif self._align_tries >= ALIGN_TRIES:
                self._shift = (0.0, 0.0)
                self.log.emit("Couldn't line up with the Sky Portal picture — using the spots "
                              "as drawn.", "Warn")
        if not self._shift:
            return 0.0, 0.0
        frame_w, _ = self._frame_size()
        scale = frame_w / zones.size[0]
        return self._shift[0] / scale, self._shift[1] / scale

    # --- somewhere close ---------------------------------------------------
    def _unit_zones(self, whole, key: str):
        zones = super()._unit_zones(whole, key)
        if zones is None or self.detector.latest is None:
            return zones
        dx, dy = self._spawn_offset(zones)
        if not isinstance(zones, PointZones):
            # An area (Phoenix's balcony): move it, and its no-go marks, with the spawn.
            move = lambda polygons: [[(x + dx, y + dy) for x, y in poly] for poly in polygons]
            return replace(zones, zones=move(zones.zones), avoid=move(zones.avoid)) if dx or dy else zones
        if dx or dy:
            zones = replace(zones, points=[(x + dx, y + dy) for x, y in zones.points])
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

    # --- upgrade caps ---------------------------------------------------------
    def _buttons_to_upgrade(self, lines, buttons):
        """Farm first (FarmFirst), units at their cap left out, and from the
        rush wave the rush unit (Phoenix) up to its minimum before anything."""
        kept = self._capped_out(lines, super()._buttons_to_upgrade(lines, buttons))
        rush = self._rush_buttons(lines, buttons)
        return rush + [b for b in kept if b not in rush] if rush else kept

    def _rush_buttons(self, lines, buttons):
        cfg = self.settings
        wave = getattr(getattr(self.detector, "tracker", None), "wave", None)
        need, key = int(getattr(cfg, "rush_upgrades", 0) or 0), str(getattr(cfg, "rush_unit", ""))
        if not need or not wave or wave < int(getattr(cfg, "rush_wave", 0) or 0) or not buttons:
            return []
        _, frame = self.capture.latest_frame()
        names = cfg.unit_names
        rush = []
        for button in buttons:
            if button_unit(button, lines, names) != key:
                continue
            level = upgrade_level(frame, button) if frame is not None else None
            if level is None or level[0] < need:
                rush.append(button)
        if rush and not getattr(self, "_rush_logged", False):
            self._rush_logged = True
            self.log.emit(f"Wave {wave} — upgrading {self._unit_label(key)} to at least {need} "
                          "before anything else (against leaks).", "Info")
        return rush

    def _capped_out(self, lines, kept):
        """Leave out units already at their upgrade cap (e.g. Elyssia at 2)."""
        caps = {k: int(v) for k, v in (getattr(self.settings, "upgrade_caps", {}) or {}).items() if int(v) > 0}
        if not caps or not kept:
            return kept
        _, frame = self.capture.latest_frame()
        if frame is None:
            return kept
        names = self.settings.unit_names
        out = []
        for button in kept:
            key = button_unit(button, lines, names)
            level = upgrade_level(frame, button) if key in caps else None
            if level is not None and level[0] >= caps[key]:
                if self._cooldown(f"cap_log_{key}", 120):
                    self.log.emit(f"{self._unit_label(key)} is at upgrade {level[0]}/{level[1]} "
                                  f"(cap {caps[key]}) — not upgrading it further.", "Info")
                continue
            out.append(button)
        return out

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

    def _watchdog(self, hwnd: int, screen: str) -> None:
        # Upgrading the damage units goes on for most of the match: a long
        # time in the unit manager is normal here, not "stuck".
        m, cfg = self.match, self.settings
        if screen == "unit_manager" and cfg.upgrade_units and not m.upgrades_done and not m.pending:
            self._screen_since = time.monotonic()
        super()._watchdog(hwnd, screen)

    def _on_vote_start(self, hwnd: int) -> None:
        """Zoom out, vote Yes, then walk to the placing spot — all while the
        vote runs, so placing starts the moment the match does."""
        self._vote_seen = True
        seconds = getattr(self.settings, "zoom_out_seconds", 0)
        if not self._vote_zoomed and seconds > 0 and self.settings.place_units:
            self._vote_zoomed = True
            self._say("Vote start — zooming out (O)")
            inp.press(hwnd, "o", hold=seconds)
            self.match.zoomed = True        # don't zoom again when the match starts
            self._rezoomed = True
            return
        super()._on_vote_start(hwnd)        # votes Yes if switched on, else waits
        voted = self.match.voted_start or not self.settings.auto_vote_start
        if not self._route_walked and self.settings.place_units and (
                voted or time.monotonic() - self._screen_since > 4):
            self._walk_route(hwnd)

    def _on_in_match(self, hwnd: int) -> None:
        # The vote ended before the walk (everyone voted at once): walk now,
        # before placing anything.
        if (self._vote_seen and not self._route_walked and self.settings.place_units
                and not self.match.placed):
            self._walk_route(hwnd)
            return
        super()._on_in_match(hwnd)

    def _walk_route(self, hwnd: int) -> None:
        """Walk the route from the spawn to the placing spot (walk_route:
        [key, seconds] steps), sprinting with Shift if walk_sprint is on."""
        self._route_walked = True
        route = [(str(k).lower(), float(t)) for k, t in (getattr(self.settings, "walk_route", []) or [])
                 if str(k).lower() in inp.SCAN_CODES]
        if not route:
            return
        text = ", ".join(f"{k.upper()} {t:g} s" for k, t in route)
        self._say(f"Walking to the placing spot ({text})")
        inp.focus(hwnd)
        sprint = getattr(self.settings, "walk_sprint", True)
        if sprint:
            inp.key_down("shift")
        try:
            for key, seconds in route:
                inp.key_down(key)
                try:
                    if not self._sleep(seconds):
                        return
                finally:
                    inp.key_up(key)
        finally:
            if sprint:
                inp.key_up("shift")
        self.log.emit(f"Walked to the placing spot ({text}).", "Info")
        self._sleep(0.3)

    def _on_lobby(self, hwnd: int) -> None:
        self._wait("in the lobby (the party leader starts the portal)")
