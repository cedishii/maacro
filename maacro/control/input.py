"""Clicks and key presses for Roblox (Windows only).

Roblox only reacts to real-looking input while its window is in front:
- the mouse has to *move* onto a button before a click registers, and
- keys are sent as hardware scan codes, not characters.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0002, 0x0008
ULONG_PTR = ctypes.c_size_t

# Hardware scan codes for the keys the macro uses.
SCAN_CODES = {
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07,
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "i": 0x17, "o": 0x18, "a": 0x1E, "s": 0x1F,
    "d": 0x20, "f": 0x21, "x": 0x2D, "esc": 0x01, "enter": 0x1C, "shift": 0x2A, "space": 0x39,
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
_user32.SendInput.restype = wintypes.UINT
_user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short


def _send(*inputs: INPUT) -> None:
    array = (INPUT * len(inputs))(*inputs)
    _user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))


def _mouse(flags: int, dx: int = 0, dy: int = 0) -> INPUT:
    return INPUT(type=INPUT_MOUSE, u=_INPUTUNION(mi=MOUSEINPUT(dx, dy, 0, flags, 0, 0)))


def _key(scan: int, up: bool) -> INPUT:
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(0, scan, flags, 0, 0)))


# --- window ----------------------------------------------------------------
def focus(hwnd: int) -> None:
    """Bring Roblox to the front (needed for it to accept input)."""
    if _user32.GetForegroundWindow() == hwnd:
        return
    # Windows only lets the active app change the foreground window; tapping
    # Alt first is the usual way to be allowed.
    _send(INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(0x12, 0, 0, 0, 0))),
          INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(0x12, 0, KEYEVENTF_KEYUP, 0, 0))))
    _user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)


def client_to_screen(hwnd: int, x: float, y: float) -> tuple[int, int]:
    point = wintypes.POINT(int(x), int(y))
    _user32.ClientToScreen(hwnd, ctypes.byref(point))
    return point.x, point.y


# --- mouse -----------------------------------------------------------------
def move_to(hwnd: int, x: float, y: float) -> None:
    """Move the mouse to (x, y) inside the Roblox window, with a small wiggle
    so Roblox notices the mouse is over the button."""
    sx, sy = client_to_screen(hwnd, x, y)
    _user32.SetCursorPos(sx, sy)
    time.sleep(0.03)
    _send(_mouse(MOUSEEVENTF_MOVE, 1, 0))
    time.sleep(0.03)
    _send(_mouse(MOUSEEVENTF_MOVE, -1, 0))
    time.sleep(0.05)


def click(hwnd: int, x: float, y: float) -> None:
    """Left-click at (x, y) inside the Roblox window."""
    focus(hwnd)
    move_to(hwnd, x, y)
    _send(_mouse(MOUSEEVENTF_LEFTDOWN))
    time.sleep(0.06)
    _send(_mouse(MOUSEEVENTF_LEFTUP))
    time.sleep(0.05)


# --- keyboard --------------------------------------------------------------
def key_down(name: str) -> None:
    _send(_key(SCAN_CODES[name], up=False))


def key_up(name: str) -> None:
    _send(_key(SCAN_CODES[name], up=True))


def press(hwnd: int, name: str, hold: float = 0.06) -> None:
    focus(hwnd)
    key_down(name)
    time.sleep(hold)
    key_up(name)


def release_all() -> None:
    """Let go of every key the macro might be holding (used when stopping)."""
    _send(*(_key(scan, up=True) for scan in SCAN_CODES.values()))


def is_pressed(vk: int) -> bool:
    """True if a key is held down right now (works even when MAACRO isn't in front)."""
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


VK_F1, VK_F3 = 0x70, 0x72
