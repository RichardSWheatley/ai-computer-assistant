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


# The static gate applies to code RITA writes, so the gate tests use the
# authored-tests path (no index match -> the coder writes the suite).
AUTHORED_TEST_FILES = json.dumps({
    "testcase.yaml": "tests:\n  app.mspi.psram:\n    tags: mspi psram\n    harness: ztest\n",
    "src/main.c": "#include <zephyr/ztest.h>\n",
    "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\n",
    "prj.conf": "CONFIG_ZTEST=y\n",
})


def make_pipeline(tmp_path, *, static_seq=(), build_seq=("ok",),
                  twister_seq=("pass.json",), max_cycles=3,
                  cerberus_configured=True):
    from rita.config import RitaConfig
    from rita.firmware.coder import FakeCoder
    from rita.firmware.index import VerificationIndex
    from rita.firmware.pipeline import IteratePipeline
    from rita.firmware.static_check import FakeCerberus
    from rita.firmware.west import FakeWest

    runner = FakeWest(build_seq=list(build_seq), twister_seq=list(twister_seq),
                      fixtures_dir=TW)
    coder = FakeCoder(completions=[AUTHORED_TEST_FILES])
    checker = FakeCerberus(script=list(static_seq)) if cerberus_configured else None
    cfg = RitaConfig(workspace=str(WS), max_patch_cycles=max_cycles)
    pipe = IteratePipeline(runner=runner, coder=coder,
                           index=VerificationIndex.build(WS), cfg=cfg,
                           workdir=tmp_path / "work", static_checker=checker)
    return pipe, runner, coder, checker


def run(pipe):
    return pipe.run(goal="verify mspi psram", board="apollo510_evb",
                    terms=["mspi", "psram"])


class TestStaticGate:
    def test_clean_static_is_green_without_the_coder(self, tmp_path):
        pipe, runner, coder, checker = make_pipeline(
            tmp_path, static_seq=["clean"])
        report = run(pipe)
        assert report.outcome == "green"
        stages = {s.stage: s.outcome for s in report.stages}
        assert stages["STATIC"] == "green"
        assert coder.patches == []

    def test_findings_are_patched_then_repassed(self, tmp_path):
        pipe, runner, coder, checker = make_pipeline(
            tmp_path, static_seq=["findings", "clean"])
        report = run(pipe)
        assert report.outcome == "green"
        assert len(coder.patches) == 1
        assert coder.patches[0].kind == "static"
        assert "uninitialized" in coder.patches[0].log_excerpt
        assert checker.calls == 2                       # re-checked after patch

    def test_persistent_findings_exhaust_and_build_never_runs(self, tmp_path):
        pipe, runner, coder, checker = make_pipeline(
            tmp_path, static_seq=["findings"] * 10, max_cycles=3)
        report = run(pipe)
        assert report.outcome == "retries_exhausted"
        static = next(s for s in report.stages if s.stage == "STATIC")
        assert static.outcome == "retries_exhausted"
        assert static.failures
        assert runner.build_calls == []                 # gate held the line
        assert len(coder.patches) == 3

    def test_sim_patch_reenters_at_static(self, tmp_path):
        # code -> static ok -> build ok -> sim FAIL -> patch -> STATIC again
        pipe, runner, coder, checker = make_pipeline(
            tmp_path, static_seq=["clean", "clean"],
            build_seq=["ok", "ok"],
            twister_seq=["fail_test.json", "pass.json"])
        report = run(pipe)
        assert report.outcome == "green"
        assert checker.calls == 2                       # once per code version
        kinds = [p.kind for p in coder.patches]
        assert kinds == ["test"]

    def test_unconfigured_checker_is_skipped_never_silent(self, tmp_path):
        pipe, runner, coder, checker = make_pipeline(
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


class TestDeepModeIsAdditive:
    """The owner: CERBERUS should ALWAYS scan; the LLM step is an
    option on top, never an either/or."""

    class _FakeCli:
        def __init__(self, ok, findings=()):
            self.ok_result = ok
            self.findings = findings
            self.calls = 0

        def check(self, target):
            self.calls += 1
            from rita.firmware.static_check import StaticResult
            return StaticResult(ok=self.ok_result,
                                findings=tuple(self.findings))

    def test_deep_runs_scan_first_then_analyze(self):
        from rita.firmware.cerberus_setup import ScanPlusAnalyze
        scan = self._FakeCli(ok=True)
        analyze = self._FakeCli(ok=True)
        result = ScanPlusAnalyze(scan, analyze).check("dir")
        assert result.ok is True
        assert scan.calls == 1 and analyze.calls == 1

    def test_scan_findings_short_circuit_the_llm(self):
        from rita.firmware.coder import FailureArtifact
        from rita.firmware.cerberus_setup import ScanPlusAnalyze
        finding = FailureArtifact(kind="static", suite="", platform="",
                                  reason="bad", log_excerpt="bad",
                                  file_hints=("a.c",))
        scan = self._FakeCli(ok=False, findings=[finding])
        analyze = self._FakeCli(ok=True)
        result = ScanPlusAnalyze(scan, analyze).check("dir")
        assert result.ok is False
        assert analyze.calls == 0        # deterministic gate first
        assert result.findings == (finding,)

    def test_clean_scan_surfaces_analyze_findings(self):
        from rita.firmware.coder import FailureArtifact
        from rita.firmware.cerberus_setup import ScanPlusAnalyze
        finding = FailureArtifact(kind="static", suite="", platform="",
                                  reason="llm", log_excerpt="llm found it",
                                  file_hints=("b.c",))
        scan = self._FakeCli(ok=True)
        analyze = self._FakeCli(ok=False, findings=[finding])
        result = ScanPlusAnalyze(scan, analyze).check("dir")
        assert result.ok is False
        assert "llm found it" in result.findings[0].log_excerpt

    def test_default_checker_deep_is_scan_plus_analyze(self, tmp_path):
        from rita.firmware.cerberus_setup import (ScanPlusAnalyze,
                                                  default_checker)
        checker = default_checker(tmp_path, deep=True)
        assert isinstance(checker, ScanPlusAnalyze)


class TestSupervisorWiring:
    def test_supervisor_builds_checker_from_config(self, tmp_path,
                                                   monkeypatch):
        # Isolate: a machine (or dev box) WITH ~/.rita/cerberus must not
        # change what this test observes.
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
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
