"""Stable interfaces the orchestrator depends on.

The core knows ONLY these abstractions — never concrete backends. Swap the
local model, vision backend, or vector DB by binding a different implementation.
This is what keeps the system modular (see docs/MODULARITY.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# --- Data shapes -----------------------------------------------------------

@dataclass
class Element:
    """A grounded, addressable UI target (from a11y tree / vision / OCR)."""
    label: str
    role: str
    x: int
    y: int
    source: str = "a11y"  # "a11y" | "vision" | "ocr"


@dataclass
class ScreenState:
    """What the assistant currently 'sees'."""
    summary: str
    elements: list[Element] = field(default_factory=list)
    screenshot_path: str | None = None


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    permission_tier: str = "read_only"  # read_only | local_write | outward_facing


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


@dataclass
class ToolResult:
    ok: bool
    output: Any = None
    error: str | None = None


# --- Interfaces ------------------------------------------------------------

@runtime_checkable
class LLMProvider(Protocol):
    def plan(self, goal: str, state: ScreenState,
             tools: list[ToolSchema], history: list[dict]) -> ToolCall:
        """Choose the next tool call given the goal and current screen state."""
        ...


@runtime_checkable
class Perception(Protocol):
    def observe(self) -> ScreenState:
        """Capture and ground the current screen into a ScreenState."""
        ...


@runtime_checkable
class ActionExecutor(Protocol):
    def execute(self, call: ToolCall) -> ToolResult:
        """Carry out a low-level action (click, type, launch, ...)."""
        ...


@runtime_checkable
class MemoryStore(Protocol):
    def remember(self, key: str, value: Any) -> None: ...
    def recall(self, query: str, k: int = 5) -> list[Any]: ...


@runtime_checkable
class Plugin(Protocol):
    """A feature that contributes tools. See docs/MODULARITY.md."""
    name: str

    def describe(self) -> list[ToolSchema]: ...
    def invoke(self, tool: str, args: dict[str, Any]) -> ToolResult: ...
