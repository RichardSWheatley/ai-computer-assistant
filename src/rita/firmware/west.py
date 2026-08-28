"""The Zephyr runner seam: west build / twister behind a Protocol.

`WestCli` is the real subprocess implementation and runs on the user's
machine where the workspace + toolchain are installed. `FakeWest` is
scripted from fixture twister.json files so the whole iterate loop is
provable headless. Both honor the gate rule: results come from
twister.json, never stdout.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .twister_results import (FailureArtifact, TwisterResult,
                              parse_twister_json)


@dataclass(frozen=True)
class BuildResult:
    ok: bool
    failure: FailureArtifact | None = None


@runtime_checkable
class ZephyrRunner(Protocol):
    def build(self, app_dir: Path, platform: str, outdir: Path) -> BuildResult: ...

    def twister(self, *, testsuite: Path, platform: str, outdir: Path,
                device: bool = False,
                hardware_map: Path | None = None) -> TwisterResult: ...

    def generate_hardware_map(self, out: Path) -> Path: ...


class WestCli:
    """Real `west` subprocess calls; cwd is the workspace root."""

    def __init__(self, workspace: str | Path, west: str = "west",
                 timeout: float = 1800.0) -> None:
        self.workspace = Path(workspace)
        self.west = west
        self.timeout = timeout

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        from .static_check import resolve_argv

        return subprocess.run([*resolve_argv([self.west]), *args],
                              cwd=self.workspace,
                              capture_output=True, text=True,
                              timeout=self.timeout)

    def build(self, app_dir: Path, platform: str, outdir: Path) -> BuildResult:  # pragma: no cover - needs a toolchain
        outdir.mkdir(parents=True, exist_ok=True)
        proc = self._run(["build", "-p", "auto", "-b", platform,
                          "-d", str(outdir), str(app_dir)])
        if proc.returncode == 0:
            return BuildResult(ok=True)
        log = (proc.stderr or proc.stdout or "")[-4000:]
        from .twister_results import _FILE_HINT_RE  # single hint source
        return BuildResult(ok=False, failure=FailureArtifact(
            kind="compile", suite=app_dir.name, platform=platform,
            reason=f"west build exited {proc.returncode}", log_excerpt=log,
            file_hints=tuple(dict.fromkeys(_FILE_HINT_RE.findall(log)))))

    def twister(self, *, testsuite: Path, platform: str, outdir: Path,
                device: bool = False,
                hardware_map: Path | None = None) -> TwisterResult:  # pragma: no cover - needs a toolchain
        outdir.mkdir(parents=True, exist_ok=True)
        args = ["twister", "-T", str(testsuite), "-p", platform,
                "--outdir", str(outdir)]
        if device:
            args += ["--device-testing", "--hardware-map", str(hardware_map)]
        self._run(args)  # exit code ignored on purpose: twister.json is the gate
        return parse_twister_json(outdir / "twister.json")

    def generate_hardware_map(self, out: Path) -> Path:  # pragma: no cover - needs hardware
        out.parent.mkdir(parents=True, exist_ok=True)
        self._run(["twister", "--generate-hardware-map", str(out)])
        return out


class FakeWest:
    """Scripted runner: each call pops the next scripted result.

    Build steps are "ok" or a fixture twister.json name whose first failure
    becomes the build failure; twister steps are fixture file names copied
    into the outdir (so parsing runs exactly like production).
    """

    def __init__(self, build_seq: list[str], twister_seq: list[str],
                 device_seq: list[str] | None = None,
                 fixtures_dir: Path | None = None) -> None:
        self.build_seq = list(build_seq)
        self.twister_seq = list(twister_seq)
        self.device_seq = list(device_seq or [])
        self.fixtures_dir = fixtures_dir
        self.build_calls: list[dict] = []
        self.twister_calls: list[dict] = []
        self.device_calls: list[dict] = []
        self.generated_maps = 0

    def build(self, app_dir: Path, platform: str, outdir: Path) -> BuildResult:
        self.build_calls.append({"app_dir": str(app_dir), "platform": platform})
        step = self.build_seq.pop(0) if self.build_seq else "ok"
        if step == "ok":
            return BuildResult(ok=True)
        result = parse_twister_json(self.fixtures_dir / step)
        return BuildResult(ok=False, failure=result.failures[0])

    def twister(self, *, testsuite: Path, platform: str, outdir: Path,
                device: bool = False,
                hardware_map: Path | None = None) -> TwisterResult:
        call = {"testsuite": str(testsuite), "platform": platform,
                "device": device,
                "hardware_map": str(hardware_map) if hardware_map else None}
        seq = self.device_seq if device else self.twister_seq
        (self.device_calls if device else self.twister_calls).append(call)
        step = seq.pop(0) if seq else "pass.json"
        outdir.mkdir(parents=True, exist_ok=True)
        dst = outdir / "twister.json"
        shutil.copy2(self.fixtures_dir / step, dst)
        return parse_twister_json(dst)   # same gate path as production

    def generate_hardware_map(self, out: Path) -> Path:
        self.generated_maps += 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("- connected: true\n  platform: fake/fake\n"
                       "  runner: fake\n  serial: /dev/null\n")
        return out
