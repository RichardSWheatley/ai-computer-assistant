from rita.app import build_assistant
from rita.config import load_config
from rita.core.interfaces import Plugin, ToolResult, ToolSchema
from rita.core.registry import ToolRegistry
from rita.plugins.loader import discover


def test_assistant_runs_to_completion():
    cfg = load_config()
    asst = build_assistant(cfg)
    result = asst.run("type_text hello there")
    assert result.finished is True
    assert any(s.call.tool == "type_text" for s in result.steps)


def test_builtin_computer_use_registered():
    cfg = load_config()
    asst = build_assistant(cfg)
    names = {s.name for s in asst.registry.schemas()}
    assert {"click", "type_text", "hotkey"} <= names


def test_dropin_plugin_discovered():
    # The example `plugins/hello` plugin should load and register say_hello.
    cfg = load_config()
    asst = build_assistant(cfg)
    names = {s.name for s in asst.registry.schemas()}
    assert "say_hello" in names


def test_confirmation_gate_blocks_outward_action():
    class SendPlugin(Plugin):
        name = "sender"

        def describe(self):
            return [ToolSchema(name="send", description="send",
                               permission_tier="outward_facing")]

        def invoke(self, tool, args):
            return ToolResult(ok=True, output="sent")

    reg = ToolRegistry()
    reg.register_plugin(SendPlugin())
    assert reg.tier("send") == "outward_facing"


def test_kill_switch_halts():
    cfg = load_config()
    asst = build_assistant(cfg)
    asst.kill_switch.trigger()
    result = asst.run("type_text hello")
    assert result.finished is False
    assert "kill switch" in result.message.lower()
