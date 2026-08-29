"""The unit-test tier, per the user's definition of TDD:

Code to the goal, then TEST EVERY SINGLE FUNCTION before moving on — its
input and output parameters (valid / boundary / invalid) — with every
function restricting or validating its parameters before executing. Unit
tests are host-run Unity tests, NOT ztest; the Zephyr suites are the
final test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Behavior tests pin the explicit NATIVE override (the documented host_cc
# escape hatch): fast and machine-independent. The default ARM+QEMU path
# is covered end-to-end in test_toolchain.py.
import shutil as _shutil

NATIVE_CC = _shutil.which("cc") or _shutil.which("gcc") or _shutil.which("clang")
MINI_UNITY = FIXTURES / "mini_unity"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"

CLAMP_C = """\
#include "app.h"
int clamp_add(int a, int b) {
    if (a < -1000 || a > 1000) return -1;   /* validate inputs */
    if (b < -1000 || b > 1000) return -1;
    int out = a + b;
    if (out > 1000) out = 1000;             /* restrict output */
    if (out < -1000) out = -1000;
    return out;
}
int scale_by_two(int v) {
    if (v < 0) return -1;
    return v * 2;
}
"""

APP_H = "int clamp_add(int a, int b);\nint scale_by_two(int v);\n"

GOOD_TESTS_C = """\
#include "unity.h"
#include "app.h"
void test_clamp_add_valid(void) { TEST_ASSERT_EQUAL_INT(5, clamp_add(2, 3)); }
void test_clamp_add_rejects_out_of_range(void) { TEST_ASSERT_EQUAL_INT(-1, clamp_add(5000, 1)); }
void test_clamp_add_restricts_output(void) { TEST_ASSERT_EQUAL_INT(1000, clamp_add(900, 900)); }
void test_scale_by_two_valid(void) { TEST_ASSERT_EQUAL_INT(8, scale_by_two(4)); }
void test_scale_by_two_rejects_negative(void) { TEST_ASSERT_EQUAL_INT(-1, scale_by_two(-2)); }
int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_clamp_add_valid);
    RUN_TEST(test_clamp_add_rejects_out_of_range);
    RUN_TEST(test_clamp_add_restricts_output);
    RUN_TEST(test_scale_by_two_valid);
    RUN_TEST(test_scale_by_two_rejects_negative);
    return UNITY_END();
}
"""

FAILING_TESTS_C = GOOD_TESTS_C.replace(
    "TEST_ASSERT_EQUAL_INT(5, clamp_add(2, 3))",
    "TEST_ASSERT_EQUAL_INT(6, clamp_add(2, 3))")


def make_app(tmp_path, tests_c: str | None = GOOD_TESTS_C) -> Path:
    app = tmp_path / "app"
    (app / "src").mkdir(parents=True)
    (app / "src" / "app.c").write_text(CLAMP_C)
    (app / "src" / "app.h").write_text(APP_H)
    (app / "src" / "main.c").write_text('#include "app.h"\nint main(void){return clamp_add(1,2)>=0?0:1;}\n')
    if tests_c is not None:
        (app / "tests" / "unit").mkdir(parents=True)
        (app / "tests" / "unit" / "test_app.c").write_text(tests_c)
    return app


# --- Function discovery + per-function completeness --------------------------

class TestFunctionScan:
    def test_lists_every_function_skipping_main(self, tmp_path):
        from rita.firmware.functions import list_functions
        app = make_app(tmp_path)
        names = {f.name for f in list_functions(app / "src")}
        assert names == {"clamp_add", "scale_by_two"}      # main excluded

    def test_untested_functions_named_exactly(self, tmp_path):
        from rita.firmware.functions import untested_functions
        app = make_app(tmp_path, tests_c=GOOD_TESTS_C.replace("scale_by_two", "clamp_add"))
        missing = untested_functions(app / "src", app / "tests" / "unit")
        assert [f.name for f in missing] == ["scale_by_two"]

    def test_full_coverage_is_empty(self, tmp_path):
        from rita.firmware.functions import untested_functions
        app = make_app(tmp_path)
        assert untested_functions(app / "src", app / "tests" / "unit") == []

    def test_no_tests_dir_means_everything_untested(self, tmp_path):
        from rita.firmware.functions import untested_functions
        app = make_app(tmp_path, tests_c=None)
        assert len(untested_functions(app / "src", app / "tests" / "unit")) == 2


# --- Host Unity runner (REAL cc) ---------------------------------------------

class TestHostUnity:
    def test_green_suite_passes(self, tmp_path):
        from rita.firmware.unity import HostUnity
        app = make_app(tmp_path)
        result = HostUnity(unity_src=MINI_UNITY, cc=NATIVE_CC).run(app / "src",
                                                     app / "tests" / "unit")
        assert result.ok is True
        assert result.passed == 5 and result.failed == 0

    def test_failing_assertion_is_a_parsed_artifact(self, tmp_path):
        from rita.firmware.unity import HostUnity
        app = make_app(tmp_path, tests_c=FAILING_TESTS_C)
        result = HostUnity(unity_src=MINI_UNITY, cc=NATIVE_CC).run(app / "src",
                                                     app / "tests" / "unit")
        assert result.ok is False
        f = result.failures[0]
        assert f.kind == "unit"
        assert "test_clamp_add_valid" in f.log_excerpt
        assert any("test_app.c" in h for h in f.file_hints)

    def test_compile_error_is_a_concrete_artifact(self, tmp_path):
        from rita.firmware.unity import HostUnity
        app = make_app(tmp_path, tests_c='#include "unity.h"\nthis is not C\n')
        result = HostUnity(unity_src=MINI_UNITY, cc=NATIVE_CC).run(app / "src",
                                                     app / "tests" / "unit")
        assert result.ok is False
        assert result.failures[0].kind == "unit"

    def test_missing_compiler_is_honestly_unavailable(self, tmp_path):
        from rita.firmware.unity import HostUnity
        app = make_app(tmp_path)
        result = HostUnity(unity_src=MINI_UNITY, cc="/no/such/cc").run(
            app / "src", app / "tests" / "unit")
        assert result.ok is False
        assert result.unavailable
        assert "compiler" in result.reason.lower()


# --- Compiler discovery: host PATH first, then the Zephyr SDK ----------------

class TestCompilerDiscovery:
    """The unit tier's compiler comes from the ARM toolchain resolver —
    Zephyr's compiler family — never an unrelated native compiler."""

    def test_default_delegates_to_the_arm_toolchain(self, monkeypatch,
                                                    tmp_path):
        from rita.firmware import toolchain, unity
        monkeypatch.setattr(
            toolchain, "detect_arm_gcc",
            lambda: toolchain.ToolchainInfo(
                cc=str(tmp_path / "arm-none-eabi-gcc"), source="path",
                root=str(tmp_path)))
        info = unity.find_compiler(None)
        assert info.source == "arm"
        assert "arm-none-eabi-gcc" in info.path

    def test_explicit_native_override_wins(self, tmp_path):
        from rita.firmware.unity import find_compiler
        mycc = tmp_path / "mycc"
        mycc.write_text("")
        info = find_compiler(str(mycc))
        assert info.source == "explicit"

    def test_no_toolchain_reason_names_the_install(self, monkeypatch,
                                                   tmp_path):
        from rita.firmware import toolchain, unity
        monkeypatch.setattr(toolchain, "detect_arm_gcc", lambda: None)
        app = make_app(tmp_path)
        result = unity.HostUnity(unity_src=MINI_UNITY).run(
            app / "src", app / "tests" / "unit")
        assert result.unavailable
        assert "arm-none-eabi-gcc" in result.reason
        assert "toolchain" in result.reason.lower()

    def test_missing_qemu_is_reported_not_faked(self, monkeypatch, tmp_path):
        from rita.firmware import toolchain, unity
        monkeypatch.setattr(
            toolchain, "detect_arm_gcc",
            lambda: toolchain.ToolchainInfo(cc="/x/arm-none-eabi-gcc",
                                            source="path", root="/x"))
        monkeypatch.setattr(toolchain, "detect_qemu", lambda: None)
        app = make_app(tmp_path)
        result = unity.HostUnity(unity_src=MINI_UNITY).run(
            app / "src", app / "tests" / "unit")
        assert result.unavailable
        assert "qemu" in result.reason.lower()


