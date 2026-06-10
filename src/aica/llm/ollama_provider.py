"""Ollama local-LLM planner — the default heavy-lifting engine when VRAM exists.

Implements the same single-step planner contract as the Claude provider, using
Ollama's tool-calling (OpenAI-style function tools) so a local model picks the
next action. Runs fully on-device — nothing leaves the machine.

Guarded and lazy: requires the `ollama` package and a running daemon with the
model pulled. Accepts an injected `client` for testing without a daemon.
"""

from __future__ import annotations

import json

from ..core.interfaces import LLMProvider, ScreenState, ToolCall, ToolSchema
from .schema import object_schema

_SYSTEM = (
    "You are the planning brain of a local computer-use assistant. Given the "
    "user's GOAL, a text description of the current SCREEN, and the HISTORY of "
    "actions taken, call exactly ONE tool that best advances the goal. Call "
    "task_complete when the goal is achieved. Act on listed elements; do not "
    "invent coordinates."
)

_DONE_TOOL = {
    "type": "function",
    "function": {
        "name": "task_complete",
        "description": "Call when the goal is achieved and no further action is needed.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": [],
        },
    },
}


def to_ollama_tool(schema: ToolSchema) -> dict:
    """Convert a ToolSchema into an Ollama/OpenAI-style function tool."""
    return {
        "type": "function",
        "function": {
            "name": schema.name,
            "description": schema.description,
            "parameters": object_schema(schema.parameters),
        },
    }


def _extract_tool_calls(response) -> list:
    """Pull tool_calls out of an Ollama chat response (object or dict form)."""
    msg = getattr(response, "message", None)
    if msg is None and isinstance(response, dict):
        msg = response.get("message")
    if msg is None:
        return []
    calls = getattr(msg, "tool_calls", None)
    if calls is None and isinstance(msg, dict):
        calls = msg.get("tool_calls")
    return calls or []


def _name_and_args(call) -> tuple[str, dict]:
    fn = getattr(call, "function", None)
    if fn is None and isinstance(call, dict):
        fn = call.get("function", {})
    name = getattr(fn, "name", None)
    if name is None and isinstance(fn, dict):
        name = fn.get("name")
    args = getattr(fn, "arguments", None)
    if args is None and isinstance(fn, dict):
        args = fn.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (ValueError, TypeError):
            args = {}
    return name or "", dict(args or {})


class OllamaPlanner(LLMProvider):
    def __init__(self, model: str = "llama3.1:8b", host: str | None = None,
                 client=None) -> None:
        self.model = model
        if client is not None:  # injected (tests)
            self._client = client
            return
        try:
            import ollama  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError("ollama package not installed") from exc
        self._client = ollama.Client(host=host) if host else ollama.Client()

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
        ollama_tools = [to_ollama_tool(t) for t in tools] + [_DONE_TOOL]
        response = self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",
                 "content": self._user_message(goal, state, history)},
            ],
            tools=ollama_tools,
        )
        calls = _extract_tool_calls(response)
        if calls:
            name, args = _name_and_args(calls[0])
            if name:
                return ToolCall(tool=name, args=args, reasoning="local:ollama")
        return ToolCall(tool="task_complete", reasoning="no tool call from local model")
