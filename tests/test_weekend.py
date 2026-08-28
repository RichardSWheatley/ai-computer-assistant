"""Weekend path: the no-key doc CLI, and cloud-handles-everything routing
when there's no local model (the no-GPU default)."""

import json
from pathlib import Path

import pytest

from rita.__main__ import main
from rita.config import Config
from rita.core.interfaces import ScreenState, ToolCall
from rita.llm import model_router as router_mod
from rita.llm.model_router import build_default_planner


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
    # Simulate a no-GPU machine: no local LLM, but an injected cloud provider.
    class FakeCloud:
        def __init__(self, model=None):
            self.model = model

        def plan(self, goal, state, tools, history):
            return ToolCall(tool="task_complete", reasoning="cloud")

    cfg = Config(use_local_llm=False, use_cloud=True, mode="auto")
    planner = build_default_planner(cfg, cloud_planner=FakeCloud())

    # No local model -> routine (light) steps must go to cloud, not MockLLM.
    assert planner.small is planner.cloud
    planner.plan("click ok", ScreenState(summary="s", elements=[]), [], [])
    assert planner.last_route == "local-small"   # == cloud here (small bound to cloud)
    assert isinstance(planner.cloud, FakeCloud)
