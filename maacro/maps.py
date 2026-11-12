"""Placement zones per map, drawn by the player.

The player takes a screenshot of a map (zoomed out), circles the areas where
units can go in white, and saves it under the map's name. MAACRO then:
- recognises the map ("Travelling to… Haunted Mansion", or the title in the match),
- lines the screenshot up with the live screen using the map-name text at the
  top (in both pictures, so its position and width give the shift and scale),
- and tries placement spots inside the circled zones first.

Files: maps/<slug>.json (name, zones, anchor) next to maps/<slug>_source.png.
"""
from __future__ import annotations

import json
import math
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .vision.ocr import OcrLine, OcrReader
from .vision.screens import _norm, fuzzy_in

MAPS_DIR = Path(__file__).resolve().parents[1] / "maps"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "map"


@dataclass
class MapZones:
    name: str
    zones: list[list[tuple[int, int]]]      # polygons, in screenshot pixels
    anchor: tuple[float, float, float]      # map-name text in the screenshot: centre x, centre y, width
    size: tuple[int, int]                   # screenshot width, height
    # Optional walk at the start of a match, before placing — the zones are
    # drawn from where it ends. {"key": "d", "seconds": 4.0, "jump": true}
    walk: dict | None = None
    # Areas scribbled over in red inside the zones: never place there (spots
    # you can't use that the game doesn't paint red, like furniture).
    avoid: list[list[tuple[int, int]]] = field(default_factory=list)
    # Height of the window title bar ("Roblox") at the top of the screenshot;
    # live frames don't have one. Used when the map title can't be read.
    titlebar: int | None = None

    # --- matching the live screen ---------------------------------------
    def matches(self, text: str) -> bool:
        # 0.75 like name_box: the stylised title reads as e.g. "Rain Mtlage".
        return fuzzy_in(self.name, text, 0.75)

    def transform(self, lines: list[OcrLine], frame_w: int, frame_h: int):
        """(scale, dx, dy) mapping screenshot pixels onto the live frame, from
        the map-name text near the top of the live screen. Without it (the top
        title isn't up yet at the start of a match), from the window size:
        same width ratio, title bar cut off. None if neither works."""
        title = name_box(lines, self.name, frame_h)
        if title is not None:
            scale = title[2] / self.anchor[2]
            if 0.4 < scale < 3.0:
                return scale, title[0] - scale * self.anchor[0], title[1] - scale * self.anchor[1]
        if self.titlebar is None:
            return None
        scale = frame_w / self.size[0]
        return scale, 0.0, -self.titlebar * scale

    def spots(self, lines: list[OcrLine], frame_w: int, frame_h: int,
              step_fraction: float = 0.045) -> list[tuple[float, float]]:
        """Grid points inside the zones, in live-frame pixels. Empty if the
        screen can't be lined up with the screenshot."""
        fit = self.transform(lines, frame_w, frame_h)
        if fit is None:
            return []
        scale, dx, dy = fit
        step = max(8, int(step_fraction * frame_h))
        spots = []
        def to_live(polygon):
            return np.array([(x * scale + dx, y * scale + dy) for x, y in polygon], np.float32)
        avoid = [to_live(polygon) for polygon in self.avoid]
        for polygon in self.zones:
            live = to_live(polygon)
            left, top = live.min(axis=0)
            right, bottom = live.max(axis=0)
            for y in np.arange(top + step / 2, bottom, step):
                for x in np.arange(left + step / 2, right, step):
                    # Keep clear of the hotbar, the side panel and the window edges.
                    if not (0.05 * frame_w < x < 0.86 * frame_w and 0.12 * frame_h < y < 0.82 * frame_h):
                        continue
                    if cv2.pointPolygonTest(live, (float(x), float(y)), True) < step * 0.3:
                        continue
                    if any(cv2.pointPolygonTest(a, (float(x), float(y)), True) > -step * 0.3 for a in avoid):
                        continue
                    spots.append((float(x), float(y)))
        return spots


def name_box(lines: list[OcrLine], name: str, frame_h: int) -> tuple[float, float, float] | None:
    """Centre x, centre y and width of the map name's words in the top title."""
    from .macro import narrow_to_words   # local import: macro imports this module
    for line in lines:
        if line.y > 0.12 * frame_h or not fuzzy_in(name, line.text, 0.75):
            continue
        words = narrow_to_words(line, name)
        return words.x + words.w / 2, words.y + words.h / 2, float(words.w)
    return None


