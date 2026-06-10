"""Model routing + Claude escalation.

Local-first: route routine steps to a small/fast local model, escalate hard or
high-stakes steps to a larger local model and, if needed, the Claude API.

This module wires the *policy*; concrete providers (Ollama, Claude) are loaded
lazily so the core has no hard dependency on them. With nothing installed it
falls back to MockLLM, so the loop always runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.interfaces import LLMProvider, ScreenState, ToolCall, ToolSchema
from .mock import MockLLM


@dataclass
class RoutingPolicy:
    # Escalate when the local planner has tried this many steps without finishing,
    # or when a step is flagged high-stakes.
    escalate_after_retries: int = 3
    allow_cloud: bool = True
    redact_before_cloud: bool = True


class LLMRouter(LLMProvider):
    def __init__(
        self,
        small: LLMProvider | None = None,
        large: LLMProvider | None = None,
        cloud: LLMProvider | None = None,
        policy: RoutingPolicy | None = None,
    ) -> None:
        self.small = small or MockLLM()
        self.large = large
        self.cloud = cloud
        self.policy = policy or RoutingPolicy()
        self._stall = 0

    def _should_escalate(self, history: list[dict]) -> bool:
        recent = history[-self.policy.escalate_after_retries:]
        return (
            len(recent) >= self.policy.escalate_after_retries
            and all(not h.get("ok") for h in recent)
        )

    def plan(self, goal: str, state: ScreenState,
             tools: list[ToolSchema], history: list[dict]) -> ToolCall:
        if self._should_escalate(history):
            if self.cloud is not None and self.policy.allow_cloud:
                # NOTE: redaction of `state`/`history` happens in the cloud
                # provider before any data leaves the machine.
                return self.cloud.plan(goal, state, tools, history)
            if self.large is not None:
                return self.large.plan(goal, state, tools, history)
        return self.small.plan(goal, state, tools, history)


def build_default_planner(config) -> LLMProvider:
    """Construct a planner from config + detected hardware.

    Lazily imports backends; silently falls back to mock when unavailable so
    the assistant always starts.
    """
    small = large = cloud = None

    # Local model via Ollama, accelerated by detected backend (cuda/metal/cpu).
    try:  # pragma: no cover - depends on optional deps + a running daemon
        if getattr(config, "use_local_llm", False):
            from .ollama_provider import OllamaPlanner
            small = OllamaPlanner(model=config.small_model)
            if config.large_model:
                large = OllamaPlanner(model=config.large_model)
    except Exception:
        small = large = None

    try:  # pragma: no cover
        if getattr(config, "use_cloud", False):
            from .claude_provider import ClaudePlanner
            cloud = ClaudePlanner(model=config.cloud_model)
    except Exception:
        cloud = None

    return LLMRouter(small=small, large=large, cloud=cloud)
