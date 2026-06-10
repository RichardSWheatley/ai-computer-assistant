"""Real desktop perception: screenshot + accessibility tree + OCR fusion.

Cheap-first policy (see docs/PERFORMANCE.md): read the accessibility tree first
(instant, no model), fall back to vision/OCR only when the UI isn't accessible.
Heavy deps are imported lazily so this module loads on any platform.
"""

from __future__ import annotations

from ..core.interfaces import Element, Perception, ScreenState


class DesktopPerception(Perception):
    """Skeleton. Wire up `mss` (capture), UI Automation (a11y), and OCR here."""

    def __init__(self, screenshot_dir: str = ".aica/screens") -> None:
        self.screenshot_dir = screenshot_dir

    def _capture(self) -> str | None:
        try:  # pragma: no cover - needs a display + optional deps
            import os
            import mss  # type: ignore
            os.makedirs(self.screenshot_dir, exist_ok=True)
            path = os.path.join(self.screenshot_dir, "frame.png")
            with mss.mss() as sct:
                sct.shot(output=path)
            return path
        except Exception:
            return None

    def _a11y_elements(self) -> list[Element]:  # pragma: no cover
        # TODO: Windows UI Automation via pywinauto/uiautomation.
        return []

    def observe(self) -> ScreenState:
        path = self._capture()
        elements = self._a11y_elements()
        summary = "desktop" if path else "desktop (no capture backend installed)"
        return ScreenState(summary=summary, elements=elements, screenshot_path=path)
