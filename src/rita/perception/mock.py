"""Mock perception for headless runs and tests."""

from __future__ import annotations

from ..core.interfaces import Element, Perception, ScreenState


class MockPerception(Perception):
    def __init__(self) -> None:
        self._tick = 0

    def observe(self) -> ScreenState:
        self._tick += 1
        return ScreenState(
            summary=f"mock desktop (frame {self._tick})",
            elements=[
                Element(label="Start", role="button", x=10, y=1060),
                Element(label="Search", role="textbox", x=120, y=1060),
            ],
        )
