"""MAACRO - start the app."""
import ctypes
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from maacro import __version__
from maacro.ui.main_window import MainWindow
from maacro.ui.theme import STYLESHEET

ICON = Path(__file__).resolve().parent / "maacro" / "assets" / "maacro.ico"


def already_running() -> bool:
    """True if another MAACRO is open (then it's brought to the front).

    Two copies would both click: one picks a card, the other un-picks it.
    """
    # use_last_error: ctypes.windll's GetLastError can be overwritten before we read it.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    main.mutex = kernel32.CreateMutexW(None, False, "MAACRO.SingleInstance")   # kept open while running
    if ctypes.get_last_error() != 183:   # ERROR_ALREADY_EXISTS
        return False
    user32.FindWindowW.restype = ctypes.c_void_p
    hwnd = user32.FindWindowW(None, f"MAACRO v{__version__}")
    if hwnd:
        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)          # SW_RESTORE
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    return True


def main() -> int:
    if already_running():
        return 0
    # Show MAACRO's own icon on the taskbar instead of Python's.
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MAACRO.App")
    except (AttributeError, OSError):
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("MAACRO")
    app.setWindowIcon(QIcon(str(ICON)))
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
