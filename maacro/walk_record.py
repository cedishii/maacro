"""Recording the walk into a lobby door: you walk it once, MAACRO writes it down.

Press "Record" on the Configs tab, switch to Roblox (already teleported in
front of the doors) and walk into the door with W / A / S / D (Shift to
sprint, Space to jump). Recording starts at the first movement key and ends
STOP_AFTER_IDLE s after you let go of everything. The keys are only read
(GetAsyncKeyState, as the hotkeys are) — nothing is pressed for you.

The samples become the walk text the lobby start plays back ("w+d 1.8, w 0.4"):
key changes shorter than MIN_STEP (fingers not lifting at the same moment)
are folded into their neighbours, pauses are dropped, and Shift held for most
of the walk switches sprinting on, so it's played back at the same speed.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal

from .control import input as inp

WALK_VKS = {"w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44, "space": 0x20}
KEY_ORDER = tuple(WALK_VKS)
VK_SHIFT, VK_ESCAPE = 0x10, 0x1B
SAMPLE_EVERY = 0.02
STOP_AFTER_IDLE = 1.5    # s with no movement key → done
WAIT_FOR_FIRST = 30.0    # s to switch to Roblox and start walking
MAX_WALK = 20.0          # s of walking at most
MIN_STEP = 0.15          # s: shorter key changes are folded away


def to_route(samples: list[tuple[float, frozenset, bool]], min_step: float = MIN_STEP) -> tuple[str, bool]:
    """samples: (time, keys held, shift held), oldest first, the last one being
    the end of the walk. → ("w+d 1.8, w 0.4", sprint)."""
    segments: list[list] = []          # [keys, seconds, shift seconds]
    for (t, keys, shift), (t_next, _, _) in zip(samples, samples[1:]):
        span = max(0.0, t_next - t)
        if segments and segments[-1][0] == keys:
            segments[-1][1] += span
            segments[-1][2] += span if shift else 0.0
        else:
            segments.append([keys, span, span if shift else 0.0])
    moving = [s for s in segments if s[0]]
    walked = sum(s[1] for s in moving)
    sprint = walked > 0 and sum(s[2] for s in moving) >= walked / 2
    # Fold short steps into the longer neighbour; then join equal neighbours.
    steps = [s[:2] for s in moving]
    changed = True
    while changed and len(steps) > 1:
        changed = False
        shortest = min(range(len(steps)), key=lambda i: steps[i][1])
        if steps[shortest][1] < min_step:
            i = shortest
            neighbours = [j for j in (i - 1, i + 1) if 0 <= j < len(steps)]
            into = max(neighbours, key=lambda j: steps[j][1])
            steps[into][1] += steps[i][1]
            del steps[i]
            changed = True
        joined = []
        for keys, seconds in steps:
            if joined and joined[-1][0] == keys:
                joined[-1][1] += seconds
                changed = True
            else:
                joined.append([keys, seconds])
        steps = joined
    parts = []
    for keys, seconds in steps:
        seconds = min(20.0, max(0.1, round(seconds, 1)))
        if seconds < min_step and len(steps) > 1:
            continue
        names = "+".join(k for k in KEY_ORDER if k in keys)
        parts.append(f"{names} {seconds:g}")
    return ", ".join(parts), sprint


def held_keys() -> tuple[frozenset, bool]:
    return (frozenset(k for k, vk in WALK_VKS.items() if inp.is_pressed(vk)),
            inp.is_pressed(VK_SHIFT))


class WalkRecorder(QThread):
    """Reads the movement keys while you walk; `done(route, sprint)` at the end."""
    status = Signal(str)
    done = Signal(str, bool)
    failed = Signal(str)

    def __init__(self, read=held_keys, clock=time.monotonic, parent=None):
        super().__init__(parent)
        self._read, self._clock = read, clock

    def run(self) -> None:
        self.status.emit("Switch to Roblox and walk into the door (W/A/S/D, Shift to sprint)…")
        start = self._clock()
        keys, shift = self._read()
        while not keys:
            if self.isInterruptionRequested() or inp.is_pressed(VK_ESCAPE):
                self.failed.emit("Recording cancelled.")
                return
            if self._clock() - start > WAIT_FOR_FIRST:
                self.failed.emit(f"No walking in {WAIT_FOR_FIRST:.0f} s — recording stopped.")
                return
            time.sleep(SAMPLE_EVERY)
            keys, shift = self._read()
        self.status.emit("Recording… let go of the keys once you're in.")
        samples = [(self._clock(), keys, shift)]
        idle_since = None
        while True:
            time.sleep(SAMPLE_EVERY)
            now = self._clock()
            keys, shift = self._read()
            samples.append((now, keys, shift))
            if self.isInterruptionRequested():
                break
            if keys:
                idle_since = None
            elif idle_since is None:
                idle_since = now
            elif now - idle_since >= STOP_AFTER_IDLE:
                break
            if now - samples[0][0] > MAX_WALK:
                break
        route, sprint = to_route(samples)
        if not route:
            self.failed.emit("Nothing was recorded.")
            return
        self.done.emit(route, sprint)
