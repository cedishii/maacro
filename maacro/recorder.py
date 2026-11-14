"""Recording unit placements: you place units by hand, MAACRO saves where.

While recording, pressing a hotbar key (1–6) or clicking a hotbar card picks
that unit; the next left click in the Roblox window is where it was placed.
A right click or Esc cancels the pick. Clicks with no unit picked are
ignored (menus, buttons…).

Saving turns every recorded spot into a small round zone for that unit in
General mode's map file (maps/general/<slug>.json, the same per-unit zones as
the screenshot method), so General places each unit where you put it. Units
you didn't record keep the zones they had.
"""
from __future__ import annotations

import ctypes
import json
import math
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from .general.maps import GENERAL_MAPS_DIR
from .maps import slugify
from .vision.hotbar import CARD_SPACING

ZONE_RADIUS = 0.06      # × window height: the round zone around each recorded spot
HOTBAR_TOP = 0.80       # × height: clicks below this are on the hotbar
# MapZones.spots only uses this part of the window (hotbar, side panel and edges are out).
USABLE = (0.05, 0.86, 0.12, 0.82)   # x from, x to, y from, y to (× width / height)

VK_LBUTTON, VK_RBUTTON, VK_ESCAPE = 0x01, 0x02, 0x1B
UNIT_VKS = {0x31 + i: str(i + 1) for i in range(6)}     # 1–6 on the main keyboard


def hotbar_slot(x: float, y: float, width: int, height: int) -> str | None:
    """The hotbar card (1–6) under a click, or None."""
    if y < HOTBAR_TOP * height:
        return None
    slot = (x - width / 2) / (CARD_SPACING * width) + 3.5
    nearest = round(slot)
    if 1 <= nearest <= 6 and abs(slot - nearest) < 0.5:
        return str(nearest)
    return None


def usable(x: float, y: float, width: int, height: int) -> bool:
    """MAACRO can place here (not under the hotbar, side panel or window edge)."""
    return USABLE[0] * width < x < USABLE[1] * width and USABLE[2] * height < y < USABLE[3] * height


def zone_circle(x: float, y: float, radius: float, points: int = 16) -> list[tuple[int, int]]:
    return [(int(round(x + radius * math.cos(2 * math.pi * i / points))),
             int(round(y + radius * math.sin(2 * math.pi * i / points)))) for i in range(points)]


@dataclass
class Recording:
    """Spots recorded in one camera view, in live-window pixels."""
    size: tuple[int, int] = (0, 0)                      # window width, height
    anchor: tuple[float, float, float] | None = None    # map title: centre x, centre y, width
    spots: list[tuple[str, float, float]] = field(default_factory=list)

    def add(self, key: str, x: float, y: float) -> None:
        self.spots.append((key, float(x), float(y)))

    def undo(self) -> None:
        if self.spots:
            self.spots.pop()

    def by_unit(self) -> dict[str, list[tuple[float, float]]]:
        units: dict[str, list[tuple[float, float]]] = {}
        for key, x, y in self.spots:
            units.setdefault(key, []).append((x, y))
        return units


def _to_space(points, rec: Recording, data: dict):
    """Recorded points into an existing map file's screenshot pixels."""
    old_anchor, old_size = data.get("anchor"), data.get("size") or rec.size
    if old_anchor and rec.anchor:
        k = old_anchor[2] / rec.anchor[2]
        return [(old_anchor[0] + (x - rec.anchor[0]) * k, old_anchor[1] + (y - rec.anchor[1]) * k)
                for x, y in points], k
    # No title to line up with: same width ratio, the file's title bar on top.
    k = old_size[0] / rec.size[0]
    bar = data.get("titlebar") or 0
    return [(x * k, y * k + bar) for x, y in points], k


