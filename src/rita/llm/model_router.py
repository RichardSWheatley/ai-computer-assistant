"""Model routing across two operating modes + a heavy/light classifier.

Modes (see docs/MODES.md):
  AUTO (default) — hardware-driven. Heavy reasoning goes to the best LOCAL model
      when one exists (i.e. when VRAM is available), and to the cloud only when no
      capable local model is present. Routine mechanical steps stay on the small
      local model for speed. So: local LLM is the default when you have VRAM;
      cloud is the default when you don't. Cloud is also used to escalate when
      the local model gets stuck.
  LOCAL_ONLY     — cloud is hard-disabled. The cloud provider is never
      constructed, so nothing can leave the machine. Privacy guarantee.

The privacy guarantee is enforced structurally: in LOCAL_ONLY the router refuses
to hold a cloud provider at all (asserted in __init__), so there is no code path
that reaches the network.

Concrete providers (local or cloud) are injected or loaded lazily; with nothing installed
the router falls back to MockLLM so the loop always runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.interfaces import LLMProvider, ScreenState, ToolCall, ToolSchema
from .mock import MockLLM


class OperatingMode(str, Enum):
    AUTO = "auto"              # hardware-driven: local when VRAM, cloud when none
    LOCAL_ONLY = "local-only"  # never leave the machine

    @classmethod
    def parse(cls, value) -> "OperatingMode":
        if isinstance(value, cls):
            return value
        s = str(value)
        # Back-compat aliases for the earlier naming.
        if s in ("cloud-default", "local-first", "default"):
            return cls.AUTO
        try:
            return cls(s)
        except ValueError:
            return cls.AUTO


# --- heavy vs light classification ----------------------------------------

# Signals that a planning step needs deep reasoning ("heavy lifting").
_HEAVY_KEYWORDS = (
    "analyze", "design", "debug", "refactor", "architect", "plan", "explain",
    "summarize", "write", "generate", "review", "research", "compose", "draft",
    "diagnose", "optimize", "build a", "create a",
)


class Classifier:
    """Returns True if this planning decision is 'heavy' (wants the cloud)."""

    def is_heavy(self, goal: str, state: ScreenState, history: list[dict]) -> bool:
        raise NotImplementedError


class HeuristicClassifier(Classifier):
    def __init__(self, stuck_after: int = 2, long_goal_chars: int = 160) -> None:
        self.stuck_after = stuck_after
        self.long_goal_chars = long_goal_chars

    def is_heavy(self, goal: str, state: ScreenState, history: list[dict]) -> bool:
        g = goal.lower()
        if any(k in g for k in _HEAVY_KEYWORDS):
            return True
        if len(goal) >= self.long_goal_chars:
            return True
        # Stuck: recent steps failed -> needs stronger reasoning.
        recent = history[-self.stuck_after:]
        if len(recent) >= self.stuck_after and all(not h.get("ok") for h in recent):
            return True
        return False


@dataclass
class RoutingPolicy:
    mode: OperatingMode = OperatingMode.AUTO
    redact_before_cloud: bool = True
    # Escalate a stuck local model to the cloud after this many failed steps.
    escalate_after_failures: int = 2


class LLMRouter(LLMProvider):
    def __init__(
        self,
        small: LLMProvider | None = None,
        large: LLMProvider | None = None,
        cloud: LLMProvider | None = None,
        policy: RoutingPolicy | None = None,
        classifier: Classifier | None = None,
    ) -> None:
        self.policy = policy or RoutingPolicy()
        # Structural privacy guarantee: no cloud provider may exist in LOCAL_ONLY.
        if self.policy.mode is OperatingMode.LOCAL_ONLY and cloud is not None:
            raise ValueError("LOCAL_ONLY mode must not be given a cloud provider")
        self.small = small or MockLLM()
        self.large = large
        self.cloud = cloud
        self.classifier = classifier or HeuristicClassifier()
        self.last_route: str = "local-small"  # introspection / logging

    @property
    def mode(self) -> OperatingMode:
        return self.policy.mode

    def _stuck(self, history: list[dict]) -> bool:
        n = self.policy.escalate_after_failures
        recent = history[-n:]
        return len(recent) >= n and all(not h.get("ok") for h in recent)

    def _route_cloud(self, goal, state, tools, history) -> ToolCall:
        self.last_route = "cloud"
        payload = _redact(state) if self.policy.redact_before_cloud else state
        return self.cloud.plan(goal, payload, tools, history)

    def _route_large(self, goal, state, tools, history) -> ToolCall:
        self.last_route = "local-large"
        return self.large.plan(goal, state, tools, history)

    def _route_small(self, goal, state, tools, history) -> ToolCall:
        self.last_route = "local-small"
        return self.small.plan(goal, state, tools, history)

    def plan(self, goal: str, state: ScreenState,
             tools: list[ToolSchema], history: list[dict]) -> ToolCall:
        heavy = self.classifier.is_heavy(goal, state, history)

        # LOCAL_ONLY: never touch the cloud. Heavy work uses the larger local
        # model if present, else the small one.
        if self.mode is OperatingMode.LOCAL_ONLY:
            if heavy and self.large is not None:
                return self._route_large(goal, state, tools, history)
            return self._route_small(goal, state, tools, history)

        # AUTO (hardware-driven). For heavy steps, prefer the best LOCAL model
        # when one exists (VRAM present); fall back to the cloud when there is no
        # local large model, or to escalate a stuck local model.
        if heavy:
            if self.cloud is not None and (self.large is None or self._stuck(history)):
                return self._route_cloud(goal, state, tools, history)
            if self.large is not None:
                return self._route_large(goal, state, tools, history)
        return self._route_small(goal, state, tools, history)


def _redact(state: ScreenState) -> ScreenState:
    """Minimal redaction before anything leaves the machine.

    Placeholder for a real policy (mask secrets/PII in element text and the
    screenshot). Kept here so the redaction point is explicit and testable.
    """
    return ScreenState(summary=state.summary, elements=state.elements,
                       screenshot_path=None)  # never ship raw frames to cloud


def build_default_planner(config, cloud_planner=None) -> LLMProvider:
    """Construct a routed planner from config + detected hardware.

    Honors config.mode. In LOCAL_ONLY the cloud provider is never constructed.
    Lazily imports backends and falls back to mock when unavailable.
    """
    mode = OperatingMode.parse(getattr(config, "mode", OperatingMode.AUTO))
    small = large = cloud = None

    try:  # pragma: no cover - optional deps + running daemon
        if getattr(config, "use_local_llm", False):
            from .ollama_provider import OllamaPlanner
            small = OllamaPlanner(model=config.small_model)
            if config.large_model:
                large = OllamaPlanner(model=config.large_model)
    except Exception:
        small = large = None

    if mode is not OperatingMode.LOCAL_ONLY and getattr(config, "use_cloud", True):
        # A cloud planner is injected, never built in: no vendor client ships
        # with RITA. Pass one via `cloud=` or set config.cloud_planner.
        cloud = cloud_planner or getattr(config, "cloud_planner", None)

    # No local model available (e.g. no GPU and no Ollama) but cloud is? Then
    # the cloud model handles routine steps too — otherwise the routine path would fall
    # back to the do-nothing MockLLM. This is the no-GPU default.
    if small is None and cloud is not None:
        small = cloud

    policy = RoutingPolicy(mode=mode)
    return LLMRouter(small=small, large=large, cloud=cloud, policy=policy)
