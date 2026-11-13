"""General mode's own placement zones: maps/general/<slug>.json.

Same MapZones class and screenshot method as the Summer maps, but each map
can give different units different zones ("zone_sets"), e.g. on Shibuya:
units 1, 5 and 6 go on the ground loops, Phoenix (4) on the green patches.

    {"name": "Shibuya District", "anchor": [...], "size": [...], "titlebar": 23,
     "zone_sets": [{"units": ["1", "5", "6"], "zones": [...], "avoid": [...]},
                   {"units": ["4"], "zones": [...]}],
     "walk": {...}}            # optional, as in the Summer maps

A unit that isn't in any set uses automatic spots. Maps without a General
file fall back to the Summer zones (maps/*.json).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2

from ..maps import MAPS_DIR, MapZones, extract_avoid, extract_zones, load_maps, name_box, slugify, titlebar_height
from ..vision.ocr import OcrReader

GENERAL_MAPS_DIR = MAPS_DIR / "general"


@dataclass
class GeneralMap(MapZones):
    # unit key → (zones, avoid) for that unit
    unit_zones: dict[str, tuple[list, list]] = field(default_factory=dict)

    def for_unit(self, key: str) -> MapZones | None:
        """This map with only `key`'s zones, or None (automatic spots)."""
        if key not in self.unit_zones:
            return None
        zones, avoid = self.unit_zones[key]
        return replace(self, zones=zones, avoid=avoid, unit_zones={})


def _polygons(raw) -> list[list[tuple[int, int]]]:
    return [[tuple(p) for p in polygon] for polygon in raw or []]


def load_general_maps(dir: Path = GENERAL_MAPS_DIR) -> list[GeneralMap]:
    maps = []
    for path in sorted(dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            unit_zones = {}
            every_zone, every_avoid = [], []
            for group in data["zone_sets"]:
                zones, avoid = _polygons(group["zones"]), _polygons(group.get("avoid"))
                every_zone += zones
                every_avoid += avoid
                for key in group["units"]:
                    unit_zones[str(key)] = (zones, avoid)
            maps.append(GeneralMap(data["name"], every_zone,
                                   tuple(data["anchor"]) if data.get("anchor") else None,
                                   tuple(data["size"]), data.get("walk"), every_avoid,
                                   data.get("titlebar"), unit_zones))
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
