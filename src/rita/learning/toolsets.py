"""Toolsets: the agent builds tools RITA keeps and reruns.

A toolset is a directory under ~/.rita/toolsets/<name>/ — the files the
agent wrote plus a toolset.md manifest (purpose, command, provenance).
RITA writes the files herself from the agent's strict-JSON answer (so
the path invariant is enforced structurally: nothing lands outside the
toolset's own directory), smoke-runs the command before registering,
and deletes the directory when the smoke run fails — failures are
reported, never registered. Registered toolsets persist across
launches: reuse is automation.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolsetInfo:
    name: str
    purpose: str
    command: tuple[str, ...]
    path: str


def toolsets_root() -> Path:
    from ..home import toolsets_dir

    return toolsets_dir()


_PROMPT = (
    "Design a small reusable command-line toolset for this request. "
    "Answer with STRICT JSON only — no prose, no code fences: "
    '{{"name": "<short-kebab-name>", "purpose": "<one line>", '
    '"files": {{"<relative path>": "<file content>"}}, '
    '"command": ["<argv0>", "..."], "smoke": ["<optional args for a '
    'self-test run>"]}}. '
    "The command runs from the toolset's own directory; use "
    '"python" as argv0 for Python scripts. The smoke args (may be '
    "empty) must make the command exit 0 quickly without touching "
    "anything outside its directory.\nRequest: {request}")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(name).lower()).strip("-")


def _resolve_command(command: list) -> tuple[str, ...]:
    """argv with 'python' pinned to a real interpreter. In a frozen app
    sys.executable is RITA herself — fall back to the system python and
    let the smoke run report honestly if there isn't one."""
    argv = [str(a) for a in command]
    if argv and argv[0] in ("python", "python3"):
        if not getattr(sys, "frozen", False):
            argv[0] = sys.executable
        else:
            import shutil

            found = shutil.which("python") or shutil.which("python3")
            if found:
                argv[0] = found
    return tuple(argv)


def create_toolset(complete, request: str) -> tuple[ToolsetInfo | None, str]:
    """Ask the agent for the toolset, write it, validate it, keep it."""
    import shutil

    try:
        raw = complete(_PROMPT.format(request=request))
    except Exception as exc:
        return None, f"the coding agent could not be asked: {exc}"
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    try:
        spec = json.loads(m.group(0) if m else (raw or ""))
    except Exception as exc:
        return None, f"the agent's toolset answer was not strict JSON ({exc})"
    name = _slug(spec.get("name", ""))
    files = spec.get("files")
    command = spec.get("command")
    if not name or not isinstance(files, dict) or not files \
            or not isinstance(command, list) or not command:
        return None, ("the agent's toolset answer is missing name, "
                      "files, or command")
    dest = toolsets_root() / name
    # Path invariant: every file lands INSIDE the toolset's directory.
    resolved_dest = dest.resolve() if dest.exists() else dest
    for rel in files:
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts:
            return None, (f"refusing the toolset: file path {rel!r} "
                          f"escapes the toolset directory")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for rel, content in files.items():
        f = dest / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(str(content))
    argv = _resolve_command(command)
    smoke = [str(a) for a in spec.get("smoke") or []]
    try:
        proc = subprocess.run(list(argv) + smoke, cwd=dest,
                              capture_output=True, text=True, timeout=120,
                              stdin=subprocess.DEVNULL)
    except Exception as exc:
        shutil.rmtree(dest, ignore_errors=True)
        return None, f"the toolset's smoke run could not start: {exc}"
    if proc.returncode != 0:
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-400:]
        shutil.rmtree(dest, ignore_errors=True)
        return None, (f"the toolset failed its smoke run (exit "
                      f"{proc.returncode}) and was not registered: {tail}")
    purpose = str(spec.get("purpose", request))[:200]
    import datetime

    (dest / "toolset.md").write_text(
        f"# {name}\n"
        f"purpose: {purpose}\n"
        f"command: {json.dumps(list(argv))}\n"
        f"created: agent-authored {datetime.date.today().isoformat()}, "
        f"validated by RITA's smoke run\n")
    return (ToolsetInfo(name=name, purpose=purpose, command=argv,
                        path=str(dest)),
            f"toolset {name} validated and registered")


def list_toolsets() -> list[ToolsetInfo]:
    root = toolsets_root()
    out: list[ToolsetInfo] = []
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        manifest = d / "toolset.md"
        if not manifest.is_file():
            continue
        purpose = ""
        command: tuple[str, ...] = ()
        for ln in manifest.read_text().splitlines():
            if ln.startswith("purpose:"):
                purpose = ln.split(":", 1)[1].strip()
            if ln.startswith("command:"):
                try:
                    command = tuple(json.loads(ln.split(":", 1)[1]))
                except Exception:
                    command = ()
        if command:
            out.append(ToolsetInfo(name=d.name, purpose=purpose,
                                   command=command, path=str(d)))
    return out


def run_toolset(name: str, args: tuple[str, ...] = ()) -> tuple[bool, str]:
    """Rerun a registered toolset from disk. Honest output either way."""
    match = next((t for t in list_toolsets() if t.name == _slug(name)), None)
    if match is None:
        known = ", ".join(t.name for t in list_toolsets()) or "none yet"
        return False, f"no toolset named {name!r} (I have: {known})"
    try:
        proc = subprocess.run(list(match.command) + list(args),
                              cwd=match.path, capture_output=True,
                              text=True, timeout=600,
                              stdin=subprocess.DEVNULL)
    except Exception as exc:
        return False, f"toolset {match.name} could not run: {exc}"
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        return False, (f"toolset {match.name} exited "
                       f"{proc.returncode}: {output[-400:]}")
    return True, output
