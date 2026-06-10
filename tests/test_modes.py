"""Operating modes (hardware-driven):

- AUTO: heavy work goes to the best LOCAL model when one exists (VRAM present),
  and to Claude only when there is no local large model. Routine -> small local.
- LOCAL_ONLY: never touches the cloud (structurally guaranteed).
"""

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


def _auto(**kw):
    return LLMRouter(policy=RoutingPolicy(mode=OperatingMode.AUTO), **kw)


def test_auto_prefers_local_large_for_heavy_when_vram():
    # VRAM present -> a local large model exists -> it is the default for heavy.
    small, large, cloud = Recorder("s"), Recorder("L"), Recorder("c")
    router = _auto(small=small, large=large, cloud=cloud)
    router.plan("analyze this stack trace and fix it", _state(), [], [])
    assert large.calls == 1 and cloud.calls == 0
    assert router.last_route == "local-large"


def test_auto_uses_cloud_for_heavy_when_no_local_large():
    # No VRAM -> no local large model -> Claude is the default for heavy.
    small, cloud = Recorder("s"), Recorder("c")
    router = _auto(small=small, cloud=cloud)
    router.plan("design a database schema for billing", _state(), [], [])
    assert cloud.calls == 1 and small.calls == 0
    assert router.last_route == "cloud"


def test_auto_keeps_routine_local():
    small, large, cloud = Recorder("s"), Recorder("L"), Recorder("c")
    router = _auto(small=small, large=large, cloud=cloud)
    router.plan("click ok", _state(), [], [])
    assert small.calls == 1 and large.calls == 0 and cloud.calls == 0
    assert router.last_route == "local-small"


def test_auto_escalates_stuck_local_to_cloud():
    small, large, cloud = Recorder("s"), Recorder("L"), Recorder("c")
    router = _auto(small=small, large=large, cloud=cloud)
    fails = [{"ok": False}, {"ok": False}]  # local has been failing -> escalate
    router.plan("refactor the module", _state(), [], fails)
    assert cloud.calls == 1
    assert router.last_route == "cloud"


def test_local_only_never_calls_cloud_even_when_heavy():
    small, large = Recorder("s"), Recorder("L")
    router = LLMRouter(small=small, large=large,
                       policy=RoutingPolicy(mode=OperatingMode.LOCAL_ONLY))
    router.plan("analyze and refactor this whole module", _state(), [], [])
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

    # No local large -> heavy goes to cloud; the raw frame must be stripped.
    router = _auto(small=Recorder("l"), cloud=CloudSpy())
    st = ScreenState(summary="x", elements=[], screenshot_path="/tmp/secret.png")
    router.plan("summarize the screen", st, [], [])
    assert captured["screenshot_path"] is None


def test_config_default_is_auto():
    cfg = load_config(local_only=False)
    assert cfg.mode == "auto"
    assert cfg.use_cloud is True


def test_config_local_only_disables_cloud():
    cfg = load_config(local_only=True)
    assert cfg.mode == "local-only"
    assert cfg.use_cloud is False


def test_back_compat_mode_alias():
    assert OperatingMode.parse("cloud-default") is OperatingMode.AUTO
    assert OperatingMode.parse("local-only") is OperatingMode.LOCAL_ONLY


def test_heuristic_classifier_signals():
    c = HeuristicClassifier()
    assert c.is_heavy("design a database schema", _state(), []) is True
    assert c.is_heavy("click", _state(), []) is False
    fails = [{"ok": False}, {"ok": False}]
    assert c.is_heavy("click", _state(), fails) is True
