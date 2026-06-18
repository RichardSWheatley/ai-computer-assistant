"""Weekend path: the no-key doc CLI, and Claude-handles-everything routing
when there's no local model (the no-GPU default)."""

import json
from pathlib import Path

import pytest

from aica.__main__ import main
from aica.config import Config
from aica.core.interfaces import ScreenState, ToolCall
from aica.llm import router as router_mod
from aica.llm.router import build_default_planner


def test_doc_cli_writes_all_three(tmp_path):
    pytest.importorskip("pptx")
    pytest.importorskip("docx")
    pytest.importorskip("openpyxl")
    ex = Path(__file__).resolve().parents[1] / "examples"

    deck = tmp_path / "d.pptx"
    assert main(["doc", "deck", str(ex / "deck.json"), "-o", str(deck)]) == 0
    assert deck.exists() and deck.stat().st_size > 0

    rep = tmp_path / "r.docx"
    assert main(["doc", "report", str(ex / "report.json"), "-o", str(rep)]) == 0
    assert rep.exists()

    sht = tmp_path / "s.xlsx"
    assert main(["doc", "sheet", str(ex / "sheet.json"), "-o", str(sht)]) == 0
    assert sht.exists()


def test_no_local_model_routes_everything_to_cloud(monkeypatch):
    # Simulate a no-GPU machine: no local LLM, but a cloud (Claude) provider.
    class FakeClaude:
        def __init__(self, model=None):
            self.model = model

        def plan(self, goal, state, tools, history):
            return ToolCall(tool="task_complete", reasoning="cloud")

    import aica.llm.claude_provider as cp
    monkeypatch.setattr(cp, "ClaudePlanner", FakeClaude)

    cfg = Config(use_local_llm=False, use_cloud=True, mode="auto",
                 cloud_model="claude-opus-4-8")
    planner = build_default_planner(cfg)

    # No local model -> routine (light) steps must go to cloud, not MockLLM.
    assert planner.small is planner.cloud
    planner.plan("click ok", ScreenState(summary="s", elements=[]), [], [])
    assert planner.last_route == "local-small"   # == cloud here (small bound to cloud)
    assert isinstance(planner.cloud, FakeClaude)
