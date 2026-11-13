"""Infinity Castle's own placement zones: maps/infinity_mansion/<slug>.json.

Same file format as the Summer maps (maps/*.json) and the same MapZones
class, but a separate folder: the same map (e.g. Snowy Town) is played from
a different spot here, and its zones mark where damage units must go.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2

from ..maps import MAPS_DIR, MapZones, extract_avoid, extract_zones, name_box, slugify, titlebar_height
from ..vision.ocr import OcrReader

IC_MAPS_DIR = MAPS_DIR / "infinity_mansion"


def load_ic_maps() -> list[MapZones]:
    maps = []
    for path in sorted(IC_MAPS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            maps.append(MapZones(data["name"], [[tuple(p) for p in z] for z in data["zones"]],
                                 tuple(data["anchor"]) if data.get("anchor") else None,
                                 tuple(data["size"]), data.get("walk"),
                                 [[tuple(p) for p in z] for z in data.get("avoid", [])],
                                 data.get("titlebar")))
        except (OSError, ValueError, KeyError):
            continue
    return maps


def create_ic_map(name: str, screenshot: Path, ocr: OcrReader | None = None) -> MapZones:
    """Save an Infinity Castle map from a screenshot with white circles (the
    map title must be in the shot). Raises ValueError with a message."""
    image = cv2.imread(str(screenshot))
    if image is None:
        raise ValueError(f"Couldn't open {screenshot}.")
    height = image.shape[0]
    zones = [z for z in extract_zones(image) if min(y for _, y in z) < 0.8 * height]  # not the hotbar
    if not zones:
        raise ValueError("No white circles found. Circle the placement areas in pure white.")
    anchor = name_box((ocr or OcrReader()).read(image), name, height)
    if anchor is None:
        raise ValueError(f"Couldn't find the map name '{name}' at the top of the screenshot.")
    zones_map = MapZones(name, zones, anchor, (image.shape[1], height), None,
                         extract_avoid(image), titlebar_height(image))
    IC_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    (IC_MAPS_DIR / f"{slugify(name)}.json").write_text(json.dumps({
        "name": name, "zones": zones, "anchor": list(anchor), "size": list(zones_map.size),
        "titlebar": zones_map.titlebar,
        **({"avoid": zones_map.avoid} if zones_map.avoid else {}),
    }, indent=2), encoding="utf-8")
    return zones_map
