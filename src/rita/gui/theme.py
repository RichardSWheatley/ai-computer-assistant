"""RITA's look: one modern dark theme, applied as QSS.

Design intent: a current-generation tool, not a default-palette Qt
form. Deep layered background, one electric accent (blue→violet
gradient reserved for the primary action), buttons with real depth
(hover lift, pressed sink), pill navigation, underline tabs, focus
rings on inputs. Everything derives from the tokens below.
"""

from __future__ import annotations

# Palette tokens — every color in the app comes from here.
ACCENT = "#5B8DEF"          # electric blue
ACCENT_2 = "#7C6AF0"        # violet — gradient partner, never used alone
ACCENT_HOVER = "#6E9BF4"
ACCENT_SOFT = "rgba(91, 141, 239, 0.16)"   # tinted fills (nav, selection)
BG = "#0F1115"              # window — near-black with a blue cast
BG_RAISED = "#151922"       # panels / cards
BG_INPUT = "#1C222D"        # inputs / buttons at rest
BG_HOVER = "#242B38"        # anything under the pointer
BG_PRESSED = "#0C0F14"      # pressed sink
BORDER = "#252C39"
BORDER_STRONG = "#39424F"
TEXT = "#EDEFF3"
TEXT_DIM = "#8A93A3"
GOOD = "#4FC38A"
WARN = "#D9A03F"
BAD = "#E06C6C"
MONO = "Cascadia Code, Consolas, 'JetBrains Mono', monospace"

_PRIMARY_GRAD = (f"qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                 f"stop:0 {ACCENT}, stop:1 {ACCENT_2})")
_PRIMARY_GRAD_HOVER = (f"qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                       f"stop:0 {ACCENT_HOVER}, stop:1 #8D7BF6)")
_PRIMARY_GRAD_PRESSED = (f"qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                         f"stop:0 #4A76CC, stop:1 #6656CE)")

QSS = f"""
* {{
    font-family: 'Segoe UI Variable', 'Segoe UI', 'SF Pro Text',
                 'Cantarell', sans-serif;
    font-size: 14px;
    color: {TEXT};
}}
QMainWindow, QDialog {{ background: {BG}; }}

/* ---- sidebar: brand + pill navigation --------------------------------- */
QWidget#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #12151C, stop:1 {BG});
    border-right: 1px solid {BORDER};
}}
QLabel#title {{
    font-size: 22px; font-weight: 700; letter-spacing: 2px;
    color: {TEXT};
}}
QLabel#dim {{ color: {TEXT_DIM}; }}
QPushButton#navButton {{
    background: transparent; border: 1px solid transparent;
    border-radius: 10px; padding: 10px 16px; text-align: left;
    color: {TEXT_DIM}; font-weight: 500;
}}
QPushButton#navButton:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
QPushButton#navButton:checked {{
    background: {ACCENT_SOFT}; color: {TEXT};
    border: 1px solid rgba(91, 141, 239, 0.35);
}}

/* ---- surfaces ---------------------------------------------------------- */
QFrame#card {{
    background: {BG_RAISED}; border: 1px solid {BORDER};
    border-radius: 12px;
}}
QTextEdit, QPlainTextEdit, QListWidget {{
    background: {BG_RAISED}; border: 1px solid {BORDER};
    border-radius: 12px; padding: 10px;
    selection-background-color: {ACCENT};
}}
QPlainTextEdit#screenPane {{
    font-family: {MONO}; font-size: 13px; background: #0B0E13;
    border: 1px solid {BORDER};
}}

/* ---- inputs: focus ring ------------------------------------------------ */
QLineEdit, QSpinBox, QComboBox {{
    background: {BG_INPUT}; border: 1px solid {BORDER};
    border-radius: 9px; padding: 9px 12px;
    selection-background-color: {ACCENT};
}}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{
    border-color: {BORDER_STRONG};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT}; background: #202734;
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {BG_RAISED}; border: 1px solid {BORDER_STRONG};
    border-radius: 8px; selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT}; outline: none;
}}

/* ---- buttons: rest / hover lift / pressed sink ------------------------- */
QPushButton {{
    background: {BG_INPUT}; border: 1px solid {BORDER_STRONG};
    border-radius: 9px; padding: 9px 18px; font-weight: 500;
    min-height: 16px;
}}
QPushButton:hover {{
    background: {BG_HOVER}; border-color: {ACCENT};
    color: white;
}}
QPushButton:pressed {{
    background: {BG_PRESSED}; border-color: {ACCENT};
    padding-top: 11px; padding-bottom: 7px;
}}
QPushButton:disabled {{
    color: {TEXT_DIM}; background: {BG_RAISED}; border-color: {BORDER};
}}
QPushButton#primary {{
    background: {_PRIMARY_GRAD}; border: none; color: white;
    font-weight: 600; padding: 10px 20px;
}}
QPushButton#primary:hover {{ background: {_PRIMARY_GRAD_HOVER}; }}
QPushButton#primary:pressed {{
    background: {_PRIMARY_GRAD_PRESSED};
    padding-top: 12px; padding-bottom: 8px;
}}
QPushButton#pause {{
    background: {WARN}; border: none; color: #17130A; font-weight: 600;
}}
QPushButton#pause:hover {{ background: #E3AF54; }}
QPushButton#pause:pressed {{ background: #B58432; }}
QPushButton#stop {{
    background: {BAD}; border: none; color: white; font-weight: 600;
}}
QPushButton#stop:hover {{ background: #E88080; }}
QPushButton#stop:pressed {{ background: #BC5252; }}
QPushButton#pickButton {{
    padding: 8px 10px; min-width: 18px;
}}
QPushButton#pickButton:pressed {{
    padding-top: 9px; padding-bottom: 7px;
}}
QPushButton#micButton {{
    padding: 9px 14px; font-weight: 500;
}}
QPushButton#micButton:checked {{
    background: {_PRIMARY_GRAD}; border: 1px solid {ACCENT};
    color: white; font-weight: 600;
}}
QToolButton {{
    background: {BG_INPUT}; border: 1px solid {BORDER_STRONG};
    border-radius: 9px; padding: 7px 14px; color: {TEXT};
    font-weight: 500;
}}
QToolButton:hover {{ background: {BG_HOVER}; border-color: {ACCENT}; }}
QToolButton:pressed {{ background: {BG_PRESSED}; }}

/* ---- chat tabs: underline style, no boxes ------------------------------ */
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_DIM};
    border: none; border-bottom: 2px solid transparent;
    padding: 9px 20px; margin-right: 6px; font-weight: 500;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{
    color: {TEXT}; border-bottom: 2px solid {ACCENT};
}}

/* ---- chrome ------------------------------------------------------------ */
QStatusBar {{
    background: {BG_RAISED}; border-top: 1px solid {BORDER};
    color: {TEXT_DIM};
}}
QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG}; border-radius: 4px; min-width: 30px;
}}
QSplitter::handle {{ background: {BORDER}; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 6px;
    border: 1px solid {BORDER_STRONG}; background: {BG_INPUT};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {_PRIMARY_GRAD}; border-color: {ACCENT};
}}
"""
