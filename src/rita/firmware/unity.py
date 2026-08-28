"""Unity unit tests — the unit tier of RITA's flow, on Zephyr's compiler.

Unit tests are NOT ztest: they exercise individual functions in isolation,
hardware stubbed. They are compiled with arm-none-eabi-gcc — the same GCC
family and version Zephyr uses (acquired by RITA when missing) — directly:
no Zephyr headers, no CMake, no west. The resulting ARM binaries run under
qemu-system-arm with semihosting, and Unity's output parses exactly as a
native run's. An explicit `host_cc` override still compiles natively and
runs directly (dev machines, CI). A missing toolchain, emulator, or
framework is reported honestly; the stage is never silently green.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .twister_results import FailureArtifact

UNITY_REPO_URL = "https://github.com/ThrowTheSwitch/Unity"

# The file group tolerates a Windows drive prefix (C:\...); \r?$ tolerates
# CRLF output from Windows-built test binaries.
_FAIL_RE = re.compile(r"^(?P<file>(?:[A-Za-z]:)?[^:\n]+):(?P<line>\d+)"
                      r":(?P<test>\w+):FAIL:?\s*(?P<msg>.*?)\r?$",
                      re.MULTILINE)
_SUMMARY_RE = re.compile(r"(\d+)\s+Tests\s+(\d+)\s+Failures", re.IGNORECASE)


@dataclass(frozen=True)
class UnitResult:
    ok: bool
    failures: tuple[FailureArtifact, ...] = ()
    ran: int = 0
    passed: int = 0
    failed: int = 0
    unavailable: bool = False
    reason: str = ""


def detect_unity(home_root: str | Path | None = None) -> Path | None:
    """The Unity sources on this machine: ~/.rita/unity clone, or the
    CERBERUS clone's unity/ (its setup_unity.sh layout). None = absent."""
    from ..home import cerberus_dir, unity_dir

    candidates = []
    base = Path(home_root) if home_root else None
    u = (base / "unity") if base else unity_dir()
    c = (base / "cerberus") if base else cerberus_dir()
    candidates = [u / "src", u, c / "unity" / "src", c / "unity"]
    for cand in candidates:
        if (cand / "unity.h").is_file() and (cand / "unity.c").is_file():
            return cand
    return None


def install_unity(dest: str | Path | None = None,
                  url: str = UNITY_REPO_URL, git: str = "git"):
    """Clone/update Unity next to CERBERUS — same acquisition contract."""
    from ..home import unity_dir

    from .cerberus_setup import InstallResult

    d = Path(dest) if dest else unity_dir()
    try:
        if (d / ".git").is_dir():
            proc = subprocess.run([git, "-C", str(d), "pull", "--ff-only"],
                                  capture_output=True, text=True, timeout=300)
            action = "updated"
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run([git, "clone", "--depth", "1", url, str(d)],
                                  capture_output=True, text=True, timeout=300)
            action = "cloned"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return InstallResult(ok=False, path=str(d),
                             detail=f"git unavailable or failed: {exc}")
    if proc.returncode != 0:
        return InstallResult(ok=False, path=str(d),
                             detail=(proc.stderr or proc.stdout or "git failed")[-500:])
    if not ((d / "src" / "unity.c").exists() or (d / "unity.c").exists()):
        return InstallResult(ok=False, path=str(d),
                             detail="clone succeeded but unity.c is missing — wrong repo?")
    return InstallResult(ok=True, path=str(d), detail=f"Unity {action} at {d}")


@dataclass(frozen=True)
class CompilerInfo:
    path: str
    source: str   # "explicit" | "host" | "sdk"


def find_compiler(explicit: str | None) -> CompilerInfo | None:
    """The unit tier's compiler is Zephyr's compiler — arm-none-eabi-gcc
    (or the SDK's arm-zephyr-eabi-gcc), version-matched to the Zephyr SDK,
    resolved by `toolchain.detect_arm_gcc`. `host_cc` remains an explicit
    NATIVE override (its binaries run directly, no emulator) for
    development machines and CI. Unrelated native compilers on the
    machine are never picked up."""
    if explicit:
        if Path(explicit).exists() or shutil.which(explicit):
            return CompilerInfo(path=explicit, source="explicit")
        return None
    from .toolchain import detect_arm_gcc

    info = detect_arm_gcc()
    if info is None:
        return None
    return CompilerInfo(path=info.cc, source="arm")


NO_TOOLCHAIN_REASON = (
    "arm-none-eabi-gcc (Zephyr's compiler family) is not on this machine: "
    "not installed by RITA, not on PATH, no GNUARMEMB_TOOLCHAIN_PATH, and "
    "no Zephyr SDK arm toolchain. Install it from Modules → Install ARM "
    "toolchain (or `rita toolchain install`) — RITA downloads the release "
    "matching your Zephyr SDK's gcc version.")

NO_QEMU_REASON = (
    "qemu-system-arm is missing: ARM test binaries cannot execute on this "
    "machine directly. It ships with the Zephyr SDK's host tools; install "
    "it or the SDK and the unit tier picks it up automatically.")


def no_compiler_reason() -> str:
    return NO_TOOLCHAIN_REASON


