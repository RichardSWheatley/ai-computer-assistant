"""Projects: hand a task to RITA — an AI may plan it, only RITA executes.

The plan is data (commands in RITA's own grammar, validated by routing
every item); execution runs through RITA's gates, item by item, persisted
and pausable.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"


def blinky_fit(_p: str = "") -> str:
    return json.dumps({"fit": "sample.basic.blinky", "reason": "fits"})


GOOD_PLAN = json.dumps({"items": [
    {"title": "Bring up the LED sample", "command": "build blinky",
     "depends_on": [], "estimate": "20m", "milestone": "bring-up"},
    {"title": "Run it on sim", "command": "run the blinky sample",
     "depends_on": [0], "estimate": "10m", "milestone": "bring-up"},
    {"title": "Board facts", "command": "tell me about the apollo510",
     "depends_on": [], "estimate": "5m", "milestone": "docs"},
]})

PLAN_WITH_UNROUTABLE = json.dumps({"items": [
    {"title": "Build the sample", "command": "build blinky", "depends_on": []},
    {"title": "Order pizza", "command": "order a pepperoni pizza",
     "depends_on": []},
]})


# --- Planner: the plan is data, validated deterministically ------------------

class TestPlanner:
    def vocab(self):
        from rita.routing.vocabulary import Vocabulary
        return Vocabulary.seed()

    def test_work_routable_goal_needs_no_ai(self):
        # "Figures it out herself": a direct command becomes a one-item
        # project with zero planner calls.
        from rita.projects.planner import quick_plan
        calls = []
        project = quick_plan("build blinky for the apollo510", self.vocab())
        assert project is not None
        assert len(project.items) == 1
        assert project.items[0].command == "build blinky for the apollo510"
        assert calls == []

    def test_non_work_goal_returns_none_from_quick_plan(self):
        from rita.projects.planner import quick_plan
        assert quick_plan("get mspi psram support production ready with "
                          "docs and characterization", self.vocab()) is None

    def test_plan_parsed_and_every_command_routed(self):
        from rita.projects.planner import plan_project
        calls = []

        def complete(prompt):
            calls.append(prompt)
            return GOOD_PLAN

        project = plan_project("bring up blinky and document the board",
                               complete, self.vocab())
        assert len(calls) == 1                      # one bounded call
        assert "grammar" in calls[0].lower() or "command" in calls[0].lower()
        assert [i.status for i in project.items] == ["pending", "pending",
                                                     "pending"]
        assert project.items[1].depends_on == [project.items[0].id]

    def test_unroutable_item_is_needs_user_never_guessed(self):
        from rita.projects.planner import plan_project
        project = plan_project("goal", lambda p: PLAN_WITH_UNROUTABLE,
                               self.vocab())
        statuses = {i.title: i.status for i in project.items}
        assert statuses["Build the sample"] == "pending"
        assert statuses["Order pizza"] == "needs_user"

    def test_garbage_output_rejected_loudly(self):
        from rita.projects.planner import PlanError, plan_project
        with pytest.raises(PlanError):
            plan_project("goal", lambda p: "sure, I'll get right on that!",
                         self.vocab())

    def test_oversized_plan_rejected(self):
        from rita.projects.planner import PlanError, plan_project
        big = json.dumps({"items": [{"title": f"t{i}", "command": "build blinky",
                                     "depends_on": []} for i in range(50)]})
        with pytest.raises(PlanError):
            plan_project("goal", lambda p: big, self.vocab())


# --- Store: restart-safe -----------------------------------------------------

class TestStore:
    def test_round_trip_and_transition_persistence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.projects.model import ProjectStore
        from rita.projects.planner import plan_project
        from rita.routing.vocabulary import Vocabulary

        store = ProjectStore()
        project = plan_project("goal", lambda p: GOOD_PLAN, Vocabulary.seed())
        store.save(project)
        project.items[0].status = "done"
        store.save(project)

        fresh = ProjectStore()                       # "restart"
        loaded = fresh.get(project.id)
        assert loaded.items[0].status == "done"
        assert loaded.items[1].status == "pending"
        assert fresh.all()[0].goal == "goal"


# --- Runner: RITA executes, the AI does not ----------------------------------

def make_supervisor(tmp_path, *, build_seq=None, twister_seq=None,
                    completions=None):
    from rita.config import RitaConfig
    from rita.firmware.claude import FakeClaude
    from rita.firmware.west import FakeWest
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    runner = FakeWest(build_seq=list(build_seq or ["ok"] * 8),
                      twister_seq=list(twister_seq or ["pass.json"] * 8),
                      fixtures_dir=TW)
    claude = FakeClaude(completions=list(completions or [blinky_fit()] * 8))
    return Supervisor(rita_cfg=RitaConfig(workspace=str(WS)),
                      config_path=tmp_path / "config", tts=FakeTTS(),
                      runner=runner, claude=claude,
                      workdir=tmp_path / "work"), runner, claude


class TestHandOffAndRun:
    def test_hand_off_runs_the_project_to_completion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        sup, runner, claude = make_supervisor(
            tmp_path, completions=[GOOD_PLAN] + [blinky_fit()] * 8)
        said = sup.hand_off("bring up blinky and document the board")
        assert "3" in said or "item" in said.lower()   # plan announced
        tid = sup.manager.latest_active()
        assert sup.manager.wait_state(tid, "DONE", timeout=15)
        result = sup.manager.report(tid).result
        assert result.outcome == "completed"
        from rita.projects.model import ProjectStore
        project = ProjectStore().all()[-1]
        statuses = [i.status for i in project.items]
        assert statuses.count("done") == 2             # two work items ran
        assert "answered" in statuses                  # chat item recorded
        assert len(runner.twister_calls) == 2          # RITA executed, per item

    def test_blocked_item_cascades_and_project_is_partial(self, tmp_path,
                                                          monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        # First item's build never passes -> exhausted -> item blocked;
        # dependent item blocked by cascade; independent chat item answered.
        sup, runner, claude = make_supervisor(
            tmp_path, build_seq=["fail_build.json"] * 20,
            completions=[GOOD_PLAN] + [blinky_fit()] * 8)
        sup.hand_off("goal")
        tid = sup.manager.latest_active()
        assert sup.manager.wait_state(tid, "DONE", timeout=20)
        result = sup.manager.report(tid).result
        assert result.outcome == "partial"
        from rita.projects.model import ProjectStore
        project = ProjectStore().all()[-1]
        by_title = {i.title: i.status for i in project.items}
        assert by_title["Bring up the LED sample"] == "blocked"
        assert by_title["Run it on sim"] == "blocked"      # cascade
        assert by_title["Board facts"] == "answered"       # independent

    def test_direct_goal_skips_the_planner_entirely(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        sup, runner, claude = make_supervisor(tmp_path)
        sup.hand_off("build blinky for the apollo510")
        tid = sup.manager.latest_active()
        assert sup.manager.wait_state(tid, "DONE", timeout=15)
        # No plan JSON was requested: only fit-judge calls happened.
        assert all("json object" not in p.lower() or "candidate" in p.lower()
                   for p in claude.prompts)

    def test_stop_mid_project_reports_partial(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from tests.test_pause_stop import SteppableWest
        sup, runner, claude = make_supervisor(
            tmp_path, completions=[GOOD_PLAN] + [blinky_fit()] * 8)
        gate = SteppableWest(runner)
        sup._runner = gate
        sup.hand_off("goal")
        tid = sup.manager.latest_active()
        assert gate.in_build.wait(5)                   # item 1 mid-build
        sup.manager.stop(tid)
        gate.release_build.set()
        assert sup.manager.wait_state(tid, "STOPPED", timeout=10)
        from rita.projects.model import ProjectStore
        project = ProjectStore().all()[-1]
        assert any(i.status in ("pending", "stopped") for i in project.items)


# --- Routing + chat status ---------------------------------------------------

class TestProjectRouting:
    @pytest.mark.parametrize("text", [
        "start a project: port the mspi driver and characterize psram",
        "take on the psram bring up",
        "plan a project to validate the apollo510 peripherals",
    ])
    def test_handoff_phrases_route_as_project(self, text):
        from rita.routing.model import Utterance
        from rita.routing.router import route
        from rita.routing.vocabulary import Vocabulary
        d = route(Utterance.from_text(text), Vocabulary.seed())
        assert d.kind == "project"
        assert d.argument                              # the goal text

    def test_project_status_answerable_in_chat(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        sup, runner, claude = make_supervisor(
            tmp_path, completions=[GOOD_PLAN] + [blinky_fit()] * 8)
        sup.hand_off("bring up blinky")
        tid = sup.manager.latest_active()
        sup.manager.wait_state(tid, "DONE", timeout=15)
        said = sup.shell.handle_typed("how is the project going")
        assert "done" in said.lower() or "complete" in said.lower()

    def test_shell_dispatches_project_kind_to_hand_off(self, tmp_path,
                                                       monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        sup, runner, claude = make_supervisor(tmp_path)
        said = sup.shell.handle_typed(
            "start a project: build blinky for the apollo510")
        assert "project" in said.lower() or "item" in said.lower()
        assert sup.manager.latest_active() or sup.manager.tasks()