# --- creating a map from a screenshot -------------------------------------
def extract_zones(image: np.ndarray) -> list[list[tuple[int, int]]]:
    """The areas circled in white: big white strokes, each filled in."""
    height, width = image.shape[:2]
    white = ((image[..., 0] > 235) & (image[..., 1] > 235) & (image[..., 2] > 235)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(white)
    zones = []
    for i in range(1, count):
        x, y, w, h, _ = stats[i]
        # Hand-drawn outlines are big in both directions; text and edges aren't.
        if (w > 0.12 * width or h > 0.12 * height) and w > 0.05 * width and h > 0.05 * height:
            zones.append(_fill_outline((labels == i).astype(np.uint8), width, height))
    return zones


def extract_avoid(image: np.ndarray) -> list[list[tuple[int, int]]]:
    """Areas scribbled over in red: big pure-red strokes, as their outer wrap.
    Small red bits (lamps, effects) are left out."""
    height, width = image.shape[:2]
    b, g, r = (image[..., i].astype(np.int16) for i in range(3))
    red = ((r > 190) & (g < 70) & (b < 80)).astype(np.uint8)
    # Scribbles are loose strokes: join them up before measuring.
    red = cv2.dilate(red, np.ones((9, 9), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(red)
    areas = []
    for i in range(1, count):
        if stats[i][4] > 0.0012 * width * height:
            points = np.column_stack(np.nonzero(labels == i))[:, ::-1]
            hull = cv2.convexHull(points).reshape(-1, 2)
            areas.append([(int(px), int(py)) for px, py in hull])
    return areas


def titlebar_height(image: np.ndarray) -> int:
    """Rows of the plain light window title bar at the top (0 if none)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    middle = gray[:, image.shape[1] // 4: image.shape[1] * 3 // 4]
    rows = 0
    while rows < min(60, image.shape[0]) and middle[rows].mean() > 225 and middle[rows].std() < 25:
        rows += 1
    return rows


def _fill_outline(stroke: np.ndarray, width: int, height: int) -> list[tuple[int, int]]:
    """The inside of one hand-drawn loop as a polygon. Small gaps in the stroke
    are closed first; a loop that's too open falls back to its outer wrap."""
    gap = max(5, int(0.012 * max(width, height)))
    closed = cv2.dilate(stroke, np.ones((gap, gap), np.uint8))
    # Flood the outside from the border; what's left unreached is the inside.
    canvas = cv2.copyMakeBorder(closed, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    flood = canvas.copy()
    cv2.floodFill(flood, np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), np.uint8), (0, 0), 1)
    inside = ((flood == 0) | (canvas == 1)).astype(np.uint8)[1:-1, 1:-1]
    points = np.column_stack(np.nonzero(stroke))[:, ::-1]
    hull = cv2.convexHull(points).reshape(-1, 2)
    contours, _ = cv2.findContours(inside, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        best = max(contours, key=cv2.contourArea)
        enclosed = cv2.contourArea(best) - int(closed.sum()) * 0.5
        if enclosed > 0.25 * cv2.contourArea(hull):
            polygon = cv2.approxPolyDP(best, 2, True).reshape(-1, 2)
            return [(int(px), int(py)) for px, py in polygon]
    return [(int(px), int(py)) for px, py in hull]


def create_map(name: str, screenshot: Path, ocr: OcrReader | None = None,
               walk: dict | None = None,
               anchor: tuple[float, float, float] | None = None) -> MapZones:
    """Save a map from a screenshot with white circles. Raises ValueError with a
    message for the player if something's missing. `walk` (see MapZones) is
    the walk done before placing; if not given, a saved one is kept."""
    image = cv2.imread(str(screenshot))
    if image is None:
        raise ValueError(f"Couldn't open {screenshot}.")
    zones = extract_zones(image)
    if not zones:
        raise ValueError("No white circles found. Circle the placement areas in pure white.")
    if anchor is None:
        lines = (ocr or OcrReader()).read(image)
        anchor = name_box(lines, name, image.shape[0])
    if anchor is None:
        raise ValueError(f"Couldn't find the map name '{name}' at the top of the screenshot. "
                         "Include the map title in the screenshot and check the spelling.")
    slug = slugify(name)
    if walk is None:
        try:
            walk = json.loads((MAPS_DIR / f"{slug}.json").read_text(encoding="utf-8")).get("walk")
        except (OSError, ValueError):
            walk = None
    zones_map = MapZones(name, zones, anchor, (image.shape[1], image.shape[0]), walk,
                         extract_avoid(image), titlebar_height(image))
    MAPS_DIR.mkdir(exist_ok=True)
    source = MAPS_DIR / f"{slug}_source.png"
    if Path(screenshot).resolve() != source.resolve():
        shutil.copyfile(screenshot, source)
    (MAPS_DIR / f"{slug}.json").write_text(json.dumps({
        "name": name, "zones": zones, "anchor": list(anchor), "size": list(zones_map.size),
        "source": source.name, "titlebar": zones_map.titlebar,
        **({"avoid": zones_map.avoid} if zones_map.avoid else {}),
        **({"walk": walk} if walk else {}),
    }, indent=2), encoding="utf-8")
    return zones_map


def load_maps() -> list[MapZones]:
    maps = []
    for path in sorted(MAPS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            maps.append(MapZones(data["name"], [[tuple(p) for p in z] for z in data["zones"]],
                                 tuple(data["anchor"]), tuple(data["size"]),
                                 data.get("walk"),
                                 [[tuple(p) for p in z] for z in data.get("avoid", [])],
                                 data.get("titlebar")))
        except (OSError, ValueError, KeyError):
            continue
    return maps


def find_map(maps: list[MapZones], lines: list[OcrLine]) -> MapZones | None:
    """The saved map whose name appears on screen (loading screen or match title)."""
    for zones_map in maps:
        if any(zones_map.matches(line.text) for line in lines):
            return zones_map
    return None


def spread(spots: list[tuple[float, float]], first_near: list[tuple[float, float]],
           min_gap: float) -> list[tuple[float, float]]:
    """Spots next to `first_near` first, then the rest, keeping a minimum gap."""
    def key(p):
        if not first_near:
            return 0.0
        return min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in first_near)
    picked: list[tuple[float, float]] = []
    for spot in sorted(spots, key=key):
        if all(math.hypot(spot[0] - q[0], spot[1] - q[1]) >= min_gap for q in picked):
            picked.append(spot)
    return picked
