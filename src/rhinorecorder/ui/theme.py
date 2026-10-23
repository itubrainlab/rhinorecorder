"""The look: g.Pype's own dark theme, plus the few rules Rhino Recorder's
own widgets need, and Rhino Recorder's icon: a rhino pretending to be a
unicorn.

g.Pype's frontend ships the theme every g.Pype application wears (Fusion,
a dark palette, and a style sheet), and the window identity (its icon,
and on Windows its taskbar ID). :func:`apply` uses both, so Rhino
Recorder looks like the g.Pype application it is.
"""
from __future__ import annotations

from pathlib import Path

APP_ICON = Path(__file__).resolve().parent.parent / "resources" / \
    "rhinorecorder.svg"

# The colours of g.Pype's dark palette (gpype.frontend.theme), named.
WINDOW = "#353535"
BASE = "#2a2a2a"
ALTERNATE = "#424242"
DARK = "#232323"
TEXT = "#ffffff"
MUTED = "#7f7f7f"
HIGHLIGHT = "#2a82da"

ICON = TEXT
ICON_ACTIVE = HIGHLIGHT
ICON_DISABLED = MUTED
RECORDING = "#e53935"
WARNING = "#ff9800"
CURSOR = HIGHLIGHT
GOOD = "#2ecc40"
BAD = "#ff4b2b"
UNKNOWN = MUTED

#: Rules for Rhino Recorder's own widgets, appended to g.Pype's sheet.
EXTRA = f"""
#Toolbar {{
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(25,25,25,255), stop:1 rgba(45,45,45,255));
    border-bottom: 1px solid rgba(0,0,0,200);
}}
#Toolbar QToolButton {{ border: none; padding: 4px; }}
#Toolbar QToolButton:hover {{ background: rgba(255,255,255,30); }}
#Toolbar QToolButton:checked {{ background: {HIGHLIGHT}; }}
#Toolbar QLabel {{ color: {MUTED}; }}
#Toolbar QLabel#Brand {{ color: {TEXT}; font-size: 15px; font-weight: 600; }}
#BrandSub {{ color: {MUTED}; font-size: 15px; }}
#Divider {{ background: rgba(255,255,255,40); }}
QPushButton#Primary {{
    background: {HIGHLIGHT}; border: 1px solid {HIGHLIGHT};
}}
QPushButton#Primary:hover {{ background: #0078cc; border-color: #0078cc; }}
QPushButton#Primary:disabled {{ background: {ALTERNATE};
    border-color: {ALTERNATE}; }}
QLabel#Note {{ color: {MUTED}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
"""


def apply(app) -> None:
    """Dress a QApplication as a g.Pype application."""
    from gpype.frontend import identity
    from gpype.frontend import theme as gpype_theme

    gpype_theme.apply(app, gpype_theme.DARK)
    app.setStyleSheet(app.styleSheet() + EXTRA)
    identity.apply(app, "Rhino Recorder", icon=APP_ICON)
