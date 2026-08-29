"""Crisp vector icons rendered at runtime — no emoji glyphs, no asset
files. Each icon is an inline SVG painted into a pixmap at the needed
color, so state changes (idle/active) recolor cleanly on any platform."""

from __future__ import annotations

_MIC_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
<g fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round">
<rect x="9" y="3" width="6" height="11" rx="3" fill="{color}"/>
<path d="M5 11a7 7 0 0 0 14 0"/>
<line x1="12" y1="18" x2="12" y2="21"/>
<line x1="8.5" y1="21" x2="15.5" y2="21"/>
</g></svg>"""


def mic_icon(color: str, size: int = 20):
    """A microphone QIcon in the given color."""
    from PySide6.QtCore import QByteArray, QSize
    from PySide6.QtGui import QIcon, QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    svg = _MIC_SVG.format(color=color).encode()
    renderer = QSvgRenderer(QByteArray(svg))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill("transparent")
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
