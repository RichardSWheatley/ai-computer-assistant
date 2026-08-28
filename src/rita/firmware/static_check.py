"""The CERBERUS static-check gate seam.

Code passes the static gate before it may build; every patch re-enters
here. Findings are the same concrete `FailureArtifact` contract as every
other gate, so Claude patches them without special handling — and never
grades its own work.

`CerberusCli` runs the configured command with the target directory
appended. Exit 0 = clean. JSON output
(`{"findings": [{"file", "line", "severity", "message"}]}`) is parsed into
one artifact per finding; any other output becomes a single artifact
carrying the raw text — so the gate works with any CLI shape until the
exact CERBERUS interface is pinned down.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .twister_results import FailureArtifact


@dataclass(frozen=True)
class StaticResult:
    ok: bool
    findings: tuple[FailureArtifact, ...] = ()


@runtime_checkable
class StaticChecker(Protocol):
    def check(self, target: Path) -> StaticResult: ...


def _artifact(target: Path, *, message: str, file: str | None = None,
              line=None, severity: str = "error",
              verdict: str | None = None) -> FailureArtifact:
    location = f"{file}:{line}" if file and line is not None else (file or "")
    log = f"{location}: {severity}: {message}" if location else message
    return FailureArtifact(
        kind="static", suite=target.name, platform="static-analysis",
        reason=f"CERBERUS: {verdict or severity}", log_excerpt=log[:4000],
        file_hints=(file,) if file else ())


# CERBERUS G.U.A.R.D. verdicts (github.com/RichardSWheatley/cerberus):
# exit 0 = approve, 1 = request changes, 2 = block. Both non-zero gate.
_VERDICTS = {1: "request changes", 2: "block"}


def split_command(command: str) -> list[str]:
    """Split a configured command string into argv, cross-platform.
    POSIX shlex eats Windows path backslashes (C:\\tools -> C:tools), so
    on Windows split in non-POSIX mode and strip the quotes it keeps."""
    if os.name == "nt":
        return [t.strip('"') for t in shlex.split(command, posix=False)]
    return shlex.split(command)


class CerberusCli:
    """Run the CERBERUS command over a target directory.

    Accepts a command string (custom tools) or an argv list (the pinned
    `python -m cerberus.cli scan` invocation, which needs cwd=<clone> since
    the repo isn't pip-installed). Environment passes through, so deep mode
    reads its own CERBERUS_LLM_* / ANTHROPIC_API_KEY settings.
    """

    def __init__(self, command: str | list[str], cwd: str | None = None,
                 timeout: float = 600.0) -> None:
        self.command = command if isinstance(command, str) else ""
        self.argv = (split_command(command) if isinstance(command, str)
                     else list(command))
        self.cwd = cwd
        self.timeout = timeout

    def check(self, target: Path) -> StaticResult:
        argv = [*self.argv, str(Path(target).resolve())]
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=self.timeout, cwd=self.cwd)
        if proc.returncode == 0:
            return StaticResult(ok=True)
        verdict = _VERDICTS.get(proc.returncode, "findings")
        out = (proc.stdout or "").strip()
        findings: list[FailureArtifact] = []
        try:
            data = json.loads(out)
            for f in data.get("findings", []):
                findings.append(_artifact(
                    target, message=str(f.get("message", "finding")),
                    file=f.get("file"), line=f.get("line"),
                    severity=str(f.get("severity", verdict)), verdict=verdict))
        except (json.JSONDecodeError, AttributeError):
            pass
        if not findings:  # non-JSON tools still yield a concrete artifact
            raw = out or (proc.stderr or "").strip() \
                or f"exit code {proc.returncode} with no output"
            findings.append(_artifact(target, message=raw, verdict=verdict))
        return StaticResult(ok=False, findings=tuple(findings))


class FakeCerberus:
    """Scripted gate: each check() pops "clean" or "findings"."""

    def __init__(self, script: list[str] | None = None) -> None:
        self.script = list(script or [])
        self.calls = 0

    def check(self, target: Path) -> StaticResult:
        self.calls += 1
        step = self.script.pop(0) if self.script else "clean"
        if step == "clean":
            return StaticResult(ok=True)
        return StaticResult(ok=False, findings=(
            _artifact(target, message="uninitialized variable 'x'",
                      file="src/main.c", line=12),))
