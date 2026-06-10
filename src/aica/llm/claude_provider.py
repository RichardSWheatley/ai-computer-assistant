"""Claude cloud provider — the 'heavy lifting' planner for CLOUD_DEFAULT mode.

Implements the single-step planner contract (`plan()` returns one ToolCall) via
a real Anthropic tool-use call:

  - our ToolSchemas are converted to Anthropic tool definitions,
  - Claude is asked to choose the next action, plus a `task_complete` tool,
  - the returned `tool_use` block is parsed back into a ToolCall.

Privacy: the router redacts `state` (drops the raw screenshot) before calling
this provider, so only the textual screen description leaves the machine.

Guarded and lazy: requires the `anthropic` package and an API key, and is only
ever constructed when mode != LOCAL_ONLY (the router enforces this). In
local-only mode this module is never imported and no network path exists.
"""

from __future__ import annotations

import os

from ..core.interfaces import LLMProvider, ScreenState, ToolCall, ToolSchema
from .schema import object_schema

MODEL = "claude-opus-4-8"

_SYSTEM = (
    "You are the planning brain of a local computer-use assistant. On each turn "
    "you receive the user's GOAL, a text description of the current SCREEN "
    "(accessibility elements — not a raw image), and the HISTORY of actions "
    "already taken. Choose exactly ONE tool call that makes the most progress "
    "toward the goal. Call task_complete when the goal is achieved or no further "
    "action is sensible. Prefer acting on listed elements; do not invent "
    "coordinates for elements you cannot see."
)


def to_anthropic_tool(schema: ToolSchema) -> dict:
    """Convert one of our ToolSchemas into an Anthropic tool definition."""
    return {
        "name": schema.name,
        "description": schema.description,
        "input_schema": object_schema(schema.parameters),
    }


_DONE_TOOL = {
    "name": "task_complete",
    "description": "Call this when the goal is achieved and no further action is needed.",
    "input_schema": {
        "type": "object",
        "properties": {"reason": {"type": "string", "description": "Why the task is done."}},
        "required": [],
    },
}


class ClaudePlanner(LLMProvider):
    def __init__(
        self,
        model: str = MODEL,
        api_key: str | None = None,
        client=None,
        max_tokens: int = 8192,
        effort: str = "high",
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        if client is not None:  # injected (tests)
            self._client = client
            return
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set; cloud planner unavailable")
        try:
            import anthropic  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError("anthropic package not installed") from exc
        self._client = anthropic.Anthropic(api_key=key)

    def _user_message(self, goal: str, state: ScreenState, history: list[dict]) -> str:
        lines = [f"GOAL: {goal}", "", f"SCREEN: {state.summary}"]
        if state.elements:
            lines.append("ELEMENTS:")
            for e in state.elements:
                lines.append(f"  - {e.role} {e.label!r} at ({e.x},{e.y})")
        if history:
            lines.append("")
            lines.append("HISTORY (most recent last):")
            for h in history[-10:]:
                status = "ok" if h.get("ok") else f"ERROR: {h.get('error')}"
                lines.append(f"  - {h.get('tool')}({h.get('args')}) -> {status}")
        lines += ["", "Choose the single next tool call."]
        return "\n".join(lines)

    def plan(self, goal: str, state: ScreenState,
             tools: list[ToolSchema], history: list[dict]) -> ToolCall:
        anthropic_tools = [to_anthropic_tool(t) for t in tools] + [_DONE_TOOL]
        message = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=_SYSTEM,
            tools=anthropic_tools,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=[{"role": "user",
                       "content": self._user_message(goal, state, history)}],
        )

        if getattr(message, "stop_reason", None) == "refusal":
            return ToolCall(tool="task_complete",
                            reasoning="Claude declined to act on this request.")

        # First tool_use block is the chosen action.
        for block in message.content:
            if getattr(block, "type", None) == "tool_use":
                return ToolCall(tool=block.name,
                                args=dict(block.input or {}),
                                reasoning="cloud:claude")

        # No tool call -> treat any text as an explanation / completion.
        text = next((b.text for b in message.content
                     if getattr(b, "type", None) == "text"), "")
        return ToolCall(tool="task_complete", reasoning=text or "no action proposed")