# The proven ARM run recipe (see docs/specs/unit-tier-toolchain.md):
# arm926ej-s + rdimon semihosting compiles Unity directly; versatilepb
# under QEMU executes it and semihosting carries Unity's output out.
_ARM_CFLAGS = ["-mcpu=arm926ej-s", "--specs=rdimon.specs"]
_QEMU_ARGS = ["-M", "versatilepb", "-cpu", "arm926", "-nographic",
              "-audio", "none", "-semihosting", "-kernel"]


class UnitRunner:
    """Compile unity.c + each test file + the sources under test with
    Zephyr's ARM gcc; run under qemu-system-arm (semihosting); parse
    Unity's output into concrete artifacts. An explicit `cc` compiles
    natively and runs directly instead."""

    def __init__(self, unity_src: str | Path, cc: str | None = None,
                 timeout: float = 120.0) -> None:
        self.unity_src = Path(unity_src)
        self.cc = cc
        self.timeout = timeout

    def run(self, src_dir: str | Path, test_dir: str | Path) -> UnitResult:
        src_dir, test_dir = Path(src_dir), Path(test_dir)
        compiler = find_compiler(self.cc)
        if compiler is None:
            return UnitResult(ok=False, unavailable=True,
                              reason=(f"compiler {self.cc!r} not found"
                                      if self.cc else no_compiler_reason()))
        cc = compiler.path
        qemu = None
        if compiler.source == "arm":
            from .toolchain import detect_qemu

            qemu = detect_qemu()
            if qemu is None:
                return UnitResult(ok=False, unavailable=True,
                                  reason=NO_QEMU_REASON)
        platform = "qemu-arm" if qemu else "host"
        test_files = sorted(test_dir.rglob("*.c")) if test_dir.is_dir() else []
        if not test_files:
            return UnitResult(ok=False, unavailable=True,
                              reason="no unit test files present")
        # Sources under test: everything except entrypoints (they carry main).
        sources = [p for p in sorted(src_dir.rglob("*.c"))
                   if p.name != "main.c" and not p.name.startswith("test_")]

        failures: list[FailureArtifact] = []
        ran = failed = 0
        with tempfile.TemporaryDirectory(prefix="rita-unity-") as tmp:
            for test_file in test_files:
                exe = Path(tmp) / (test_file.stem + ".elf")
                argv = [cc, *(_ARM_CFLAGS if qemu else []),
                        "-I", str(self.unity_src), "-I", str(src_dir),
                        str(self.unity_src / "unity.c"), str(test_file),
                        *map(str, sources), "-o", str(exe)]
                comp = subprocess.run(argv, capture_output=True, text=True,
                                      timeout=self.timeout)
                if comp.returncode != 0:
                    failures.append(FailureArtifact(
                        kind="unit", suite=test_file.name, platform=platform,
                        reason="unit tests failed to compile",
                        log_excerpt=(comp.stderr or comp.stdout)[-4000:],
                        file_hints=(test_file.name,)))
                    continue
                run_argv = ([qemu, *_QEMU_ARGS, str(exe)] if qemu
                            else [str(exe)])
                try:
                    run = subprocess.run(run_argv, capture_output=True,
                                         text=True, timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    failures.append(FailureArtifact(
                        kind="unit", suite=test_file.name, platform=platform,
                        reason=f"unit run timed out after {self.timeout:.0f}s",
                        log_excerpt="the test binary never finished under "
                                    "the emulator", file_hints=(test_file.name,)))
                    continue
                except OSError as exc:
                    failures.append(FailureArtifact(
                        kind="unit", suite=test_file.name, platform=platform,
                        reason="unit test binary failed to execute",
                        log_excerpt=str(exc), file_hints=(test_file.name,)))
                    continue
                out = run.stdout or ""
                m = _SUMMARY_RE.search(out)
                if m:
                    ran += int(m.group(1))
                    failed += int(m.group(2))
                for fm in _FAIL_RE.finditer(out):
                    failures.append(FailureArtifact(
                        kind="unit", suite=test_file.name, platform=platform,
                        reason=f"unit test {fm.group('test')} failed",
                        log_excerpt=fm.group(0),
                        file_hints=(Path(fm.group("file")).name,),
                        testcase=fm.group("test")))
                if run.returncode != 0 and not _FAIL_RE.search(out) and not m:
                    failures.append(FailureArtifact(
                        kind="unit", suite=test_file.name, platform=platform,
                        reason=f"unit runner exited {run.returncode}",
                        log_excerpt=(out or run.stderr)[-4000:],
                        file_hints=(test_file.name,)))
        return UnitResult(ok=not failures, failures=tuple(failures),
                          ran=ran, passed=ran - failed, failed=failed)


HostUnity = UnitRunner   # the seam's historical name


class FakeUnity:
    """Scripted unit tier for pipeline tests: pops "green"/"red"."""

    def __init__(self, script: list[str] | None = None) -> None:
        self.script = list(script or [])
        self.calls = 0

    def run(self, src_dir, test_dir) -> UnitResult:
        self.calls += 1
        step = self.script.pop(0) if self.script else "green"
        if step == "green":
            return UnitResult(ok=True, ran=5, passed=5)
        return UnitResult(ok=False, ran=5, passed=4, failed=1, failures=(
            FailureArtifact(kind="unit", suite="test_app.c", platform="host",
                            reason="unit test test_clamp_add_valid failed",
                            log_excerpt="test_app.c:3:test_clamp_add_valid:FAIL: Values Not Equal",
                            file_hints=("test_app.c",),
                            testcase="test_clamp_add_valid"),))
