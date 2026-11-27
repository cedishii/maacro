"""Profiles picked by map: name a profile after a map ("Shibuya District",
"Shibuya District Act", "Rain Village Summer Hunt") and it's used by itself
whenever a match on that map starts — a different team or placement plan per
map, with no clicking between runs.

`with_auto_profile(ModeThread)` adds this to any mode's controller (like
party.with_party), without changing the controller: when the map is known
(loading screen / vote start) and no unit has been placed yet, the profile's
unit setup replaces the current one for this match. A map without a profile
goes back to the mode's own setup.
"""
from __future__ import annotations

import copy
import functools

from . import profiles
from .history import split_map

# What a profile changes: the unit setup and how it's played, not the mode's
# switches the player set on purpose for this session.
PROFILE_FIELDS = ("placement_order", "unit_names", "upgrade_priority", "path_units", "farm_units",
                  "green_units", "upgrade_caps", "place_from_wave", "upgrade_from_wave", "optional_units",
                  "card_strategy", "zoom_out_seconds")
MAP_SCREENS = ("loading", "vote_start", "in_match")


def profile_for_map(names: list[str], raw_map: str) -> str | None:
    """The best profile name for this map: same map and stage kind first,
    then the same map with no kind in the profile name. None if none fits."""
    want_map, want_kind = split_map(raw_map)
    if not want_map:
        return None
    exact = plain = None
    for name in names:
        p_map, p_kind = split_map(name)
        if p_map != want_map:
            continue
        if p_kind and p_kind == want_kind and exact is None:
            exact = name
        elif not p_kind and plain is None:
            plain = name
    return exact or plain


@functools.lru_cache(maxsize=None)
def with_auto_profile(cls):
    if getattr(cls, "_auto_profile", False):
        return cls

    class AutoProfileThread(cls):
        _auto_profile = True
        profile_mode = ""           # set by the Main page: the mode key (profiles/<mode>/)
        auto_profiles = True        # Settings → "Use the profile named after the map"

        def run(self) -> None:
            self._base_settings = self.settings
            self._profile_match = None
            self._profile_map = None
            self._profile_name = None
            super().run()

        def _watch_map(self, det) -> None:
            super()._watch_map(det)
            try:
                self._pick_profile()
            except Exception as exc:          # never let this stop the macro
                self.log.emit(f"Couldn't pick a profile for this map: {exc}", "Warn")

        def _pick_profile(self) -> None:
            if not (self.auto_profiles and self.profile_mode):
                return
            if self.detector.tracker.screen not in MAP_SCREENS:
                return
            raw = self.detector.tracker.map_name or ""
            if not raw:
                return
            m = self.match
            if self._profile_match is m and self._profile_map == raw:
                return          # already decided for this match and map
            if m.placed:
                self._profile_match, self._profile_map = m, raw
                return          # units already going down: don't change plans mid-match
            self._profile_match, self._profile_map = m, raw
            base = getattr(self, "_base_settings", None) or self.settings
            name = profile_for_map(profiles.list_profiles(self.profile_mode), raw)
            if name is None:
                if self._profile_name is not None:
                    self.settings = base
                    self._profile_name = None
                    m.pending = list(base.placement_order)
                    self.log.emit(f"Map {split_map(raw)[0]}: no profile for it — back to the "
                                  "mode's own setup.", "Info")
                return
            if name == self._profile_name:
                m.pending = list(self.settings.placement_order)
                return
            loaded = profiles.load_profile(self.profile_mode, name, type(base))
            merged = copy.copy(base)
            for field in PROFILE_FIELDS:
                if hasattr(merged, field) and hasattr(loaded, field):
                    setattr(merged, field, getattr(loaded, field))
            self.settings = merged
            self._profile_name = name
            m.pending = list(merged.placement_order)
            self.log.emit(f"Map {split_map(raw)[0]} → using profile '{name}' "
                          f"({len(merged.placement_order)} placements).", "Info")

    AutoProfileThread.__name__ = f"AutoProfile{cls.__name__}"
    AutoProfileThread.__qualname__ = AutoProfileThread.__name__
    return AutoProfileThread
