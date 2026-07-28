"""A deterministic mock planner so the whole loop runs with no model installed.

It lets you exercise the orchestrator + plugins headlessly (CI, this container,
your PC before a GPU is set up). Real providers implement the same `plan()`.
"""

from __future__ import annotations

from ..core.interfaces import LLMProvider, ScreenState, ToolCall, ToolSchema


class MockLLM(LLMProvider):
    """Walks through available non-read-only tools once, then completes.

    Picks the first tool whose name appears in the goal text, otherwise the
    first registered tool; emits `task_complete` when nothing is left to try.
    """

    def __init__(self) -> None:
        self._used: set[str] = set()

    def plan(self, goal: str, state: ScreenState,
             tools: list[ToolSchema], history: list[dict]) -> ToolCall:
        goal_l = goal.lower()
        # Prefer a tool explicitly named in the goal.
        for t in tools:
            if t.name in self._used:
                continue
            if t.name.replace("_", " ") in goal_l or t.name in goal_l:
                self._used.add(t.name)
                return ToolCall(tool=t.name, args={"goal": goal},
                                reasoning=f"goal mentions {t.name}")
        # Otherwise try the next unused tool.
        for t in tools:
            if t.name not in self._used:
                self._used.add(t.name)
                return ToolCall(tool=t.name, args={"goal": goal},
                                reasoning="trying next available tool")
        return ToolCall(tool="task_complete", reasoning="no tools left to try")
