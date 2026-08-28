"""The ARM toolchain: detected in Zephyr's order, installed by RITA."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
MINI_UNITY = FIXTURES / "mini_unity"


def _fake_gcc(dirpath: Path, name: str = "arm-none-eabi-gcc") -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / name
    p.write_text("")
    return p


class TestDetectionOrder:
    def test_rita_install_wins(self, tmp_path, monkeypatch):
        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        monkeypatch.delenv("GNUARMEMB_TOOLCHAIN_PATH", raising=False)
        own = _fake_gcc(tmp_path / "rita" / "toolchains" / "arm-none-eabi" / "bin")
        monkeypatch.setattr(toolchain.shutil, "which",
                            lambda n: "/elsewhere/arm-none-eabi-gcc")
        info = toolchain.detect_arm_gcc()
        assert info.source == "rita"
        assert info.cc == str(own)

    def test_path_next(self, tmp_path, monkeypatch):
        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        monkeypatch.delenv("GNUARMEMB_TOOLCHAIN_PATH", raising=False)
        monkeypatch.setattr(toolchain.shutil, "which",
                            lambda n: "/usr/bin/arm-none-eabi-gcc"
                            if n == "arm-none-eabi-gcc" else None)
        info = toolchain.detect_arm_gcc()
        assert info.source == "path"
        # Path() normalizes separators per-OS; compare shape-independently.
        assert Path(info.cc).as_posix() == "/usr/bin/arm-none-eabi-gcc"

    def test_gnuarmemb_env_next(self, tmp_path, monkeypatch):
        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        gnu = _fake_gcc(tmp_path / "gnuarm" / "bin")
        monkeypatch.setenv("GNUARMEMB_TOOLCHAIN_PATH", str(tmp_path / "gnuarm"))
        monkeypatch.setattr(toolchain.shutil, "which", lambda n: None)
        info = toolchain.detect_arm_gcc()
        assert info.source == "gnuarmemb"
        assert info.cc == str(gnu)

    def test_zephyr_sdk_last(self, tmp_path, monkeypatch):
        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        monkeypatch.delenv("GNUARMEMB_TOOLCHAIN_PATH", raising=False)
        sdk = tmp_path / "zephyr-sdk-1.0.1"
        (sdk / "sdk_version").parent.mkdir(parents=True)
        (sdk / "sdk_version").write_text("1.0.1")
        _fake_gcc(sdk / "arm-zephyr-eabi" / "bin", "arm-zephyr-eabi-gcc")
        monkeypatch.setenv("ZEPHYR_SDK_INSTALL_DIR", str(sdk))
        monkeypatch.setattr(toolchain.shutil, "which", lambda n: None)
        info = toolchain.detect_arm_gcc()
        assert info.source == "sdk"
        assert "arm-zephyr-eabi-gcc" in info.cc

    def test_unrelated_native_compilers_are_ignored(self, tmp_path,
                                                    monkeypatch):
        # CI runners ship clang/gcc — they are NOT ARM toolchains.
        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        monkeypatch.delenv("GNUARMEMB_TOOLCHAIN_PATH", raising=False)
        monkeypatch.delenv("ZEPHYR_SDK_INSTALL_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setattr(
            toolchain.shutil, "which",
            lambda n: "/usr/bin/clang" if n in ("clang", "gcc", "cc") else None)
        assert toolchain.detect_arm_gcc() is None


class TestInstall:
    def test_install_extracts_and_verifies(self, tmp_path, monkeypatch):
        # A tiny fake release archive stands in for the real download;
        # the extract + locate + verify logic is fully exercised.
        import io
        import tarfile

        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            data = b"#!/bin/sh\necho 'arm-none-eabi-gcc (fake) 13.2'\n"
            info = tarfile.TarInfo("arm-gnu-toolchain-13.2/bin/arm-none-eabi-gcc")
            info.size = len(data)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(data))
        monkeypatch.setattr(toolchain, "_download",
                            lambda url, dest: dest.write_bytes(buf.getvalue()))
        res = toolchain.install_arm_gcc(archive_suffix=".tar.gz")
        assert res.ok, res.detail
        info = toolchain.detect_arm_gcc()
        assert info is not None and info.source == "rita"

    def test_download_failure_is_honest(self, tmp_path, monkeypatch):
        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))

        def boom(url, dest):
            raise OSError("network down")

        monkeypatch.setattr(toolchain, "_download", boom)
        res = toolchain.install_arm_gcc()
        assert res.ok is False
        assert "network down" in res.detail


class TestUnitTierUsesIt:
    def test_find_compiler_resolves_arm_gcc(self, tmp_path, monkeypatch):
        from rita.firmware import toolchain, unity
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        own = _fake_gcc(tmp_path / "rita" / "toolchains" / "arm-none-eabi" / "bin")
        monkeypatch.delenv("GNUARMEMB_TOOLCHAIN_PATH", raising=False)
        monkeypatch.setattr(toolchain.shutil, "which", lambda n: None)
        info = unity.find_compiler(None)
        assert info is not None
        assert info.source == "arm"
        assert info.path == str(own)

    def test_missing_toolchain_reason_names_the_install(self, tmp_path,
                                                        monkeypatch):
        from rita.firmware import toolchain, unity
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        monkeypatch.delenv("GNUARMEMB_TOOLCHAIN_PATH", raising=False)
        monkeypatch.delenv("ZEPHYR_SDK_INSTALL_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setattr(toolchain.shutil, "which", lambda n: None)
        reason = unity.no_compiler_reason()
        assert "arm-none-eabi-gcc" in reason
        assert "toolchain" in reason.lower()
        assert "llvm" not in reason.lower() and "mingw" not in reason.lower()


NEED_REAL = not (shutil.which("arm-none-eabi-gcc")
                 and shutil.which("qemu-system-arm"))


@pytest.mark.skipif(NEED_REAL, reason="needs arm-none-eabi-gcc + qemu")
class TestRealArmRun:
    """The proven recipe, end to end: ARM compile, QEMU semihosting run,
    Unity output parsed — failures detected, never silently green."""

    def _app(self, tmp_path):
        src = tmp_path / "app" / "src"
        tests = tmp_path / "app" / "tests" / "unit"
        src.mkdir(parents=True)
        tests.mkdir(parents=True)
        (src / "app.h").write_text("int clamp_add(int a, int b);\n")
        (src / "app.c").write_text(
            '#include "app.h"\n'
            "int clamp_add(int a, int b) {\n"
            "    if (a < -1000 || a > 1000) return -1;\n"
            "    if (b < -1000 || b > 1000) return -1;\n"
            "    int out = a + b;\n"
            "    if (out > 1000) out = 1000;\n"
            "    return out;\n}\n")
        return tmp_path / "app", tests

    def test_green_suite_passes_under_qemu(self, tmp_path):
        from rita.firmware.unity import UnitRunner
        app, tests = self._app(tmp_path)
        (tests / "test_app.c").write_text(
            '#include "unity.h"\n#include "app.h"\n'
            "void test_valid(void) { TEST_ASSERT_EQUAL_INT(5, clamp_add(2, 3)); }\n"
            "void test_reject(void) { TEST_ASSERT_EQUAL_INT(-1, clamp_add(5000, 1)); }\n"
            "int main(void) { UNITY_BEGIN(); RUN_TEST(test_valid);"
            " RUN_TEST(test_reject); return UNITY_END(); }\n")
        result = UnitRunner(unity_src=MINI_UNITY).run(app / "src",
                                                      app / "tests" / "unit")
        assert result.ok is True, result.reason or result.failures
        assert result.passed == 2

    def test_failing_assertion_is_detected_under_qemu(self, tmp_path):
        from rita.firmware.unity import UnitRunner
        app, tests = self._app(tmp_path)
        (tests / "test_app.c").write_text(
            '#include "unity.h"\n#include "app.h"\n'
            "void test_wrong(void) { TEST_ASSERT_EQUAL_INT(99, clamp_add(1, 1)); }\n"
            "int main(void) { UNITY_BEGIN(); RUN_TEST(test_wrong);"
            " return UNITY_END(); }\n")
        result = UnitRunner(unity_src=MINI_UNITY).run(app / "src",
                                                      app / "tests" / "unit")
        assert result.ok is False
        assert result.failed == 1
        assert any("test_wrong" in (f.testcase or "") for f in result.failures)


class TestVersionMatchesZephyr:
    """The unit-tier gcc must be the SAME VERSION as Zephyr's gcc."""

    def _sdk(self, tmp_path, version_line):
        sdk = tmp_path / "zephyr-sdk-1.0.1"
        bindir = sdk / "arm-zephyr-eabi" / "bin"
        bindir.mkdir(parents=True)
        gcc = bindir / "arm-zephyr-eabi-gcc"
        gcc.write_text("")
        (sdk / "sdk_version").write_text("1.0.1")
        return sdk, gcc, version_line

    def test_detection_prefers_the_version_zephyr_uses(self, tmp_path,
                                                       monkeypatch):
        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        monkeypatch.delenv("GNUARMEMB_TOOLCHAIN_PATH", raising=False)
        sdk, sdk_gcc, _ = self._sdk(tmp_path, "13.2.1")
        monkeypatch.setenv("ZEPHYR_SDK_INSTALL_DIR", str(sdk))
        own = _fake_gcc(tmp_path / "rita" / "toolchains" / "arm-none-eabi" / "bin")
        versions = {own.as_posix(): (12, 2), sdk_gcc.as_posix(): (13, 2),
                    "/usr/bin/arm-none-eabi-gcc": (13, 2)}
        monkeypatch.setattr(toolchain, "_gcc_version",
                            lambda cc: versions.get(Path(cc).as_posix()))
        monkeypatch.setattr(toolchain.shutil, "which",
                            lambda n: "/usr/bin/arm-none-eabi-gcc"
                            if n == "arm-none-eabi-gcc" else None)
        info = toolchain.detect_arm_gcc()
        # RITA's own 12.2 does NOT match Zephyr's 13.2 -> first match wins.
        assert Path(info.cc).as_posix() == "/usr/bin/arm-none-eabi-gcc"
        assert info.version == (13, 2)
        assert info.mismatch is False

    def test_mismatch_is_recorded_when_nothing_matches(self, tmp_path,
                                                       monkeypatch):
        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        monkeypatch.delenv("GNUARMEMB_TOOLCHAIN_PATH", raising=False)
        sdk, sdk_gcc, _ = self._sdk(tmp_path, "13.2.1")
        monkeypatch.setenv("ZEPHYR_SDK_INSTALL_DIR", str(sdk))
        own = _fake_gcc(tmp_path / "rita" / "toolchains" / "arm-none-eabi" / "bin")
        versions = {own.as_posix(): (12, 2),
                    sdk_gcc.as_posix(): None}   # sdk unreadable
        monkeypatch.setattr(toolchain, "_gcc_version",
                            lambda cc: versions.get(Path(cc).as_posix()))
        monkeypatch.setattr(toolchain.shutil, "which", lambda n: None)
        info = toolchain.detect_arm_gcc()
        assert info.cc == str(own)
        assert info.mismatch is True       # surfaced, never silent

    def test_install_picks_the_release_matching_zephyrs_gcc(self, tmp_path,
                                                            monkeypatch):
        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        monkeypatch.setattr(toolchain, "zephyr_gcc_version", lambda: (12, 2))
        urls = []

        def fake_download(url, dest):
            urls.append(url)
            raise OSError("stop here — url captured")

        monkeypatch.setattr(toolchain, "_download", fake_download)
        toolchain.install_arm_gcc()
        assert urls and "12.2" in urls[0]

    def test_install_default_release_when_no_sdk(self, tmp_path, monkeypatch):
        from rita.firmware import toolchain
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        monkeypatch.setattr(toolchain, "zephyr_gcc_version", lambda: None)
        urls = []

        def fake_download(url, dest):
            urls.append(url)
            raise OSError("stop")

        monkeypatch.setattr(toolchain, "_download", fake_download)
        toolchain.install_arm_gcc()
        assert urls and toolchain.DEFAULT_RELEASE in urls[0]
