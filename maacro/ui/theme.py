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
    /* The sidebar symbols are in Segoe UI Symbol: naming it saves Windows a
       ~300 ms search through the fonts on the first draw. */
    font-family: "Segoe UI Symbol";
    background: transparent; border: 1px solid transparent; border-radius: 8px;
    color: {MUTED}; padding: 8px 4px; font-size: 8.5pt;
}}
#NavButton:hover {{ background: {CARD}; color: {TEXT}; }}
#NavButton:checked {{ background: {CARD}; color: {TEXT}; border-color: {ACCENT}; }}

/* Panels and cards */
#Panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
#Panel QLabel, #Card QLabel, #Panel QCheckBox {{ background: transparent; }}
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
QLineEdit, QComboBox, QSpinBox {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px;
}}
#Card QLineEdit, #Card QSpinBox {{ background: {PANEL}; }}
QSpinBox:disabled, QLineEdit:disabled {{ color: {MUTED}; }}
#Card QCheckBox {{ background: transparent; }}

/* Radio buttons (pick-one settings): a ring, filled with the accent when chosen */
QRadioButton {{ background: transparent; spacing: 8px; }}
QRadioButton::indicator {{
    width: 12px; height: 12px; border-radius: 7px;
    border: 1px solid {MUTED}; background: transparent;
}}
QRadioButton::indicator:checked {{ border: 1px solid {ACCENT}; background: {ACCENT}; }}
QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}

/* Check boxes: a rounded square, filled with the accent when ticked */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 13px; height: 13px; border-radius: 3px;
    border: 1px solid {MUTED}; background: transparent;
}}
QCheckBox::indicator:checked {{ border: 1px solid {ACCENT}; background: {ACCENT}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:disabled {{ border-color: {BORDER}; }}
QCheckBox::indicator:checked:disabled {{ background: {BORDER}; }}

/* Mode tabs */
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: {CARD}; color: {MUTED}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 6px 16px; margin-right: 6px;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-color: {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QComboBox QAbstractItemView {{ background: {CARD}; selection-background-color: {ACCENT}; }}
QPlainTextEdit {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px;
    font-family: "Consolas"; font-size: 9pt;
}}
/* Tables (Stats page) */
QTableWidget {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px;
    gridline-color: {BORDER}; alternate-background-color: {PANEL};
}}
QHeaderView::section {{
    background: {PANEL}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 4px 8px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {PANEL}; border: none; }}
#StatValue {{ font-size: 16pt; font-weight: 700; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 20px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 20px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""
