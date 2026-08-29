"""RITA's look: one modern dark theme, applied as QSS.

Design intent: a clean native app — generous spacing, one accent color,
soft radii, quiet chrome. Not a terminal, not a web page.
"""

from __future__ import annotations

ACCENT = "#4F8CC9"          # calm blue
ACCENT_HOVER = "#63A0DD"
BG = "#16181D"              # window
BG_RAISED = "#1E2128"       # panels / cards
BG_INPUT = "#262A33"
BORDER = "#2E333D"
TEXT = "#E6E8EC"
TEXT_DIM = "#9AA1AC"
GOOD = "#57B98A"
WARN = "#D9A03F"
BAD = "#D96B6B"
MONO = "Cascadia Code, Consolas, 'JetBrains Mono', monospace"

QSS = f"""
* {{
    font-family: 'Segoe UI', 'SF Pro Text', 'Cantarell', sans-serif;
    font-size: 14px;
    color: {TEXT};
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#sidebar {{
    background: {BG_RAISED};
    border-right: 1px solid {BORDER};
}}
QPushButton#navButton {{
    background: transparent; border: none; border-radius: 8px;
    padding: 10px 16px; text-align: left; color: {TEXT_DIM};
}}
QPushButton#navButton:hover {{ background: {BG_INPUT}; color: {TEXT}; }}
QPushButton#navButton:checked {{
    background: {BG_INPUT}; color: {TEXT};
    border-left: 3px solid {ACCENT};
}}
QLabel#title {{ font-size: 20px; font-weight: 600; }}
QLabel#dim {{ color: {TEXT_DIM}; }}
QFrame#card {{
    background: {BG_RAISED}; border: 1px solid {BORDER}; border-radius: 10px;
}}
QLineEdit, QSpinBox {{
    background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 9px 12px; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QPushButton {{
    background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 9px 16px;
}}
QPushButton:hover {{ background: #2E3440; border-color: {ACCENT}; }}
QPushButton:pressed {{
    background: #101319; border-color: {ACCENT};
    padding-top: 11px; padding-bottom: 7px;
}}
QPushButton#primary {{
    background: {ACCENT}; border: 1px solid {ACCENT}; color: white;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:pressed {{ background: #3D74AC; }}
QPushButton#pause {{ background: {WARN}; border: 1px solid {WARN};
    color: #1b1b1b; font-weight: 600; }}
QPushButton#pause:pressed {{ background: #B58432; }}
QPushButton#stop {{ background: {BAD}; border: 1px solid {BAD};
    color: white; font-weight: 600; }}
QPushButton#stop:pressed {{ background: #B85555; }}
QPushButton:disabled {{
    color: {TEXT_DIM}; background: {BG_RAISED}; border-color: {BORDER};
}}
QTextEdit, QPlainTextEdit, QListWidget {{
    background: {BG_RAISED}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 8px;
}}
QPlainTextEdit#screenPane {{
    font-family: {MONO}; font-size: 13px; background: #12141A;
}}
QStatusBar {{ background: {BG_RAISED}; border-top: 1px solid {BORDER}; color: {TEXT_DIM}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QSplitter::handle {{ background: {BORDER}; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid {BORDER}; background: {BG_INPUT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
"""
