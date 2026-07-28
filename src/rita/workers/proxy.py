"""Python-side adapters that make a native worker satisfy the core interfaces.

These implement `Perception` and the input surface by delegating over RPC. The
orchestrator can't tell whether the eyes/hands are Python or Rust — that's the
whole point of the boundary.
"""

from __future__ import annotations

from ..core.interfaces import Element, Perception, ScreenState, ToolResult
from . import protocol as P
from .client import WorkerClient


class WorkerPerception(Perception):
    def __init__(self, client: WorkerClient) -> None:
        self.client = client

    def observe(self) -> ScreenState:
        r = self.client.call(P.M_CAPTURE)
        elements = [Element(**e) for e in r.get("elements", [])]
        return ScreenState(summary=r.get("summary", "worker"),
                           elements=elements,
                           screenshot_path=r.get("screenshot_path"))


class WorkerInputController:
    """Drop-in replacement for action.input.InputController, backed by the worker."""

    def __init__(self, client: WorkerClient) -> None:
        self.client = client

    def click(self, x: int, y: int, button: str = "left") -> ToolResult:
        r = self.client.call(P.M_CLICK, {"x": x, "y": y, "button": button})
        return ToolResult(ok=True, output=r.get("detail"))

    def type_text(self, text: str) -> ToolResult:
        r = self.client.call(P.M_TYPE, {"text": text})
        return ToolResult(ok=True, output=r.get("detail"))

    def hotkey(self, *keys: str) -> ToolResult:
        r = self.client.call(P.M_HOTKEY, {"keys": list(keys)})
        return ToolResult(ok=True, output=r.get("detail"))
