"""Gates and patches apply to code RITA writes — never upstream code.

An unmodified in-tree sample must build without the MISRA gate (stock
Zephyr code doesn't aim for it), and a failing one is a workspace issue
to report — RITA never patches the user's zephyr tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"


def blinky_fit(_p: str = "") -> str:
    return json.dumps({"fit": "sample.basic.blinky", "reason": "fits"})


def make_pipeline(tmp_path, *, static_seq=(), build_seq=("ok",),
                  twister_seq=("pass.json",)):
    from rita.config import RitaConfig
    from rita.firmware.coder import FakeCoder
    from rita.firmware.index import VerificationIndex
    from rita.firmware.pipeline import IteratePipeline
    from rita.firmware.static_check import FakeCerberus
    from rita.firmware.west import FakeWest

    runner = FakeWest(build_seq=list(build_seq), twister_seq=list(twister_seq),
                      fixtures_dir=TW)
    coder = FakeCoder(completions=[blinky_fit()])
    checker = FakeCerberus(script=list(static_seq))
    pipe = IteratePipeline(runner=runner, coder=coder,
                           index=VerificationIndex.build(WS),
                           cfg=RitaConfig(workspace=str(WS)),
                           workdir=tmp_path / "work", static_checker=checker)
    return pipe, runner, coder, checker


def run(pipe):
    return pipe.run(goal="blink the led", board="apollo510_evb",
                    terms=["led", "blinky"])


class TestInTreeSamplesAreNotGated:
    def test_static_gate_skips_unmodified_samples(self, tmp_path):
        # Findings scripted — but the gate must not even LOOK at stock code.
        pipe, runner, coder, checker = make_pipeline(
            tmp_path, static_seq=["findings"] * 10)
        report = run(pipe)
        assert report.outcome == "green"
        static = next(s for s in report.stages if s.stage == "STATIC")
        assert static.outcome == "skipped"
        assert "in-tree" in static.detail.lower()
        assert checker.calls == 0
        assert coder.patches == []

    def test_failing_in_tree_sample_is_reported_never_patched(self, tmp_path):
        pipe, runner, coder, checker = make_pipeline(
            tmp_path, twister_seq=["fail_test.json"] * 10)
        report = run(pipe)
        assert report.outcome == "failed"
        assert coder.patches == []                    # tree never touched
        final = next(s for s in report.stages if s.stage == "FINAL_TEST")
        assert final.outcome == "failed"
        assert "workspace" in final.detail.lower() or \
               "in-tree" in final.detail.lower()
        assert final.failures                          # artifact still shown

    def test_in_tree_build_failure_is_reported_never_patched(self, tmp_path):
        pipe, runner, coder, checker = make_pipeline(
            tmp_path, build_seq=["fail_build.json"] * 10)
        report = run(pipe)
        assert report.outcome == "failed"
        assert coder.patches == []


class TestAuthoredCodeStaysGated:
    def test_scaffold_still_passes_through_the_static_gate(self, tmp_path):
        from rita.config import RitaConfig
        from rita.firmware.coder import FakeCoder
        from rita.firmware.index import VerificationIndex
        from rita.firmware.pipeline import IteratePipeline
        from rita.firmware.static_check import FakeCerberus
        from rita.firmware.west import FakeWest

        test_files = json.dumps({
            "testcase.yaml": "tests:\n  app.x:\n    tags: x\n    harness: ztest\n",
            "src/main.c": "#include <zephyr/ztest.h>\n",
            "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\n",
            "prj.conf": "CONFIG_ZTEST=y\n"})
        runner = FakeWest(build_seq=["ok"] * 4, twister_seq=["pass.json"] * 4,
                          fixtures_dir=TW)
        coder = FakeCoder(completions=[test_files])
        checker = FakeCerberus(script=["findings", "clean"])
        pipe = IteratePipeline(
            runner=runner, coder=coder, index=VerificationIndex.build(WS),
            cfg=RitaConfig(workspace=str(WS),
                           applications_dir=str(tmp_path / "apps")),
            workdir=tmp_path / "work", static_checker=checker)
        report = pipe.run(goal="an example for mspi psram", board="apollo510_evb",
                          terms=["mspi", "psram"], scaffold=True)
        assert report.outcome == "green"
        assert checker.calls == 2                      # gated + re-gated
        assert len(coder.patches) == 1                 # patched the app

    def test_pipeline_refuses_patch_targets_in_upstream_tree(self, tmp_path):
        from rita.firmware.pipeline import IteratePipeline
        from rita.firmware.twister_results import FailureArtifact
        pipe, runner, coder, checker = make_pipeline(tmp_path)
        art = FailureArtifact(kind="test", suite="s", platform="p",
                              reason="r", log_excerpt="x", file_hints=())
        with pytest.raises(RuntimeError, match="upstream"):
            pipe._patch(art, Path(WS) / "zephyr" / "samples" / "basic" / "blinky")
