"""Find the Roblox window and take pictures of it (Windows only).

While Roblox is the window in front, its part of the screen is copied
(BitBlt from the screen): cheap, it's what is already on screen. Otherwise
PrintWindow is used, which can capture the game behind other windows but
makes Windows render the game window again for every picture (heavy on a
DirectX game: it was making Roblox stutter). Neither works on a minimized
window.
"""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

ROBLOX_TITLE = "Roblox"

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

# Declare handle types so 64-bit handles are not cut to 32 bits.
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND
_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.IsWindow.restype = wintypes.BOOL
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsIconic.restype = wintypes.BOOL
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetClientRect.restype = wintypes.BOOL
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int
_user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
_user32.PrintWindow.restype = wintypes.BOOL
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.ClientToScreen.restype = wintypes.BOOL
_gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                          wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
_gdi32.BitBlt.restype = wintypes.BOOL
SRCCOPY = 0x00CC0020

_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteObject.restype = wintypes.BOOL
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_gdi32.DeleteDC.restype = wintypes.BOOL

PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2  # needed for DirectX games like Roblox
DIB_RGB_COLORS = 0
BI_RGB = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


_gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
]
_gdi32.GetDIBits.restype = ctypes.c_int


def find_roblox_window() -> int | None:
    """Return the Roblox window handle, or None if Roblox is not open."""
    hwnd = _user32.FindWindowW(None, ROBLOX_TITLE)
    return hwnd or None


def capture_window(hwnd: int, from_screen: bool = False) -> np.ndarray | None:
    """Picture of the inside of a window as a BGRA array (height, width, 4).
    from_screen: copy it from the screen (only right while it's in front)."""
    if not _user32.IsWindow(hwnd) or _user32.IsIconic(hwnd):
        return None
    rect = wintypes.RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    origin = wintypes.POINT(0, 0)
    if from_screen and not _user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None

    source = None if from_screen else hwnd      # None = the whole screen
    window_dc = _user32.GetDC(source)
    if not window_dc:
        return None
    memory_dc = _gdi32.CreateCompatibleDC(window_dc)
    bitmap = _gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = _gdi32.SelectObject(memory_dc, bitmap)
    try:
        if from_screen:
            if not _gdi32.BitBlt(memory_dc, 0, 0, width, height, window_dc, origin.x, origin.y, SRCCOPY):
                return None
        elif not _user32.PrintWindow(hwnd, memory_dc, PW_CLIENTONLY | PW_RENDERFULLCONTENT):
            return None
        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = width
        header.biHeight = -height  # negative = rows go top to bottom
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = BI_RGB
        # Straight into the array: one copy of the picture, not two.
        frame = np.empty((height, width, 4), dtype=np.uint8)
        rows = _gdi32.GetDIBits(memory_dc, bitmap, 0, height, frame.ctypes.data,
                                ctypes.byref(header), DIB_RGB_COLORS)
        if rows != height:
            return None
        return frame
    finally:
        _gdi32.SelectObject(memory_dc, previous)
        _gdi32.DeleteObject(bitmap)
        _gdi32.DeleteDC(memory_dc)
        _user32.ReleaseDC(source, window_dc)


PREVIEW_EVERY = 0.25   # seconds between live-view pictures (4 a second)
IDLE_INTERVAL_MS = 1000  # one picture a second while nothing needs more (macro stopped)


class CaptureThread(QThread):
    """Captures the Roblox window several times a second in the background."""

    frame_ready = Signal(QImage)
    status_changed = Signal(str)  # "found", "minimized", "missing"

    def __init__(self, fps: int = 10, parent=None):
        super().__init__(parent)
        self.interval_ms = max(1, 1000 // fps)
        self._status = ""
        self.hwnd: int | None = None
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_id = 0
        self._frame_time = 0.0
        self._preview_at = 0.0
        self._screen_copy_ok = True     # False once a screen copy came back black
        # Set by the window: build live-view pictures only while one is on
        # screen, and slow right down while the macro isn't running.
        self.preview_wanted = True
        self.idle = False

    def latest_frame(self) -> tuple[int, np.ndarray | None]:
        """The newest BGRA frame and a number that changes with every new frame."""
        with self._lock:
            return self._frame_id, self._frame

    def latest_frame_info(self) -> tuple[int, np.ndarray | None, float]:
        """Like latest_frame, plus when it was captured (time.monotonic)."""
        with self._lock:
            return self._frame_id, self._frame, self._frame_time

    def latest_qimage(self) -> QImage | None:
        """The newest frame as a picture (e.g. for a Discord drop post)."""
        _, frame = self.latest_frame()
        if frame is None:
            return None
        height, width = frame.shape[:2]
        return QImage(frame.data, width, height, width * 4, QImage.Format.Format_RGB32).copy()

    def _set_status(self, status: str) -> None:
        if status != self._status:
            self._status = status
            self.status_changed.emit(status)

    def run(self) -> None:
        hwnd = None
        while not self.isInterruptionRequested():
            try:
                hwnd = self._step(hwnd)
            except Exception:
                # A capture can fail while Roblox is closing or resizing:
                # look for the window again instead of ending the thread.
                hwnd = None
                self.msleep(1000)

    def _step(self, hwnd):
        """One capture: find the window, grab a frame. Returns the window."""
        if not hwnd or not _user32.IsWindow(hwnd):
            hwnd = find_roblox_window()
        self.hwnd = hwnd
        if not hwnd:
            self._set_status("missing")
        elif _user32.IsIconic(hwnd):
            self._set_status("minimized")
        else:
            started = time.monotonic()
            frame = None
            if self._screen_copy_ok and _user32.GetForegroundWindow() == hwnd:
                frame = capture_window(hwnd, from_screen=True)
                if frame is not None and frame[::24, ::24, :3].max() < 8:
                    self._screen_copy_ok = False    # black: this PC can't copy it that way
                    frame = None
            if frame is None:
                frame = capture_window(hwnd)
            if frame is not None:
                with self._lock:
                    self._frame = frame
                    self._frame_id += 1
                    self._frame_time = started
                self._set_status("found")
                # The on-screen preview only needs a few pictures a second:
                # building and drawing each one costs CPU the game could use.
                if not self.preview_wanted or started - self._preview_at < PREVIEW_EVERY:
                    self.msleep(self._interval())
                    return hwnd
                self._preview_at = started
                height, width = frame.shape[:2]
                # BGRA bytes are what QImage calls RGB32.
                image = QImage(frame.data, width, height, width * 4,
                               QImage.Format.Format_RGB32).copy()
                self.frame_ready.emit(image)
        self.msleep(self._interval() if hwnd else 1000)
        return hwnd

    def _interval(self) -> int:
        return IDLE_INTERVAL_MS if self.idle else self.interval_ms
