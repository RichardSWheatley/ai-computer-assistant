"""Operating modes: cloud-default routes heavy work to cloud; local-only never
touches the cloud (structurally guaranteed)."""

import pytest

from aica.config import load_config
from aica.core.interfaces import LLMProvider, ScreenState, ToolCall
from aica.llm.router import (
    HeuristicClassifier,
    LLMRouter,
    OperatingMode,
    RoutingPolicy,
)


class Recorder(LLMProvider):
    """A fake provider that records that it was called and tags the tool."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.calls = 0

    def plan(self, goal, state, tools, history) -> ToolCall:
        self.calls += 1
        return ToolCall(tool="task_complete", reasoning=self.tag)


def _state():
    return ScreenState(summary="s", elements=[])


def test_cloud_default_routes_heavy_to_cloud():
    small, cloud = Recorder("local"), Recorder("cloud")
    router = LLMRouter(small=small, cloud=cloud,
                       policy=RoutingPolicy(mode=OperatingMode.CLOUD_DEFAULT))
    # "analyze ..." is heavy -> cloud
    router.plan("analyze this stack trace and fix it", _state(), [], [])
    assert cloud.calls == 1 and small.calls == 0
    assert router.last_route == "cloud"


def test_cloud_default_keeps_routine_local():
    small, cloud = Recorder("local"), Recorder("cloud")
    router = LLMRouter(small=small, cloud=cloud,
                       policy=RoutingPolicy(mode=OperatingMode.CLOUD_DEFAULT))
    router.plan("click ok", _state(), [], [])   # mechanical -> local
    assert small.calls == 1 and cloud.calls == 0
    assert router.last_route == "local-small"


def test_local_only_never_calls_cloud_even_when_heavy():
    small, large = Recorder("local"), Recorder("local-large")
    router = LLMRouter(small=small, large=large,
                       policy=RoutingPolicy(mode=OperatingMode.LOCAL_ONLY))
    router.plan("analyze and refactor this whole module", _state(), [], [])
    # heavy -> larger LOCAL model, not cloud
    assert large.calls == 1
    assert router.last_route == "local-large"


def test_local_only_refuses_to_hold_cloud_provider():
    with pytest.raises(ValueError):
        LLMRouter(small=Recorder("l"), cloud=Recorder("c"),
                  policy=RoutingPolicy(mode=OperatingMode.LOCAL_ONLY))


def test_redaction_strips_screenshot_before_cloud():
    captured = {}

    class CloudSpy(LLMProvider):
        def plan(self, goal, state, tools, history):
            captured["screenshot_path"] = state.screenshot_path
            return ToolCall(tool="task_complete")

    router = LLMRouter(small=Recorder("l"), cloud=CloudSpy(),
                       policy=RoutingPolicy(mode=OperatingMode.CLOUD_DEFAULT))
    st = ScreenState(summary="x", elements=[], screenshot_path="/tmp/secret.png")
    router.plan("summarize the screen", st, [], [])
    assert captured["screenshot_path"] is None  # raw frame never leaves


def test_config_local_only_disables_cloud():
    cfg = load_config(local_only=True)
    assert cfg.mode == "local-only"
    assert cfg.use_cloud is False


def test_config_default_is_cloud():
    cfg = load_config(local_only=False)
    assert cfg.mode == "cloud-default"
    assert cfg.use_cloud is True


def test_heuristic_classifier_signals():
    c = HeuristicClassifier()
    assert c.is_heavy("design a database schema", _state(), []) is True
    assert c.is_heavy("click", _state(), []) is False
    # stuck -> heavy
    fails = [{"ok": False}, {"ok": False}]
    assert c.is_heavy("click", _state(), fails) is True
