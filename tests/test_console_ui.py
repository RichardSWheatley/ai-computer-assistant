"""Interactive console confirmer + its integration with the orchestrator gate."""

from rita.app import build_assistant
from rita.config import load_config
from rita.core.interfaces import Plugin, ToolCall, ToolResult, ToolSchema
from rita.ui.console import describe_action, make_console_confirmer


def test_describe_action_renders_tool_and_args():
    s = describe_action(ToolCall(tool="send_email",
                                 args={"to": ["a@co"], "subject": "Hi"},
                                 reasoning="user asked"))
    assert "send_email" in s and "to=" in s and "user asked" in s


def test_confirmer_approves_on_yes():
    out = []
    confirm = make_console_confirmer(input_fn=lambda p: "y", output_fn=out.append)
    assert confirm(ToolCall(tool="send_email")) is True
    assert any("Approval needed" in line for line in out)


def test_confirmer_denies_on_blank_or_no():
    deny_blank = make_console_confirmer(input_fn=lambda p: "", output_fn=lambda s: None)
    deny_no = make_console_confirmer(input_fn=lambda p: "n", output_fn=lambda s: None)
    assert deny_blank(ToolCall(tool="x")) is False
    assert deny_no(ToolCall(tool="x")) is False


class _SendPlugin(Plugin):
    name = "sender"

    def describe(self):
        return [ToolSchema("send_it", "send", {}, "outward_facing")]

    def invoke(self, tool, args):
        return ToolResult(ok=True, output="SENT")


def test_interactive_confirmer_unblocks_outward_action():
    cfg = load_config()
    # With an interactive 'yes' confirmer, the outward action is now allowed.
    asst = build_assistant(cfg, confirm=make_console_confirmer(
        input_fn=lambda p: "y", output_fn=lambda s: None))
    asst.registry.register_plugin(_SendPlugin())
    assert asst.would_allow(ToolCall(tool="send_it")) is True

    # A 'no' confirmer keeps it blocked.
    asst2 = build_assistant(cfg, confirm=make_console_confirmer(
        input_fn=lambda p: "n", output_fn=lambda s: None))
    asst2.registry.register_plugin(_SendPlugin())
    assert asst2.would_allow(ToolCall(tool="send_it")) is False
