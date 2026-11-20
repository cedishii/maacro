"""Recording the walk into a lobby door: you walk it once, MAACRO writes it down.

Press "Record" on the Configs tab, switch to Roblox (already teleported in
front of the doors) and walk into the door with W / A / S / D (Shift to
sprint, Space to jump), turning the camera with the right mouse button if
the way needs it. Recording starts at the first movement key and ends
STOP_AFTER_IDLE s after you let go of everything. Nothing is pressed for you:
the keys are only read (GetAsyncKeyState, as the hotkeys are) and so is the
mouse (raw input — Roblox locks the cursor while you turn, so the cursor
position doesn't move, but the mouse's own movement still comes through).

The samples become the walk the lobby start plays back, e.g.
"w+d 1.8, turn 240, w 0.4": key changes shorter than MIN_STEP (fingers not
lifting at the same moment) are folded into their neighbours, pauses are
dropped, a camera turn is the mouse movement while the right button was held
(played back the same way, so it turns the same amount), and Shift held for
most of the walk switches sprinting on, so it's played back at the same speed.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QThread, Signal

from .control import input as inp

WALK_VKS = {"w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44, "space": 0x20}
KEY_ORDER = tuple(WALK_VKS)
VK_SHIFT, VK_ESCAPE, VK_RBUTTON = 0x10, 0x1B, 0x02
SAMPLE_EVERY = 0.01
STOP_AFTER_IDLE = 1.5    # s with no movement key (and no turning) → done
WAIT_FOR_FIRST = 30.0    # s to switch to Roblox and start walking
MAX_WALK = 20.0          # s of walking at most
MIN_STEP = 0.15          # s: shorter key changes are folded away
MIN_TURN = 10            # mouse counts: smaller turns are a hand wobble


def _fold(steps: list[list], min_step: float) -> list[list]:
    """[[keys, seconds]…]: fold steps shorter than min_step into their longer
    neighbour and join equal neighbours."""
    steps = [list(s) for s in steps]
    changed = True
    while changed and len(steps) > 1:
        changed = False
        shortest = min(range(len(steps)), key=lambda i: steps[i][1])
        if steps[shortest][1] < min_step:
            neighbours = [j for j in (shortest - 1, shortest + 1) if 0 <= j < len(steps)]
            into = max(neighbours, key=lambda j: steps[j][1])
            steps[into][1] += steps[shortest][1]
            del steps[shortest]
            changed = True
        joined: list[list] = []
        for keys, seconds in steps:
            if joined and joined[-1][0] == keys:
                joined[-1][1] += seconds
                changed = True
            else:
                joined.append([keys, seconds])
        steps = joined
    return steps


def to_route(samples: list[tuple], min_step: float = MIN_STEP, min_turn: int = MIN_TURN) -> tuple[str, bool]:
    """samples: (time, keys held, shift held[, mouse counts moved — None when
    the right button isn't held]), oldest first, the last one being the end of
    the walk. → ("w+d 1.8, turn 240, w 0.4", sprint)."""
    events: list[list] = []            # ["keys", keys, seconds, shift seconds] / ["turn", counts]
    turn = None
    for current, following in zip(samples, samples[1:]):
        t, keys, shift = current[:3]
        dx = current[3] if len(current) > 3 else None
        span = max(0.0, following[0] - t)
        if dx is None:
            turn = None
        else:
            if turn is None:
                turn = ["turn", 0]
                events.append(turn)
            turn[1] += dx
        last = events[-1] if events else None
        if last is not None and last[0] == "keys" and last[1] == keys:
            last[2] += span
            last[3] += span if shift else 0.0
        else:
            events.append(["keys", keys, span, span if shift else 0.0])
    moving = [e for e in events if e[0] == "keys" and e[1]]
    walked = sum(e[2] for e in moving)
    sprint = walked > 0 and sum(e[3] for e in moving) >= walked / 2
    kept = [e for e in events if (e[0] == "keys" and e[1]) or (e[0] == "turn" and abs(e[1]) >= min_turn)]
    out: list = []
    run: list[list] = []
    for event in kept:
        if event[0] == "turn":
            out += _fold(run, min_step)
            run = []
            if out and out[-1][0] == "turn":
                out[-1][1] += event[1]
            else:
                out.append(["turn", event[1]])
        else:
            run.append([event[1], event[2]])
    out += _fold(run, min_step)
    parts = []
    for first, second in out:
        if first == "turn":
            parts.append(f"turn {int(second)}")
        else:
            seconds = min(20.0, max(0.1, round(second, 1)))
            parts.append(f"{'+'.join(k for k in KEY_ORDER if k in first)} {seconds:g}")
    return ", ".join(parts), sprint


def held_keys() -> tuple[frozenset, bool]:
    return (frozenset(k for k, vk in WALK_VKS.items() if inp.is_pressed(vk)),
            inp.is_pressed(VK_SHIFT))


# --- raw mouse input (read only) ---------------------------------------------
class _RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class _RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class _RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", wintypes.USHORT), ("_pad", wintypes.USHORT),
                ("usButtonFlags", wintypes.USHORT), ("usButtonData", wintypes.USHORT),
                ("ulRawButtons", wintypes.ULONG), ("lLastX", wintypes.LONG), ("lLastY", wintypes.LONG),
                ("ulExtraInformation", wintypes.ULONG)]


class _RAWINPUT(ctypes.Structure):
    _fields_ = [("header", _RAWINPUTHEADER), ("mouse", _RAWMOUSE)]


class RawMouse:
    """The mouse's own horizontal movement, from a hidden message-only window
    in the calling thread (works while Roblox is in front and the cursor is
    locked). take() → counts moved since the last call."""
    WM_INPUT, PM_REMOVE, RID_INPUT, RIDEV_INPUTSINK, RIDEV_REMOVE = 0x00FF, 1, 0x10000003, 0x100, 0x1

    def __init__(self):
        self.hwnd = None

    def open(self) -> bool:
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.CreateWindowExW.restype = wintypes.HWND
            user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                               wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                               ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                               wintypes.HINSTANCE, wintypes.LPVOID]
            user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                               ctypes.POINTER(wintypes.UINT), wintypes.UINT]
            user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                                            wintypes.UINT, wintypes.UINT]
            self._user32 = user32
            self.hwnd = user32.CreateWindowExW(0, "Message", None, 0, 0, 0, 0, 0,
                                               wintypes.HWND(-3), None, None, None)
            if not self.hwnd:
                return False
            device = _RAWINPUTDEVICE(1, 2, self.RIDEV_INPUTSINK, self.hwnd)
            if not user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)):
                self.close()
                return False
            return True
        except (AttributeError, OSError):
            self.hwnd = None
            return False

    def take(self) -> int:
        if not self.hwnd:
            return 0
        user32, moved = self._user32, 0
        msg = wintypes.MSG()
        header = ctypes.sizeof(_RAWINPUTHEADER)
        while user32.PeekMessageW(ctypes.byref(msg), self.hwnd, self.WM_INPUT, self.WM_INPUT, self.PM_REMOVE):
            size = wintypes.UINT(0)
            handle = wintypes.HANDLE(msg.lParam)
            user32.GetRawInputData(handle, self.RID_INPUT, None, ctypes.byref(size), header)
            if not size.value or size.value > 256:
                continue
            buffer = ctypes.create_string_buffer(size.value)
            if user32.GetRawInputData(handle, self.RID_INPUT, buffer, ctypes.byref(size), header) <= 0:
                continue
            data = ctypes.cast(buffer, ctypes.POINTER(_RAWINPUT)).contents
            if data.header.dwType == 0 and not data.mouse.usFlags & 1:     # a mouse, relative move
                moved += data.mouse.lLastX
        return moved

    def close(self) -> None:
        if not self.hwnd:
            return
        try:
            device = _RAWINPUTDEVICE(1, 2, self.RIDEV_REMOVE, None)
            self._user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device))
            self._user32.DestroyWindow(self.hwnd)
        except OSError:
            pass
        self.hwnd = None


class WalkRecorder(QThread):
    """Reads the movement keys (and camera turns) while you walk; `done(route,
    sprint)` at the end. `turning()` → mouse counts moved, or None while the
    right button isn't held (default: raw input)."""
    status = Signal(str)
    done = Signal(str, bool)
    failed = Signal(str)

    def __init__(self, read=held_keys, clock=time.monotonic, turning=None, parent=None):
        super().__init__(parent)
        self._read, self._clock, self._turning = read, clock, turning

    def run(self) -> None:
        mouse = None
        turning = self._turning
        if turning is None:
            mouse = RawMouse()
            if mouse.open():
                turning = lambda: (lambda moved: moved if inp.is_pressed(VK_RBUTTON) else None)(mouse.take())
            else:
                turning = lambda: None
        try:
            self._record(turning)
        finally:
            if mouse is not None:
                mouse.close()

    def _record(self, turning) -> None:
        self.status.emit("Switch to Roblox and walk into the door (W/A/S/D, Shift to sprint, "
                         "right mouse button to turn)…")
        start = self._clock()
        keys, shift = self._read()
        while not keys:
            if self.isInterruptionRequested() or inp.is_pressed(VK_ESCAPE):
                self.failed.emit("Recording cancelled.")
                return
            if self._clock() - start > WAIT_FOR_FIRST:
                self.failed.emit(f"No walking in {WAIT_FOR_FIRST:.0f} s — recording stopped.")
                return
            turning()                          # a turn before walking isn't part of the way
            time.sleep(SAMPLE_EVERY)
            keys, shift = self._read()
        self.status.emit("Recording… let go of everything once you're in.")
        samples = [(self._clock(), keys, shift, turning())]
        idle_since = None
        while True:
            time.sleep(SAMPLE_EVERY)
            now = self._clock()
            keys, shift = self._read()
            moved = turning()
            samples.append((now, keys, shift, moved))
            if self.isInterruptionRequested():
                break
            if keys or moved is not None:
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
