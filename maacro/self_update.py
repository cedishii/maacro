"""Noticing that MAACRO's own files were updated while it's open.

Python loads the code once, when MAACRO opens: stopping and starting (F3 /
F1) keeps running the old version. When the files on disk are newer than
what was loaded, MAACRO says so on Start and offers to restart itself.

The new copy is started with `--wait-for <pid>` and waits for this one to
close first (only one MAACRO may run at a time).
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def newest_code_time(root: Path = ROOT) -> float:
    """The newest modification time of MAACRO's code files."""
    newest = 0.0
    for path in [root / "main.py", *(root / "maacro").rglob("*.py")]:
        try:
            newest = max(newest, path.stat().st_mtime)
        except OSError:
            pass
    return newest


LOADED_AT = newest_code_time()


def code_changed(root: Path = ROOT, loaded_at: float | None = None) -> bool:
    """True when a code file is newer than the code that's running."""
    loaded = LOADED_AT if loaded_at is None else loaded_at
    return newest_code_time(root) > loaded + 1.0


def restart_command() -> tuple[str, list[str]]:
    """(program, arguments) that start a new MAACRO once this one has closed."""
    return sys.executable, [str(ROOT / "main.py"), "--wait-for", str(os.getpid())]


def wait_for_exit(pid: int, timeout_s: float = 20.0) -> None:
    """Block until process `pid` has exited (or timeout_s passed)."""
    SYNCHRONIZE = 0x00100000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        return                      # already gone
    try:
        kernel32.WaitForSingleObject(ctypes.c_void_p(handle), int(timeout_s * 1000))
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
