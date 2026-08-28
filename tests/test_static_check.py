"""The CERBERUS static-check gate: code -> STATIC -> build -> test."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"


def blinky_fit(_p: str = "") -> str:
    return json.dumps({"fit": "sample.basic.blinky", "reason": "fits"})


def make_pipeline(tmp_path, *, static_seq=(), build_seq=("ok",),
                  twister_seq=("pass.json",), max_cycles=3,
                  cerberus_configured=True):
    from rita.config import RitaConfig
    from rita.firmware.claude import FakeClaude
    from rita.firmware.index import VerificationIndex
    from rita.firmware.pipeline import IteratePipeline
    from rita.firmware.static_check import FakeCerberus
    from rita.firmware.west import FakeWest

    runner = FakeWest(build_seq=list(build_seq), twister_seq=list(twister_seq),
                      fixtures_dir=TW)
    claude = FakeClaude(completions=[blinky_fit()])
    checker = FakeCerberus(script=list(static_seq)) if cerberus_configured else None
    cfg = RitaConfig(workspace=str(WS), max_patch_cycles=max_cycles)
    pipe = IteratePipeline(runner=runner, claude=claude,
                           index=VerificationIndex.build(WS), cfg=cfg,
                           workdir=tmp_path / "work", static_checker=checker)
    return pipe, runner, claude, checker


def run(pipe):
    return pipe.run(goal="blink the led", board="apollo510_evb",
                    terms=["led", "blinky"])


class TestStaticGate:
    def test_clean_static_is_green_without_claude(self, tmp_path):
        pipe, runner, claude, checker = make_pipeline(
            tmp_path, static_seq=["clean"])
        report = run(pipe)
        assert report.outcome == "green"
        stages = {s.stage: s.outcome for s in report.stages}
        assert stages["STATIC"] == "green"
        assert claude.patches == []

    def test_findings_are_patched_then_repassed(self, tmp_path):
        pipe, runner, claude, checker = make_pipeline(
            tmp_path, static_seq=["findings", "clean"])
        report = run(pipe)
        assert report.outcome == "green"
        assert len(claude.patches) == 1
        assert claude.patches[0].kind == "static"
        assert "uninitialized" in claude.patches[0].log_excerpt
        assert checker.calls == 2                       # re-checked after patch

    def test_persistent_findings_exhaust_and_build_never_runs(self, tmp_path):
        pipe, runner, claude, checker = make_pipeline(
            tmp_path, static_seq=["findings"] * 10, max_cycles=3)
        report = run(pipe)
        assert report.outcome == "retries_exhausted"
        static = next(s for s in report.stages if s.stage == "STATIC")
        assert static.outcome == "retries_exhausted"
        assert static.failures
        assert runner.build_calls == []                 # gate held the line
        assert len(claude.patches) == 3

    def test_sim_patch_reenters_at_static(self, tmp_path):
        # code -> static ok -> build ok -> sim FAIL -> patch -> STATIC again
        pipe, runner, claude, checker = make_pipeline(
            tmp_path, static_seq=["clean", "clean"],
            build_seq=["ok", "ok"],
            twister_seq=["fail_test.json", "pass.json"])
        report = run(pipe)
        assert report.outcome == "green"
        assert checker.calls == 2                       # once per code version
        kinds = [p.kind for p in claude.patches]
        assert kinds == ["test"]

    def test_unconfigured_checker_is_skipped_never_silent(self, tmp_path):
        pipe, runner, claude, checker = make_pipeline(
            tmp_path, cerberus_configured=False)
        report = run(pipe)
        assert report.outcome == "green"
        static = next(s for s in report.stages if s.stage == "STATIC")
        assert static.outcome == "skipped"
        assert "not configured" in static.detail.lower()


class TestCerberusCli:
    """Real subprocess runs against a stand-in cerberus executable."""

    def _fake_cerberus(self, tmp_path, body: str) -> str:
        script = tmp_path / "fake_cerberus.py"
        script.write_text(body)
        return f'"{sys.executable}" "{script}"'

    def test_exit_zero_is_clean(self, tmp_path):
        from rita.firmware.static_check import CerberusCli
        cmd = self._fake_cerberus(tmp_path, "import sys; sys.exit(0)\n")
        result = CerberusCli(cmd).check(tmp_path)
        assert result.ok is True
        assert result.findings == ()

    def test_json_findings_are_parsed(self, tmp_path):
        from rita.firmware.static_check import CerberusCli
        cmd = self._fake_cerberus(tmp_path, (
            "import json, sys\n"
            "print(json.dumps({'findings': [{'file': 'src/main.c',"
            " 'line': 12, 'severity': 'error',"
            " 'message': 'possible null deref'}]}))\n"
            "sys.exit(1)\n"))
        result = CerberusCli(cmd).check(tmp_path)
        assert result.ok is False
        f = result.findings[0]
        assert f.kind == "static"
        assert "null deref" in f.log_excerpt
        assert "src/main.c" in f.file_hints

    def test_non_json_output_still_yields_an_artifact(self, tmp_path):
        from rita.firmware.static_check import CerberusCli
        cmd = self._fake_cerberus(tmp_path, (
            "import sys\n"
            "print('main.c:40: warning: suspicious cast')\n"
            "sys.exit(2)\n"))
        result = CerberusCli(cmd).check(tmp_path)
        assert result.ok is False
        assert "suspicious cast" in result.findings[0].log_excerpt

    def test_target_dir_is_passed_to_the_command(self, tmp_path):
        from rita.firmware.static_check import CerberusCli
        cmd = self._fake_cerberus(tmp_path, (
            "import sys\n"
            "sys.exit(0 if sys.argv[1] else 3)\n"))
        assert CerberusCli(cmd).check(tmp_path).ok is True


class TestSupervisorWiring:
    def test_supervisor_builds_checker_from_config(self, tmp_path):
        from rita.config import RitaConfig
        from rita.firmware.static_check import CerberusCli
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                             cerberus_command="cerberus --json"),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        checker = sup._make_static_checker()
        assert isinstance(checker, CerberusCli)
        sup2 = Supervisor(rita_cfg=RitaConfig(workspace=str(WS)),
                          config_path=tmp_path / "c2", tts=FakeTTS(),
                          workdir=tmp_path / "w2")
        assert sup2._make_static_checker() is None
