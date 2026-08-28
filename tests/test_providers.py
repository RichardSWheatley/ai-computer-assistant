"""Provider tests with injected fake clients — no network, no daemon.

Covers tool-schema conversion and tool_call parsing for the local Ollama
planner, and proves a local-LLM planner can drive the full orchestrator
loop end to end. Cloud planners are injected objects with no shipped
client, so there is nothing vendor-specific to test here.
"""

from rita.app import build_assistant
from rita.config import load_config
from rita.core.interfaces import ScreenState, ToolSchema
from rita.llm.ollama_provider import OllamaPlanner, to_ollama_tool


def _tools():
    return [ToolSchema(name="click", description="click mouse",
                       parameters={"x": "int", "y": "int", "button": "str=left"})]


def _state():
    return ScreenState(summary="desktop", elements=[])


# --- schema conversion -----------------------------------------------------

def test_ollama_tool_schema():
    t = to_ollama_tool(_tools()[0])
    assert t["type"] == "function"
    fn = t["function"]
    assert fn["name"] == "click"
    assert set(fn["parameters"]["required"]) == {"x", "y"}


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
