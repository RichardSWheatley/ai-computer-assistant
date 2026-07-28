"""The claude-worker seam: Claude as the coding agent, one step per call.

Claude authors applications (scaffold), writes tests (Fix 2), judges fit
(Fix 2), and patches failures. It never routes, never schedules tests, and
never judges its own success — gates do. `patch()` REQUIRES a concrete
`FailureArtifact`: the invariant is enforced here and honored by the
pipeline, which only builds artifacts from parsed gate results.

`ClaudeWorkerCli` shells out to `claude -p` with `--mcp-config` pointing at
the workspace MCP server (Fix 2) so Claude sees the workspace through
indexed tools, not filesystem groping.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .twister_results import FailureArtifact


@dataclass(frozen=True)
class PatchResult:
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class ScaffoldResult:
    ok: bool
    app_dir: str
    detail: str = ""


@runtime_checkable
class ClaudeWorker(Protocol):
    def complete(self, prompt: str) -> str: ...

    def patch(self, failure: FailureArtifact, workdir: Path) -> PatchResult: ...

    def scaffold(self, goal: str, board: str, dest: Path) -> ScaffoldResult: ...


def _require_failure(failure: FailureArtifact | None) -> FailureArtifact:
    if failure is None or not failure.log_excerpt.strip():
        raise ValueError(
            "Claude is never invoked to patch without a concrete failure "
            "artifact (parsed from the gate result)")
    return failure


_PATCH_PROMPT = """A Zephyr {kind} failure needs a fix. Do exactly one step:
produce the patch for this failure, applied to the files in this directory.
Do not run tests, do not judge success — the orchestrator re-runs the gates.

{artifact}"""

_SCAFFOLD_PROMPT = """Create a complete Zephyr application in this directory
for board {board}: {goal}

It must build with `west build -b {board}` unmodified: include CMakeLists.txt,
prj.conf, and src/main.c.

Mandatory coding contract: every function must either RESTRICT its input and
output parameters (constrained types, enforced ranges) or VALIDATE them
before executing (guard clauses that reject invalid input). Every function
will be unit-tested for its input/output parameters and statically checked;
unguarded parameters are a defect.

Do exactly this one step; the orchestrator checks and tests it."""


class ClaudeWorkerCli:
    """`claude -p` subprocess with a bounded timeout (runs on the user's box)."""

    def __init__(self, workspace: str | Path,
                 mcp_config: str | Path | None = None,
                 command: tuple[str, ...] = ("claude", "-p"),
                 timeout: float = 600.0) -> None:
        self.workspace = Path(workspace)
        self.mcp_config = str(mcp_config) if mcp_config else None
        self.command = command
        self.timeout = timeout

    def _invoke(self, prompt: str, cwd: Path, *,
                allow_edits: bool) -> subprocess.CompletedProcess:  # pragma: no cover - needs claude CLI
        args = [*self.command, prompt, "--output-format", "text"]
        if self.mcp_config:
            args += ["--mcp-config", self.mcp_config]
        if allow_edits:
            args += ["--permission-mode", "acceptEdits"]
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              timeout=self.timeout)

    def complete(self, prompt: str) -> str:  # pragma: no cover - needs claude CLI
        proc = self._invoke(prompt, self.workspace, allow_edits=False)
        return proc.stdout

    def patch(self, failure: FailureArtifact, workdir: Path) -> PatchResult:  # pragma: no cover - needs claude CLI
        failure = _require_failure(failure)
        prompt = _PATCH_PROMPT.format(kind=failure.kind,
                                      artifact=failure.describe())
        proc = self._invoke(prompt, workdir, allow_edits=True)
        return PatchResult(ok=proc.returncode == 0,
                           detail=(proc.stdout or proc.stderr or "")[-500:])

    def scaffold(self, goal: str, board: str, dest: Path) -> ScaffoldResult:  # pragma: no cover - needs claude CLI
        dest.mkdir(parents=True, exist_ok=True)
        prompt = _SCAFFOLD_PROMPT.format(goal=goal, board=board)
        proc = self._invoke(prompt, dest, allow_edits=True)
        ok = proc.returncode == 0 and (dest / "CMakeLists.txt").exists()
        return ScaffoldResult(ok=ok, app_dir=str(dest),
                              detail=(proc.stdout or "")[-500:])


class FakeClaude:
    """Scripted worker that records every artifact it is handed."""

    def __init__(self, completions: list[str] | None = None,
                 patch_ok: bool = True) -> None:
        self.completions = list(completions or [])
        self.patch_ok = patch_ok
        self.patches: list[FailureArtifact] = []
        self.prompts: list[str] = []
        self.scaffolds: list[str] = []
        self.scaffolds_dirs: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.completions:
            return json.dumps({"fit": "none", "reason": "unscripted"})
        return self.completions.pop(0)

    def patch(self, failure: FailureArtifact | None, workdir: Path) -> PatchResult:
        failure = _require_failure(failure)
        self.patches.append(failure)
        return PatchResult(ok=self.patch_ok, detail="patched (fake)")

    def scaffold(self, goal: str, board: str, dest: Path) -> ScaffoldResult:
        dest = Path(dest)
        (dest / "src").mkdir(parents=True, exist_ok=True)
        (dest / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n")
        (dest / "prj.conf").write_text("CONFIG_GPIO=y\n")
        (dest / "src" / "main.c").write_text("int main(void) { return 0; }\n")
        # A validated helper, so the unit tier has a function to cover.
        (dest / "src" / "app.c").write_text(
            "int fake_helper(int v) {\n"
            "    if (v < 0) return -1;\n"
            "    return v + 1;\n"
            "}\n")
        self.scaffolds.append(goal)
        self.scaffolds_dirs.append(str(dest))
        return ScaffoldResult(ok=True, app_dir=str(dest), detail="scaffolded (fake)")
