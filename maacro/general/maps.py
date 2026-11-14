"""General mode's own placement zones: maps/general/<slug>.json.

Same MapZones class and screenshot method as the Summer maps, but each map
can give different units different zones ("zone_sets"), e.g. on Shibuya:
units 1, 5 and 6 go on the ground loops, Phoenix (4) on the green patches.

    {"name": "Shibuya District", "anchor": [...], "size": [...], "titlebar": 23,
     "zone_sets": [{"units": ["1", "5", "6"], "zones": [...], "avoid": [...]},
                   {"units": ["4"], "zones": [...]}],
     "walk": {...}}            # optional, as in the Summer maps

A set can give exact "points" ([[x, y], ...], screenshot pixels) instead of
zones: that unit is placed on exactly those spots, in that order (e.g. the
centres of circles drawn on a screenshot). A unit that isn't in any set uses
automatic spots. Maps without a General
file fall back to the Summer zones (maps/*.json).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2

from ..maps import MAPS_DIR, MapZones, extract_avoid, extract_zones, load_maps, name_box, slugify, titlebar_height
from ..vision.ocr import OcrReader

GENERAL_MAPS_DIR = MAPS_DIR / "general"
RING_STEP = 0.05     # × height between the rings of "close by" spots around a point


@dataclass
class GeneralMap(MapZones):
    # unit key → (zones, avoid) for that unit
    unit_zones: dict[str, tuple[list, list]] = field(default_factory=dict)
    # unit key → exact spots for that unit
    unit_points: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    def for_unit(self, key: str) -> MapZones | None:
        """This map with only `key`'s zones (or exact points), or None (automatic spots)."""
        if key in self.unit_points:
            return PointZones(self.name, [], self.anchor, self.size, self.walk, [], self.titlebar,
                              self.unit_points[key])
        if key not in self.unit_zones:
            return None
        zones, avoid = self.unit_zones[key]
        return replace(self, zones=zones, avoid=avoid, unit_zones={}, unit_points={})


@dataclass
class PointZones(MapZones):
    """Exact spots instead of areas: the live positions of `points`."""
    points: list[tuple[float, float]] = field(default_factory=list)
    # 0 = just the points; n = also n rings of spots around each (when the
    # points themselves are taken or failed: "somewhere close").
    ring: int = 0

    def spots(self, lines, frame_w: int, frame_h: int, step_fraction: float = 0.045):
        fit = self.transform(lines, frame_w, frame_h)
        if fit is None:
            return []
        scale, dx, dy = fit
        live = [(x * scale + dx, y * scale + dy) for x, y in self.points]
        out = list(live)
        for r in range(1, self.ring + 1):
            radius, count = RING_STEP * frame_h * r, 6 * r
            for x, y in live:
                out += [(x + radius * math.cos(2 * math.pi * (i + 0.5 * r) / count),
                         y + radius * math.sin(2 * math.pi * (i + 0.5 * r) / count))
                        for i in range(count)]
        return [(x, y) for x, y in out if usable_point(x, y, frame_w, frame_h)]


def usable_point(x: float, y: float, frame_w: int, frame_h: int) -> bool:
    """Inside the window and off the game's buttons: the top bar, the hotbar
    (bottom middle) and the window's very bottom. Beside the hotbar is fine."""
    if not (0.02 * frame_w < x < 0.98 * frame_w and 0.10 * frame_h < y < 0.97 * frame_h):
        return False
    return not (0.31 * frame_w < x < 0.70 * frame_w and y > 0.85 * frame_h)


def _polygons(raw) -> list[list[tuple[int, int]]]:
    return [[tuple(p) for p in polygon] for polygon in raw or []]


def load_general_maps(dir: Path = GENERAL_MAPS_DIR) -> list[GeneralMap]:
    maps = []
    for path in sorted(dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            unit_zones, unit_points = {}, {}
            every_zone, every_avoid = [], []
            for group in data["zone_sets"]:
                if group.get("points"):
                    for key in group["units"]:
                        unit_points[str(key)] = [tuple(p) for p in group["points"]]
                    continue
                zones, avoid = _polygons(group["zones"]), _polygons(group.get("avoid"))
                every_zone += zones
                every_avoid += avoid
                for key in group["units"]:
                    unit_zones[str(key)] = (zones, avoid)
            maps.append(GeneralMap(data["name"], every_zone,
                                   tuple(data["anchor"]) if data.get("anchor") else None,
                                   tuple(data["size"]), data.get("walk"), every_avoid,
                                   data.get("titlebar"), unit_zones, unit_points))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return maps


def maps_for_general() -> list[MapZones]:
    """General's own maps first, then the Summer maps it has no file for."""
    own = load_general_maps()
    names = {m.name.lower() for m in own}
    return own + [m for m in load_maps() if m.name.lower() not in names]


def create_general_map(name: str, shots: list[tuple[list[str], Path]],
                       ocr: OcrReader | None = None, walk: dict | None = None) -> GeneralMap:
    """Save a General map from screenshots with white circles, one per group
    of units: [(["1", "5", "6"], shot_a), (["4"], shot_b)]. All shots must be
    from the same (zoomed-out) camera; the map title is read from whichever
    shot shows it. Raises ValueError with a message for the player."""
    reader = ocr or OcrReader()
    anchor = size = titlebar = None
    groups = []
    for units, shot in shots:
        image = cv2.imread(str(shot))
        if image is None:
            raise ValueError(f"Couldn't open {shot}.")
        height = image.shape[0]
        zones = [z for z in extract_zones(image) if min(y for _, y in z) < 0.8 * height]  # not the hotbar
        if not zones:
            raise ValueError(f"No white circles found in {Path(shot).name}.")
        groups.append({"units": [str(u) for u in units], "zones": zones,
                       **({"avoid": a} if (a := extract_avoid(image)) else {})})
        size = size or (image.shape[1], height)
        titlebar = titlebar if titlebar is not None else titlebar_height(image)
        anchor = anchor or name_box(reader.read(image), name, height)
    GENERAL_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    (GENERAL_MAPS_DIR / f"{slugify(name)}.json").write_text(json.dumps({
        "name": name, "anchor": list(anchor) if anchor else None, "size": list(size),
        "titlebar": titlebar, "zone_sets": groups, **({"walk": walk} if walk else {}),
    }, indent=2), encoding="utf-8")
    return next(m for m in load_general_maps() if m.name == name)
