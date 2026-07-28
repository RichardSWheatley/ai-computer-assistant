"""Provider tests with injected fake clients — no network, no daemon.

Covers tool-schema conversion and tool_use parsing for both the Claude and the
local Ollama planners, and proves a local-LLM planner can drive the full
orchestrator loop end to end.
"""

from rita.app import build_assistant
from rita.config import load_config
from rita.core.interfaces import ScreenState, ToolSchema
from rita.llm.claude_provider import ClaudePlanner, to_anthropic_tool
from rita.llm.ollama_provider import OllamaPlanner, to_ollama_tool


def _tools():
    return [ToolSchema(name="click", description="click mouse",
                       parameters={"x": "int", "y": "int", "button": "str=left"})]


def _state():
    return ScreenState(summary="desktop", elements=[])


# --- schema conversion -----------------------------------------------------

def test_anthropic_tool_schema():
    t = to_anthropic_tool(_tools()[0])
    assert t["name"] == "click"
    sch = t["input_schema"]
    assert sch["properties"]["x"] == {"type": "integer"}
    assert sch["properties"]["button"] == {"type": "string"}
    assert set(sch["required"]) == {"x", "y"}  # button has a default -> optional


def test_ollama_tool_schema():
    t = to_ollama_tool(_tools()[0])
    assert t["type"] == "function"
    fn = t["function"]
    assert fn["name"] == "click"
    assert set(fn["parameters"]["required"]) == {"x", "y"}


# --- Claude planner (fake anthropic client) --------------------------------

class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Msg:
    def __init__(self, content, stop_reason="tool_use"):
        self.content = content
        self.stop_reason = stop_reason


class _FakeAnthropic:
    def __init__(self, message):
        self._message = message
        self.captured = None
        self.messages = self  # so client.messages.create(...) works

    def create(self, **kwargs):
        self.captured = kwargs
        return self._message


def test_claude_parses_tool_use():
    msg = _Msg([_Block(type="tool_use", name="click", id="t1",
                       input={"x": 5, "y": 9, "button": "left"})])
    fake = _FakeAnthropic(msg)
    planner = ClaudePlanner(client=fake)
    call = planner.plan("click ok", _state(), _tools(), [])
    assert call.tool == "click" and call.args["x"] == 5
    # request was shaped correctly
    sent = fake.captured
    assert sent["model"] == "claude-opus-4-8"
    assert sent["thinking"] == {"type": "adaptive"}
    tool_names = {t["name"] for t in sent["tools"]}
    assert {"click", "task_complete"} <= tool_names


def test_claude_no_tool_returns_complete():
    msg = _Msg([_Block(type="text", text="All done.")], stop_reason="end_turn")
    planner = ClaudePlanner(client=_FakeAnthropic(msg))
    call = planner.plan("x", _state(), _tools(), [])
    assert call.tool == "task_complete"


def test_claude_refusal_returns_complete():
    msg = _Msg([_Block(type="text", text="")], stop_reason="refusal")
    planner = ClaudePlanner(client=_FakeAnthropic(msg))
    call = planner.plan("x", _state(), _tools(), [])
    assert call.tool == "task_complete"


# --- Ollama planner (fake ollama client) -----------------------------------

class _FakeOllama:
    """Returns a tool_call for the named tool, then task_complete next time."""

    def __init__(self, tool_name, args):
        self._tool_name = tool_name
        self._args = args
        self.calls = 0
        self.captured = None

    def chat(self, **kwargs):
        self.captured = kwargs
        self.calls += 1
        name = self._tool_name if self.calls == 1 else "task_complete"
        args = self._args if self.calls == 1 else {}
        return {"message": {"tool_calls": [
            {"function": {"name": name, "arguments": args}}]}}


def test_ollama_parses_tool_call():
    fake = _FakeOllama("click", {"x": 3, "y": 4})
    planner = OllamaPlanner(model="llama3.1:8b", client=fake)
    call = planner.plan("click ok", _state(), _tools(), [])
    assert call.tool == "click" and call.args == {"x": 3, "y": 4}
    assert call.reasoning == "local:ollama"
    # function tools were sent
    assert any(t["function"]["name"] == "task_complete"
               for t in fake.captured["tools"])


def test_ollama_handles_json_string_arguments():
    class _JsonArgs(_FakeOllama):
        def chat(self, **kwargs):
            return {"message": {"tool_calls": [
                {"function": {"name": "click", "arguments": '{"x": 1, "y": 2}'}}]}}

    planner = OllamaPlanner(client=_JsonArgs("click", {}))
    call = planner.plan("click", _state(), _tools(), [])
    assert call.args == {"x": 1, "y": 2}


def test_local_llm_drives_full_loop():
    # A local-LLM planner (fake Ollama) drives the real orchestrator + plugins.
    fake = _FakeOllama("type_text", {"text": "hello"})
    planner = OllamaPlanner(client=fake)
    cfg = load_config()
    asst = build_assistant(cfg, planner=planner)
    result = asst.run("type hello into the editor")
    assert result.finished is True
    assert any(s.call.tool == "type_text" for s in result.steps)
