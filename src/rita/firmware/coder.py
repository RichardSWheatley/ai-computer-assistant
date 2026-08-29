"""The coder-worker seam: an external CLI as the coding agent, one step per call.

The coding agent authors applications (scaffold), writes tests (Fix 2),
judges fit (Fix 2), and patches failures. It never routes, never schedules
tests, and never judges its own success — gates do. `patch()` REQUIRES a
concrete `FailureArtifact`: the invariant is enforced here and honored by
the pipeline, which only builds artifacts from parsed gate results.

`CoderCli` shells out to the command the user configured (`coder_command`
— which CLI is config data, never code) with `--mcp-config` pointing at
the workspace MCP server (Fix 2) so the agent sees the workspace through
indexed tools, not filesystem groping.
"""

from __future__ import annotations

import json
import os
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


def _is_windows() -> bool:
    return os.name == "nt"


def launch_login(cfg) -> str:
    """Open the coding agent's OWN login flow in a visible console window.

    The flow is the vendor CLI's interactive OAuth — RITA cannot complete
    it headlessly, but the user never types a command: one click opens
    the window, they finish the login there, and `check setup` verifies.
    `coder_login_command` overrides for agents whose login is a distinct
    subcommand; the default is the agent run bare, which prompts its own
    login when logged out."""
    from .static_check import resolve_argv, split_command

    if cfg.coder_login_command:
        argv = split_command(cfg.coder_login_command)
    elif cfg.coder_command:
        argv = split_command(cfg.coder_command)[:1]    # bare, interactive
    else:
        return ("No coding agent is configured yet — set its command on "
                "the Settings page first, then log it in from here.")
    try:
        argv = resolve_argv(argv)
    except FileNotFoundError as exc:
        return str(exc)
    cwd = cfg.workspace or str(Path.home())
    try:
        if _is_windows():
            subprocess.Popen(argv, cwd=cwd,
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:                     # dev machines: best-effort terminal
            try:
                subprocess.Popen(["x-terminal-emulator", "-e", *argv],
                                 cwd=cwd)
            except OSError:
                subprocess.Popen(argv, cwd=cwd)
    except OSError as exc:
        return f"I couldn't open the login window: {exc}"
    return ("I opened a window with your coding agent — finish the login "
            "there, then say 'check setup' and I'll verify it worked.")


# Where auth failures send the user: RITA's button, never a terminal.
LOGIN_HINT = (" — YOUR CODING AGENT IS NOT LOGGED IN: click 'Log in "
              "coding agent' on the Settings page (RITA opens the login "
              "window for you), finish the login there, then try again.")


@runtime_checkable
class CoderWorker(Protocol):
    def complete(self, prompt: str) -> str: ...

    def patch(self, failure: FailureArtifact, workdir: Path) -> PatchResult: ...

    def scaffold(self, goal: str, board: str, dest: Path) -> ScaffoldResult: ...


def _require_failure(failure: FailureArtifact | None) -> FailureArtifact:
    if failure is None or not failure.log_excerpt.strip():
        raise ValueError(
            "The coding agent is never invoked to patch without a concrete failure "
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


class CoderCli:
    """The configured coding-agent CLI as a subprocess, bounded timeout."""

    def __init__(self, workspace: str | Path, command: tuple[str, ...], *,
                 mcp_config: str | Path | None = None,
                 timeout: float = 600.0) -> None:
        self.workspace = Path(workspace)
        self.mcp_config = str(mcp_config) if mcp_config else None
        self.command = command
        self.timeout = timeout
        # True once an invocation had to fall back to running without the
        # workspace MCP server. Surfaced in reports — never silent.
        self.mcp_fallback = False
        # Progress narration sink: "asking the agent… / replied in Ns".
        self.on_activity = None

    def _note(self, msg: str) -> None:
        if self.on_activity is not None:
            try:
                self.on_activity(msg)
            except Exception:
                pass

    def _args(self, prompt: str, *, allow_edits: bool,
              with_mcp: bool) -> tuple[list, str | None]:
        """(argv, stdin payload). npm/pip .cmd shims route through
        cmd.exe, which DESTROYS multi-line arguments — the owner's agent
        replied 'your message ends at the colon': the prompt had been
        truncated at its first newline. Through a shim, the prompt
        travels via stdin; a real binary keeps it in argv."""
        from .static_check import resolve_argv

        argv = resolve_argv(list(self.command))
        shim = argv[0].lower().endswith((".cmd", ".bat"))
        stdin_payload = prompt if shim else None
        args = [*argv] + ([] if shim else [prompt]) + [
            "--output-format", "text"]
        if with_mcp and self.mcp_config:
            args += ["--mcp-config", self.mcp_config]
        if allow_edits:
            args += ["--permission-mode", "acceptEdits"]
        return args, stdin_payload

    def _run(self, args: list, stdin_payload: str | None,
             cwd: Path) -> subprocess.CompletedProcess:
        # UTF-8 both ways: agent output decoded per locale turned em
        # dashes into mojibake on Windows (cp1252).
        import time as _time

        self._note("→ asking the coding agent…")
        t0 = _time.monotonic()
        try:
            proc = subprocess.run(args, cwd=cwd, capture_output=True,
                                  encoding="utf-8", errors="replace",
                                  input=stdin_payload,
                                  timeout=self.timeout)
        except subprocess.TimeoutExpired:
            self._note(f"✗ no reply within {self.timeout:.0f}s — "
                       "the agent was cut off")
            raise
        dt = _time.monotonic() - t0
        self._note(f"← the coding agent replied in {dt:.0f}s "
                   f"(exit {proc.returncode}, "
                   f"{len(proc.stdout or '')} chars)")
        return proc

    def _invoke(self, prompt: str, cwd: Path, *,
                allow_edits: bool) -> subprocess.CompletedProcess:
        args, payload = self._args(prompt, allow_edits=allow_edits,
                                   with_mcp=True)
        try:
            proc = self._run(args, payload, cwd)
        except subprocess.TimeoutExpired:
            # A hang is often transient (a wedged tool, a network
            # stall). One more try before giving up with evidence.
            self._note("→ retrying once — a hang is often transient…")
            try:
                proc = self._run(args, payload, cwd)
            except subprocess.TimeoutExpired as second:
                raise RuntimeError(self._timeout_text(second)) from None
        self.last_args = args
        if proc.returncode == 0 or not self.mcp_config:
            return proc
        # Workspace tools are an enhancement, not a prerequisite: a broken
        # MCP server must never block authoring. Retry once without it and
        # record the fallback so reports can say what happened.
        retry_args, payload = self._args(prompt, allow_edits=allow_edits,
                                         with_mcp=False)
        retry = self._run(retry_args, payload, cwd)
        if retry.returncode == 0:
            self.mcp_fallback = True
            self.last_args = retry_args
            return retry
        return proc

    def complete(self, prompt: str) -> str:
        proc = self._invoke(prompt, self.workspace, allow_edits=False)
        out = (proc.stdout or "").strip()
        if proc.returncode != 0 or not out:
            raise RuntimeError(self._failure_text(proc))
        return proc.stdout

    @staticmethod
    def _tail(stream) -> str:
        """Last 600 chars of a possibly-bytes, possibly-None stream."""
        if isinstance(stream, bytes):
            stream = stream.decode("utf-8", "replace")
        text = (stream or "").strip()
        return text[-600:] or "(nothing)"

    def _timeout_text(self, exc: subprocess.TimeoutExpired) -> str:
        """A double timeout, with the evidence: what the agent had said
        before the cutoff, and what to do about it."""
        cmd = exc.cmd if isinstance(exc.cmd, (list, tuple)) else [exc.cmd]
        argv = " ".join(str(a) for a in list(cmd)[:2])
        return (f"the coding agent ({argv}) produced no reply within "
                f"{self.timeout:.0f}s, twice in a row, and was cut off. "
                f"Partial output before the cutoff — "
                f"stdout: {self._tail(exc.stdout)} | "
                f"stderr: {self._tail(exc.stderr)}. "
                "If this step is genuinely that big, raise the agent "
                "reply ceiling in Settings. If it keeps happening, the "
                "agent may be stuck waiting for something interactive — "
                "run 'check setup' and log it in again from Settings.")

    def _failure_text(self, proc) -> str:
        """Quote what actually happened: argv, exit code, both streams."""
        argv = " ".join(getattr(self, "last_args", list(self.command))[:2])
        out = (proc.stdout or "").strip()[-600:] or "(empty)"
        err = (proc.stderr or "").strip()[-600:] or "(empty)"
        note = (" (retried without the workspace MCP server too)"
                if self.mcp_config else "")
        blob = f"{out} {err}".lower()
        hint = ""
        if any(h in blob for h in ("authenticate", "oauth", "unauthorized",
                                   "login", "api key", "session expired")):
            hint = LOGIN_HINT
        return (f"the coding agent ({argv}) exited {proc.returncode}"
                f"{note}. stdout: {out} | stderr: {err}{hint}")

    def patch(self, failure: FailureArtifact, workdir: Path) -> PatchResult:  # pragma: no cover - needs the coding-agent CLI
        failure = _require_failure(failure)
        prompt = _PATCH_PROMPT.format(kind=failure.kind,
                                      artifact=failure.describe())
        proc = self._invoke(prompt, workdir, allow_edits=True)
        return PatchResult(ok=proc.returncode == 0,
                           detail=(proc.stdout or proc.stderr or "")[-500:])

    def scaffold(self, goal: str, board: str, dest: Path) -> ScaffoldResult:  # pragma: no cover - needs the coding-agent CLI
        dest.mkdir(parents=True, exist_ok=True)
        prompt = _SCAFFOLD_PROMPT.format(goal=goal, board=board)
        proc = self._invoke(prompt, dest, allow_edits=True)
        ok = proc.returncode == 0 and (dest / "CMakeLists.txt").exists()
        return ScaffoldResult(ok=ok, app_dir=str(dest),
                              detail=(proc.stdout or "")[-500:])


class FakeCoder:
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