def save_recording(name: str, rec: Recording, frame: np.ndarray | None = None,
                   folder: Path = GENERAL_MAPS_DIR) -> Path:
    """Write (or update) General's map file for `name`. Raises ValueError."""
    name = name.strip()
    if not name:
        raise ValueError("Type the map's name first.")
    if not rec.spots or not rec.size[0]:
        raise ValueError("Nothing recorded yet.")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slugify(name)}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, ValueError):
        data = None
    if data is None:
        data = {"name": name, "anchor": list(rec.anchor) if rec.anchor else None,
                "size": list(rec.size), "titlebar": 0, "zone_sets": []}
    units = rec.by_unit()
    sets = []
    for group in data.get("zone_sets", []):             # units not recorded keep their zones
        kept = [u for u in group.get("units", []) if str(u) not in units]
        if kept:
            sets.append({**group, "units": kept})
    for key in sorted(units):
        points, k = _to_space(units[key], rec, data)
        radius = ZONE_RADIUS * rec.size[1] * k
        sets.append({"units": [key], "zones": [zone_circle(x, y, radius) for x, y in points],
                     "recorded": True})
    data["zone_sets"] = sets
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if frame is not None:
        cv2.imwrite(str(folder / f"{slugify(name)}_recorded.png"), draw_spots(frame, rec))
    return path


def draw_spots(frame: np.ndarray, rec: Recording) -> np.ndarray:
    """The frame with each recorded spot circled and numbered."""
    image = frame[:, :, :3].copy() if frame.ndim == 3 and frame.shape[2] == 4 else frame.copy()
    radius = int(ZONE_RADIUS * image.shape[0])
    for key, x, y in rec.spots:
        ok = usable(x, y, image.shape[1], image.shape[0])
        color = (255, 255, 255) if ok else (60, 60, 255)
        cv2.circle(image, (int(x), int(y)), radius, color, 2)
        cv2.putText(image, key, (int(x) - 7, int(y) + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    return image


# --- watching your clicks ------------------------------------------------------
class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class ClickWatcher(QThread):
    """Watches the keyboard and mouse while Roblox is in front (reads only,
    sends nothing)."""
    picked = Signal(str)                    # unit key picked (key press or hotbar click)
    placed = Signal(str, float, float)      # unit key, client x, y
    cancelled = Signal()

    def __init__(self, get_hwnd, parent=None):
        super().__init__(parent)
        self.get_hwnd = get_hwnd

    def run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetAsyncKeyState.restype = ctypes.c_short
        user32.GetForegroundWindow.restype = wintypes.HWND
        down = lambda vk: bool(user32.GetAsyncKeyState(vk) & 0x8000)
        watched = [VK_LBUTTON, VK_RBUTTON, VK_ESCAPE, *UNIT_VKS]
        was = {vk: down(vk) for vk in watched}
        armed = None
        while not self.isInterruptionRequested():
            self.msleep(10)
            now = {vk: down(vk) for vk in watched}
            pressed = [vk for vk in watched if now[vk] and not was[vk]]
            was = now
            hwnd = self.get_hwnd()
            if not pressed or not hwnd or user32.GetForegroundWindow() != hwnd:
                continue
            for vk in pressed:
                if vk in UNIT_VKS:
                    armed = UNIT_VKS[vk]
                    self.picked.emit(armed)
                elif vk in (VK_RBUTTON, VK_ESCAPE):
                    if armed:
                        armed = None
                        self.cancelled.emit()
                elif vk == VK_LBUTTON:
                    point = _POINT()
                    user32.GetCursorPos(ctypes.byref(point))
                    user32.ScreenToClient(wintypes.HWND(hwnd), ctypes.byref(point))
                    rect = wintypes.RECT()
                    user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(rect))
                    slot = hotbar_slot(point.x, point.y, rect.right, rect.bottom)
                    if slot:
                        armed = slot
                        self.picked.emit(slot)
                    elif armed:
                        self.placed.emit(armed, float(point.x), float(point.y))
                        armed = None
