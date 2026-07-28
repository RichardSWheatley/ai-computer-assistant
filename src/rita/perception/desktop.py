"""Real desktop perception: accessibility tree (+ screenshot) -> ScreenState.

Cheap-first policy (docs/PERFORMANCE.md): read the accessibility tree first
(instant, no model); capture pixels for the record but only lean on vision/OCR
when the tree is empty (vision/OCR is a future plug-in point here).

`fuse()` is pure and unit-tested; the OS-specific capture/a11y are injected so
the perception object is testable with fakes.
"""

from __future__ import annotations

from ..core.interfaces import Element, Perception, ScreenState
from ..security.injection import neutralize
from .a11y import A11yBackend, get_a11y_backend
from .capture import capture_screen


def fuse(a11y: list[Element], ocr: list[Element] | None = None) -> list[Element]:
    """Merge a11y + OCR elements, deduping by (label, rough position).

    Element labels are untrusted input, so invisible/bidi characters used to
    hide injected instructions are stripped at ingestion.
    """
    out: list[Element] = []
    seen: set[tuple[str, int, int]] = set()
    for e in list(a11y) + list(ocr or []):
        e = Element(label=neutralize(e.label), role=e.role, x=e.x, y=e.y, source=e.source)
        key = (e.label.strip().lower(), e.x // 20, e.y // 20)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


class DesktopPerception(Perception):
    def __init__(self, a11y: A11yBackend | None = None, capture=capture_screen,
                 ocr=None) -> None:
        self.a11y = a11y or get_a11y_backend()
        self._capture = capture
        self._ocr = ocr  # optional callable(path) -> list[Element]

    def observe(self) -> ScreenState:
        shot = self._capture() if self._capture else None
        path = shot[0] if shot else None

        elements = self.a11y.elements()
        if not elements and self._ocr and path:
            elements = self._ocr(path)  # fall back to vision/OCR only when needed

        elements = fuse(elements, None)
        summary = (f"{len(elements)} elements"
                   + (f", {shot[1][0]}x{shot[1][1]} screen" if shot else "")) \
            if elements or shot else "desktop (no capture/a11y backend available)"
        return ScreenState(summary=summary, elements=elements, screenshot_path=path)

    def locate(self, label: str) -> tuple[int, int] | None:
        """Resolve a label to click coordinates via the accessibility tree."""
        el = self.a11y.find(label)
        return (el.x, el.y) if el else None
