"""Host-run Unity unit tests — the unit tier of RITA's flow.

Unit tests are NOT ztest: they exercise individual functions in isolation
on the host, in milliseconds, hardware stubbed. RITA uses Unity
(ThrowTheSwitch — the same framework CERBERUS's Executioner uses), cloned
onto the machine like CERBERUS itself. A missing compiler or framework is
reported honestly; the stage is never silently green.
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


def _is_windows() -> bool:
    return os.name == "nt"


# Common Windows install locations that don't put themselves on PATH.
_WINDOWS_COMPILER_DIRS = [
    Path(r"C:\Program Files\LLVM\bin"),
    Path(r"C:\Program Files (x86)\LLVM\bin"),
    Path(r"C:\msys64\mingw64\bin"),
    Path(r"C:\msys64\ucrt64\bin"),
    Path(r"C:\MinGW\bin"),
    Path(r"C:\ProgramData\chocolatey\bin"),
]

_WINDOWS_COMPILER_NAMES = ("clang.exe", "gcc.exe", "cc.exe")


def find_compiler(explicit: str | None) -> CompilerInfo | None:
    """The unit tier's C compiler, in order: explicit override; a native
    host compiler (PATH, plus well-known install dirs on Windows); then
    the Zephyr SDK's toolchain — but ONLY where its output can actually
    run. SDK toolchains are cross compilers emitting ELF, so on Windows
    they are not host compilers and are not offered."""
    if explicit:
        if Path(explicit).exists() or shutil.which(explicit):
            return CompilerInfo(path=explicit, source="explicit")
        return None
    for cand in ("cc", "gcc", "clang"):
        if shutil.which(cand):
            return CompilerInfo(path=cand, source="host")
    if _is_windows():
        for d in _WINDOWS_COMPILER_DIRS:
            for name in _WINDOWS_COMPILER_NAMES:
                cand = Path(d) / name
                if cand.is_file():
                    return CompilerInfo(path=str(cand), source="host")
        return None            # SDK toolchains can't produce runnable .exe
    from .workspace import read_sdk_info

    sdk = read_sdk_info()
    if sdk:
        root = Path(sdk["path"])
        for rel in ("x86_64-zephyr-elf/bin/x86_64-zephyr-elf-gcc",
                    "x86_64-zephyr-elf/bin/x86_64-zephyr-elf-gcc.exe",
                    "llvm/bin/clang", "llvm/bin/clang.exe"):
            cand = root / rel
            if cand.is_file():
                return CompilerInfo(path=str(cand), source="sdk")
    return None


_NO_COMPILER_REASON = ("no C compiler found: none on PATH (cc/gcc/clang) and "
                       "no Zephyr SDK toolchain detected")

# Windows needs a NATIVE compiler: the Zephyr SDK's toolchains are cross
# compilers that emit ELF binaries Windows cannot execute, so they can't
# run host unit tests no matter how they're invoked.
NO_HOST_COMPILER_WINDOWS = (
    "no native C compiler on this machine. The Zephyr SDK's toolchains are "
    "cross compilers (they emit ELF binaries Windows can't run), so the "
    "unit tier needs a native one: install LLVM/clang for Windows or "
    "MinGW-w64 gcc (winget install LLVM.LLVM), or point Settings → "
    "C compiler at one. It is picked up automatically once present.")


def no_compiler_reason() -> str:
    return NO_HOST_COMPILER_WINDOWS if _is_windows() else _NO_COMPILER_REASON


class HostUnity:
    """Compile unity.c + each test file + the sources under test with the
    host compiler; run; parse Unity's output into concrete artifacts."""

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
                exe = Path(tmp) / (test_file.stem + ".bin")
                argv = [cc, "-I", str(self.unity_src), "-I", str(src_dir),
                        str(self.unity_src / "unity.c"), str(test_file),
                        *map(str, sources), "-o", str(exe)]
                if compiler.source == "sdk":
                    argv.append("-static")   # cross toolchain: self-contained
                comp = subprocess.run(argv, capture_output=True, text=True,
                                      timeout=self.timeout)
                if comp.returncode != 0:
                    failures.append(FailureArtifact(
                        kind="unit", suite=test_file.name, platform="host",
                        reason="unit tests failed to compile",
                        log_excerpt=(comp.stderr or comp.stdout)[-4000:],
                        file_hints=(test_file.name,)))
                    continue
                try:
                    run = subprocess.run([str(exe)], capture_output=True,
                                         text=True, timeout=self.timeout)
                except OSError as exc:   # e.g. cross-built binary on this host
                    hint = ("the Zephyr SDK cross-compiler produced a binary "
                            "this host cannot execute; install a native host "
                            "C compiler (gcc/clang)"
                            if compiler.source == "sdk" else str(exc))
                    failures.append(FailureArtifact(
                        kind="unit", suite=test_file.name, platform="host",
                        reason="unit test binary failed to execute",
                        log_excerpt=hint, file_hints=(test_file.name,)))
                    continue
                out = run.stdout or ""
                m = _SUMMARY_RE.search(out)
                if m:
                    ran += int(m.group(1))
                    failed += int(m.group(2))
                for fm in _FAIL_RE.finditer(out):
                    failures.append(FailureArtifact(
                        kind="unit", suite=test_file.name, platform="host",
                        reason=f"unit test {fm.group('test')} failed",
                        log_excerpt=fm.group(0),
                        file_hints=(Path(fm.group("file")).name,),
                        testcase=fm.group("test")))
                if run.returncode != 0 and not _FAIL_RE.search(out) and not m:
                    failures.append(FailureArtifact(
                        kind="unit", suite=test_file.name, platform="host",
                        reason=f"unit runner exited {run.returncode}",
                        log_excerpt=(out or run.stderr)[-4000:],
                        file_hints=(test_file.name,)))
        return UnitResult(ok=not failures, failures=tuple(failures),
                          ran=ran, passed=ran - failed, failed=failed)


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
