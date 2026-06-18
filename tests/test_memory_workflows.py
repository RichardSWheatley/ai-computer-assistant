"""Memory store (keyword + embedder recall, persistence) and the workflow engine."""

from dataclasses import dataclass

from aica.memory.store import MemoryStore
from aica.workflows.engine import BUILTINS, Workflow, WorkflowEngine


# --- memory ----------------------------------------------------------------

def test_remember_and_keyword_recall():
    m = MemoryStore()
    m.remember("stack", "The project uses Python and Ollama.")
    m.remember("style", "User prefers concise commit messages.")
    hits = m.recall("what language does the project use")
    assert any("Python" in h for h in hits)


def test_remember_upserts_by_key():
    m = MemoryStore()
    m.remember("k", "first")
    m.remember("k", "second")
    assert len(m.all()) == 1 and m.all()[0].value == "second"


def test_recall_with_embedder():
    # toy embedder: 2-d vector by presence of two keywords
    def emb(text):
        t = text.lower()
        return [1.0 if "python" in t else 0.0, 1.0 if "deck" in t else 0.0]
    m = MemoryStore(embedder=emb)
    m.remember("a", "we write Python code")
    m.remember("b", "build a slide deck")
    assert m.recall("python language")[0] == "we write Python code"


def test_memory_persists_to_disk(tmp_path):
    p = tmp_path / "mem.json"
    MemoryStore(path=str(p)).remember("k", "durable value")
    assert p.exists()
    reloaded = MemoryStore(path=str(p))
    assert reloaded.recall("durable") == ["durable value"]


def test_memory_plugin_dispatch():
    import importlib.util
    from pathlib import Path
    f = Path(__file__).resolve().parents[1] / "plugins" / "memory" / "plugin.py"
    spec = importlib.util.spec_from_file_location("memory_plugin", str(f))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    plugin = mod.create()
    assert plugin.invoke("remember", {"key": "fav", "value": "blue"}).ok
    assert "blue" in plugin.invoke("recall", {"query": "fav"}).output
    assert plugin.describe()[1].permission_tier == "read_only"  # recall


# --- workflows -------------------------------------------------------------

@dataclass
class _FakeRun:
    finished: bool
    message: str = ""


class _FakeAssistant:
    def __init__(self, fail_on=None):
        self.goals = []
        self.fail_on = fail_on

    def run(self, goal):
        self.goals.append(goal)
        ok = goal != self.fail_on
        return _FakeRun(finished=ok, message="ok" if ok else "declined")


def test_workflow_runs_all_steps():
    a = _FakeAssistant()
    wf = Workflow("demo", "x", ["step one", "step two", "step three"])
    res = WorkflowEngine(a).run(wf)
    assert res.completed and len(res.step_results) == 3
    assert a.goals == ["step one", "step two", "step three"]


def test_workflow_stops_on_blocked_step():
    a = _FakeAssistant(fail_on="step two")
    wf = Workflow("demo", "x", ["step one", "step two", "step three"])
    res = WorkflowEngine(a).run(wf)
    assert not res.completed
    assert len(res.step_results) == 2          # stopped, didn't run step three
    assert "step two" in res.message


def test_builtin_workflows_present():
    a = _FakeAssistant()
    res = WorkflowEngine(a).run_named("daily_brief")
    assert res.completed
    assert "daily_brief" in BUILTINS and "meeting_prep" in BUILTINS
