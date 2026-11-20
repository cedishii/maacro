"""Reading the real keyboard and mouse (Windows raw input) — read only.

A hidden message-only window in the calling thread registers for raw input
with RIDEV_INPUTSINK, so input arrives while Roblox is in front, and the
mouse's own movement still comes through while Roblox locks the cursor (when
you turn the camera). Only physical devices count: input sent by a program
(SendInput, MAACRO's own clicks) has no device, so it's left out.

events() → what happened since the last call, oldest first:
    ("key", scan, extended, down)      scan code as sent back by input.scan_key
    ("button", "left" / "right", down)
    ("wheel", delta)                   +120 = one notch away from you
    ("move", dx, dy)                   mouse counts (relative)
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes


class _RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class _RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class _RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", wintypes.USHORT), ("_pad", wintypes.USHORT),
                ("usButtonFlags", wintypes.USHORT), ("usButtonData", ctypes.c_short),
                ("ulRawButtons", wintypes.ULONG), ("lLastX", wintypes.LONG), ("lLastY", wintypes.LONG),
                ("ulExtraInformation", wintypes.ULONG)]


class _RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", wintypes.USHORT), ("Flags", wintypes.USHORT), ("Reserved", wintypes.USHORT),
                ("VKey", wintypes.USHORT), ("Message", wintypes.UINT), ("ExtraInformation", wintypes.ULONG)]


class _RAWDATA(ctypes.Union):
    _fields_ = [("mouse", _RAWMOUSE), ("keyboard", _RAWKEYBOARD)]


class _RAWINPUT(ctypes.Structure):
    _fields_ = [("header", _RAWINPUTHEADER), ("data", _RAWDATA)]


WM_INPUT, PM_REMOVE, RID_INPUT = 0x00FF, 1, 0x10000003
RIDEV_INPUTSINK, RIDEV_REMOVE = 0x100, 0x1
RIM_TYPEMOUSE, RIM_TYPEKEYBOARD = 0, 1
MOUSE = (1, 2)
KEYBOARD = (1, 6)
_BUTTONS = ((0x0001, "left", True), (0x0002, "left", False), (0x0004, "right", True), (0x0008, "right", False))
RI_MOUSE_WHEEL = 0x0400


def parse(kind: int, device: int, mouse=None, keyboard=None) -> list[tuple]:
    """One raw input record → events (empty for programs' input)."""
    if not device:
        return []
    out: list[tuple] = []
    if kind == RIM_TYPEKEYBOARD and keyboard is not None:
        if keyboard.VKey == 0xFF or not keyboard.MakeCode:
            return []
        out.append(("key", int(keyboard.MakeCode), bool(keyboard.Flags & 2), not keyboard.Flags & 1))
    elif kind == RIM_TYPEMOUSE and mouse is not None:
        if not mouse.usFlags & 1 and (mouse.lLastX or mouse.lLastY):
            out.append(("move", int(mouse.lLastX), int(mouse.lLastY)))
        for flag, button, down in _BUTTONS:
            if mouse.usButtonFlags & flag:
                out.append(("button", button, down))
        if mouse.usButtonFlags & RI_MOUSE_WHEEL:
            out.append(("wheel", int(mouse.usButtonData)))
    return out


class RawInput:
    def __init__(self, devices=(MOUSE, KEYBOARD)):
        self.devices = devices
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
            array = (_RAWINPUTDEVICE * len(self.devices))(
                *(_RAWINPUTDEVICE(page, usage, RIDEV_INPUTSINK, self.hwnd) for page, usage in self.devices))
            if not user32.RegisterRawInputDevices(array, len(self.devices), ctypes.sizeof(_RAWINPUTDEVICE)):
                self.close()
                return False
            return True
        except (AttributeError, OSError):
            self.hwnd = None
            return False

    def events(self) -> list[tuple]:
        if not self.hwnd:
            return []
        user32, out = self._user32, []
        msg = wintypes.MSG()
        header = ctypes.sizeof(_RAWINPUTHEADER)
        while user32.PeekMessageW(ctypes.byref(msg), self.hwnd, WM_INPUT, WM_INPUT, PM_REMOVE):
            size = wintypes.UINT(0)
            handle = wintypes.HANDLE(msg.lParam)
            user32.GetRawInputData(handle, RID_INPUT, None, ctypes.byref(size), header)
            if not size.value or size.value > 256:
                continue
            buffer = ctypes.create_string_buffer(max(size.value, ctypes.sizeof(_RAWINPUT)))
            if user32.GetRawInputData(handle, RID_INPUT, buffer, ctypes.byref(size), header) <= 0:
                continue
            raw = ctypes.cast(buffer, ctypes.POINTER(_RAWINPUT)).contents
            out += parse(raw.header.dwType, raw.header.hDevice or 0, raw.data.mouse, raw.data.keyboard)
        return out

    def close(self) -> None:
        if not self.hwnd:
            return
        try:
            array = (_RAWINPUTDEVICE * len(self.devices))(
                *(_RAWINPUTDEVICE(page, usage, RIDEV_REMOVE, None) for page, usage in self.devices))
            self._user32.RegisterRawInputDevices(array, len(self.devices), ctypes.sizeof(_RAWINPUTDEVICE))
            self._user32.DestroyWindow(self.hwnd)
        except OSError:
            pass
        self.hwnd = None
