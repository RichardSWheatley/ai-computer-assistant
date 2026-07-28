"""Fix 3: the iterate loop belongs to the orchestrator.

Bounded retries, sim-first, twister.json as the only gate truth, Claude
invoked exactly once per concrete failure artifact — all proven here with
FakeWest + FakeClaude + fixture twister.json files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"

GOOD_TEST_FILES = {
    "testcase.yaml": ("tests:\n  app.watchdog.custom:\n    tags: watchdog\n"
                      "    harness: ztest\n"),
    "src/main.c": "#include <zephyr/ztest.h>\n",
    "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\n",
    "prj.conf": "CONFIG_ZTEST=y\n",
}


# --- twister.json parsing (the only gate truth) ------------------------------

class TestTwisterResults:
    def test_pass(self):
        from rita.firmware.twister_results import parse_twister_json
        r = parse_twister_json(TW / "pass.json")
        assert r.ok is True
        assert r.failures == ()

    def test_build_failure_is_compile_kind_with_file_hints(self):
        from rita.firmware.twister_results import parse_twister_json
        r = parse_twister_json(TW / "fail_build.json")
        assert r.ok is False
        f = r.failures[0]
        assert f.kind == "compile"
        assert "led0" in f.log_excerpt
        assert any("main.c" in h for h in f.file_hints)

    def test_test_failure_is_test_kind(self):
        from rita.firmware.twister_results import parse_twister_json
        r = parse_twister_json(TW / "fail_test.json")
        assert r.ok is False
        f = r.failures[0]
        assert f.kind == "test"
        assert f.suite == "sample.basic.blinky"


# --- Pipeline harness --------------------------------------------------------

def make_pipeline(tmp_path, *, build_seq=(), twister_seq=(), device_seq=(),
                  max_cycles=3, device=False, hw_map=None, completions=None):
    from rita.config import RitaConfig
    from rita.firmware.claude import FakeClaude
    from rita.firmware.index import VerificationIndex
    from rita.firmware.pipeline import IteratePipeline
    from rita.firmware.west import FakeWest

    runner = FakeWest(build_seq=list(build_seq), twister_seq=list(twister_seq),
                      device_seq=list(device_seq), fixtures_dir=TW)
    claude = FakeClaude(completions=list(completions or []))
    cfg = RitaConfig(workspace=str(WS), max_patch_cycles=max_cycles,
                     device_tier_enabled=device,
                     hardware_map=str(hw_map) if hw_map else None)
    pipe = IteratePipeline(runner=runner, claude=claude,
                           index=VerificationIndex.build(WS), cfg=cfg,
                           workdir=tmp_path / "work")
    return pipe, runner, claude


def blinky_fit(prompt: str) -> str:
    return json.dumps({"fit": "sample.basic.blinky", "reason": "fits"})


class TestIteratePipeline:
    def test_green_first_try_no_claude(self, tmp_path):
        pipe, runner, claude = make_pipeline(
            tmp_path, build_seq=["ok"], twister_seq=["pass.json"],
            completions=[blinky_fit("")])
        report = pipe.run(goal="blink the led", board="apollo510_evb",
                          terms=["led", "blinky"])
        assert report.outcome == "green"
        assert claude.patches == []                    # never invoked
        stages = {s.stage: s.outcome for s in report.stages}
        assert stages["UNIT_TEST"] == "skipped"        # no authored code
        assert stages["FINAL_TEST"] == "green"         # the Zephyr suite ran
        assert stages["DEVICE"] == "blocked"           # tier off, never faked

    def test_compile_fail_patch_then_green(self, tmp_path):
        pipe, runner, claude = make_pipeline(
            tmp_path, build_seq=["fail_build.json", "ok"],
            twister_seq=["pass.json"], completions=[blinky_fit("")])
        report = pipe.run(goal="blink the led", board="apollo510_evb",
                          terms=["led", "blinky"])
        assert report.outcome == "green"
        assert len(claude.patches) == 1
        assert claude.patches[0].kind == "compile"
        assert "led0" in claude.patches[0].log_excerpt  # concrete artifact in

    def test_retries_exhausted_is_reported_not_hidden(self, tmp_path):
        pipe, runner, claude = make_pipeline(
            tmp_path, build_seq=["fail_build.json"] * 10,
            max_cycles=3, completions=[blinky_fit("")])
        report = pipe.run(goal="blink the led", board="apollo510_evb",
                          terms=["led", "blinky"])
        assert report.outcome == "retries_exhausted"
        assert len(claude.patches) == 3                # budget honored exactly
        final = next(s for s in report.stages if s.stage == "FINAL_TEST")
        assert final.outcome == "retries_exhausted"
        assert final.failures                          # failure attached

    def test_sim_test_fail_patch_then_green(self, tmp_path):
        pipe, runner, claude = make_pipeline(
            tmp_path, build_seq=["ok", "ok"],
            twister_seq=["fail_test.json", "pass.json"],
            completions=[blinky_fit("")])
        report = pipe.run(goal="blink the led", board="apollo510_evb",
                          terms=["led", "blinky"])
        assert report.outcome == "green"
        assert len(claude.patches) == 1
        assert claude.patches[0].kind == "test"

    def test_sim_green_precedes_device_and_blocked_tier_never_runs_device(self, tmp_path):
        pipe, runner, claude = make_pipeline(
            tmp_path, build_seq=["ok"], twister_seq=["pass.json"],
            completions=[blinky_fit("")])
        pipe.run(goal="blink", board="apollo510_evb", terms=["led", "blinky"])
        assert runner.device_calls == []               # no device attempt

    def test_device_tier_enabled_generates_map_when_missing(self, tmp_path):
        pipe, runner, claude = make_pipeline(
            tmp_path, build_seq=["ok"], twister_seq=["pass.json"],
            device_seq=["pass.json"], device=True, hw_map=None,
            completions=[blinky_fit("")])
        report = pipe.run(goal="blink", board="apollo510_evb",
                          terms=["led", "blinky"])
        assert runner.generated_maps == 1              # never hardcoded ports
        assert runner.device_calls and runner.device_calls[0]["hardware_map"]
        assert report.outcome == "green"
        assert next(s for s in report.stages if s.stage == "DEVICE").outcome == "green"

    def test_no_match_authors_test_then_twister_gates_it(self, tmp_path):
        pipe, runner, claude = make_pipeline(
            tmp_path, build_seq=["ok"], twister_seq=["pass.json"],
            completions=[json.dumps(GOOD_TEST_FILES)])
        report = pipe.run(goal="verify the watchdog fires",
                          board="apollo510_evb", terms=["watchdog"])
        assert report.outcome == "green"
        resolve = next(s for s in report.stages if s.stage == "RESOLVE")
        assert "written" in resolve.detail
        # twister ran against the authored suite, not a workspace sample
        suite = Path(runner.twister_calls[0]["testsuite"])
        assert (suite / "testcase.yaml").exists()
        assert "watchdog" in (suite / "testcase.yaml").read_text()

    def test_patch_requires_a_concrete_failure(self):
        from rita.firmware.claude import FakeClaude
        with pytest.raises(ValueError):
            FakeClaude().patch(None, Path("."))


# --- Router work dispatch -> pipeline ---------------------------------------

class TestWorkDispatch:
    def test_build_dispatch_runs_pipeline_and_reports(self, tmp_path):
        from rita.firmware.pipeline import handle_work_dispatch
        from rita.routing.model import Utterance
        from rita.routing.router import route
        from rita.routing.vocabulary import Vocabulary

        pipe, runner, claude = make_pipeline(
            tmp_path, build_seq=["ok"], twister_seq=["pass.json"],
            completions=[blinky_fit("")])
        d = route(Utterance.from_text("build blinky for the apollo510"),
                  Vocabulary.seed())
        said = handle_work_dispatch(d, pipe)
        assert "green" in said.lower() or "passed" in said.lower()
        assert runner.twister_calls                    # the gate actually ran
