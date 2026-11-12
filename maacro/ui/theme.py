"""MAACRO colors and the Qt stylesheet."""

BG = "#0e1016"
PANEL = "#161922"
CARD = "#1c202b"
BORDER = "#272c3a"
TEXT = "#e6e8ef"
MUTED = "#8a90a2"
ACCENT = "#8b5cf6"
WIN = "#4ade80"
LOSS = "#f87171"
WARN = "#fbbf24"

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI";
    font-size: 10pt;
}}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; }}

/* Sidebar */
#Sidebar {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
#Brand {{ color: {ACCENT}; font-size: 10.5pt; font-weight: 800; padding: 14px 0 10px 0; }}
#NavButton {{
    background: transparent; border: 1px solid transparent; border-radius: 8px;
    color: {MUTED}; padding: 8px 4px; font-size: 8.5pt;
}}
#NavButton:hover {{ background: {CARD}; color: {TEXT}; }}
#NavButton:checked {{ background: {CARD}; color: {TEXT}; border-color: {ACCENT}; }}

/* Panels and cards */
#Panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
#Panel QLabel, #Card QLabel {{ background: transparent; }}
#PanelTitle {{ font-size: 11pt; font-weight: 600; }}
#PageTitle {{ font-size: 15pt; font-weight: 700; }}
#Muted {{ color: {MUTED}; }}
#BigWin {{ color: {WIN}; font-size: 20pt; font-weight: 600; }}
#BigLoss {{ color: {LOSS}; font-size: 20pt; font-weight: 600; }}
#Value {{ font-weight: 600; }}

/* Live view */
#LiveView {{ background: #07080c; border: 1px solid {BORDER}; border-radius: 10px; }}

/* Inputs */
QPushButton {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 12px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; }}
#StartButton {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600; }}
#StartButton:disabled {{ background: {CARD}; border-color: {BORDER}; color: {MUTED}; }}
QLineEdit, QComboBox {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px;
}}
QComboBox QAbstractItemView {{ background: {CARD}; selection-background-color: {ACCENT}; }}
QPlainTextEdit {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px;
    font-family: "Consolas"; font-size: 9pt;
}}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 20px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""