# --- Unity acquisition -------------------------------------------------------

@pytest.fixture()
def unity_fixture_repo(tmp_path) -> Path:
    repo = tmp_path / "unity-src"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "unity.c").write_text((MINI_UNITY / "unity.c").read_text())
    (repo / "src" / "unity.h").write_text((MINI_UNITY / "unity.h").read_text())
    import os
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"],
                ["git", "-c", "user.name=t", "-c", "user.email=t@t",
                 "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=repo, check=True,
                       env={"PATH": os.environ["PATH"]})
    return repo


class TestUnityAcquisition:
    def test_install_and_detect(self, unity_fixture_repo, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.firmware.unity import detect_unity, install_unity
        res = install_unity(url=str(unity_fixture_repo))
        assert res.ok
        found = detect_unity()
        assert found is not None
        assert (found / "unity.h").exists()      # points at the src dir

    def test_cerberus_clone_unity_layout_detected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.firmware.unity import detect_unity
        cerb_unity = tmp_path / "rita" / "cerberus" / "unity" / "src"
        cerb_unity.mkdir(parents=True)
        (cerb_unity / "unity.h").write_text("x")
        (cerb_unity / "unity.c").write_text("x")
        assert detect_unity() == cerb_unity

    def test_absent_is_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.firmware.unity import detect_unity
        assert detect_unity() is None


# --- Unit-test authorship ----------------------------------------------------

class TestWriteUnityTests:
    def fn_sigs(self):
        from rita.firmware.functions import FunctionSig
        return [FunctionSig("clamp_add", "src/app.c", 2),
                FunctionSig("scale_by_two", "src/app.c", 10)]

    def test_valid_output_written(self, tmp_path):
        from rita.firmware.testwriter import write_unity_tests
        files = {"test_app.c": GOOD_TESTS_C}
        written = write_unity_tests("clamp and scale", self.fn_sigs(),
                                    tmp_path / "unit",
                                    lambda p: json.dumps(files))
        assert (tmp_path / "unit" / "test_app.c").exists()

    def test_missing_function_coverage_rejected(self, tmp_path):
        from rita.firmware.testwriter import write_unity_tests
        files = {"test_app.c": GOOD_TESTS_C.replace("scale_by_two", "clamp_add")}
        with pytest.raises(ValueError):
            write_unity_tests("x", self.fn_sigs(), tmp_path / "unit",
                              lambda p: json.dumps(files))

    def test_ztest_shaped_output_rejected(self, tmp_path):
        from rita.firmware.testwriter import write_unity_tests
        files = {"test_app.c": "#include <zephyr/ztest.h>\nZTEST_SUITE(x,0,0,0,0,0);"}
        with pytest.raises(ValueError):
            write_unity_tests("x", self.fn_sigs(), tmp_path / "unit",
                              lambda p: json.dumps(files))

    def test_prompt_names_every_function_and_the_contract(self, tmp_path):
        from rita.firmware.testwriter import write_unity_tests
        prompts = []

        def complete(p):
            prompts.append(p)
            return json.dumps({"test_app.c": GOOD_TESTS_C})

        write_unity_tests("goal", self.fn_sigs(), tmp_path / "unit", complete)
        assert "clamp_add" in prompts[0] and "scale_by_two" in prompts[0]
        assert "input" in prompts[0].lower() and "output" in prompts[0].lower()


# --- Pipeline integration: code -> STATIC -> UNIT_TEST -> FINAL_TEST ---------

UNITY_FILES_FOR_FAKE = json.dumps({"test_app.c": (
    '#include "unity.h"\n'
    "void test_fake_helper_valid(void) {}\n"
    "void test_fake_helper_rejects_negative(void) {}\n"
    "int main(void) { UNITY_BEGIN(); return UNITY_END(); }\n")})


def make_scaffold_pipeline(tmp_path, *, unit_seq=("green",), static_seq=None,
                           twister_seq=("pass.json",), max_cycles=3):
    from rita.config import RitaConfig
    from rita.firmware.coder import FakeCoder
    from rita.firmware.index import VerificationIndex
    from rita.firmware.pipeline import IteratePipeline
    from rita.firmware.static_check import FakeCerberus
    from rita.firmware.unity import FakeUnity
    from rita.firmware.west import FakeWest

    runner = FakeWest(build_seq=["ok"] * 6, twister_seq=list(twister_seq),
                      fixtures_dir=TW)
    fit = json.dumps({"fit": "sample.basic.blinky", "reason": "fits"})
    coder = FakeCoder(completions=[fit, UNITY_FILES_FOR_FAKE])
    unity = FakeUnity(script=list(unit_seq))
    checker = FakeCerberus(script=list(static_seq)) if static_seq else None
    cfg = RitaConfig(workspace=str(WS), max_patch_cycles=max_cycles,
                     applications_dir=str(tmp_path / "apps"))
    pipe = IteratePipeline(runner=runner, coder=coder,
                           index=VerificationIndex.build(WS), cfg=cfg,
                           workdir=tmp_path / "work", static_checker=checker,
                           unit_runner=unity)
    return pipe, runner, coder, unity


def run_scaffold(pipe):
    return pipe.run(goal="an led helper app", board="apollo510_evb",
                    terms=["led", "blinky"], scaffold=True)


class TestPipelineUnitStage:
    def test_stage_order_and_authorship(self, tmp_path):
        pipe, runner, coder, unity = make_scaffold_pipeline(tmp_path)
        report = run_scaffold(pipe)
        assert report.outcome == "green"
        names = [s.stage for s in report.stages]
        assert names.index("UNIT_TEST") < names.index("FINAL_TEST")
        # Unit tests were authored to cover fake_helper, then run green once.
        assert any("fake_helper" in p for p in coder.prompts)  # named in brief
        app_dir = Path(coder.scaffolds_dirs[0])
        assert (app_dir / "tests" / "unit" / "test_app.c").exists()
        assert unity.calls == 1
        # The final test (Zephyr suite) ran under twister.
        assert runner.twister_calls

    def test_unit_red_patches_and_reenters_static(self, tmp_path):
        pipe, runner, coder, unity = make_scaffold_pipeline(
            tmp_path, unit_seq=("red", "green"),
            static_seq=["clean", "clean"])
        report = run_scaffold(pipe)
        assert report.outcome == "green"
        assert [p.kind for p in coder.patches] == ["unit"]
        assert unity.calls == 2                    # re-run after the patch
        # STATIC ran once per code version (patch re-entered the gate).
        static_greens = [s for s in report.stages
                        if s.stage == "STATIC" and s.outcome == "green"]
        assert len(static_greens) == 2

    def test_unit_exhaustion_is_reported_and_final_never_runs(self, tmp_path):
        pipe, runner, coder, unity = make_scaffold_pipeline(
            tmp_path, unit_seq=["red"] * 10, max_cycles=2)
        report = run_scaffold(pipe)
        assert report.outcome == "retries_exhausted"
        unit = next(s for s in report.stages if s.stage == "UNIT_TEST")
        assert unit.outcome == "retries_exhausted"
        assert runner.twister_calls == []          # final test held back

    def test_sample_run_skips_unit_stage_visibly(self, tmp_path):
        from rita.firmware.pipeline import IteratePipeline
        pipe, runner, coder, unity = make_scaffold_pipeline(tmp_path)
        report = pipe.run(goal="blink the led", board="apollo510_evb",
                          terms=["led", "blinky"], scaffold=False)
        unit = next(s for s in report.stages if s.stage == "UNIT_TEST")
        assert unit.outcome == "skipped"
        assert "nothing RITA-coded" in unit.detail
        assert unity.calls == 0


# --- The contract rule is in the coding brief --------------------------------

class TestContractRule:
    def test_scaffold_brief_carries_the_rule(self):
        # Scaffold is decomposed now — the contract rule must travel
        # with EVERY per-file write call, not a retired whole-app brief.
        from rita.firmware.coder import _WRITE_PROMPT
        text = _WRITE_PROMPT.lower()
        assert "restrict" in text and "validate" in text
        assert "input" in text and "output" in text
