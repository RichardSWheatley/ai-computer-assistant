"""Claude cloud provider — the 'heavy lifting' planner for CLOUD_DEFAULT mode.

Guarded and lazy: requires the `anthropic` package and an API key. It is only
ever constructed when mode != LOCAL_ONLY (the router enforces this), so in
local-only mode this module is never imported and no network path exists.

This is a thin skeleton: it shapes the request/response. Wire the real tool-use
call where indicated. Until then it raises clearly so callers fall back to local.
"""

from __future__ import annotations

import os

from ..core.interfaces import LLMProvider, ScreenState, ToolCall, ToolSchema


class ClaudePlanner(LLMProvider):
    def __init__(self, model: str = "claude-opus-4-8",
                 api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set; cloud planner unavailable")
        try:
            import anthropic  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("anthropic package not installed") from exc
        self._client = anthropic.Anthropic(api_key=self.api_key)

    def plan(self, goal: str, state: ScreenState,
             tools: list[ToolSchema], history: list[dict]) -> ToolCall:  # pragma: no cover
        # TODO: map `tools` -> Anthropic tool schemas, send `state.summary` +
        # screenshot (already redacted by the router) + history, parse the
        # tool_use block into a ToolCall. Skeleton raises so callers degrade
        # gracefully until this is implemented.
        raise NotImplementedError("ClaudePlanner.plan not wired yet")
