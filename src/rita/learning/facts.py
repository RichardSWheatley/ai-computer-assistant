"""Validated machine facts RITA remembers (~/.rita/knowledge/machine).

One markdown file per fact: title, provenance line, evidence line, and
a JSON body carrying the machine-readable value. Facts re-validate on
every read — a fact whose path no longer exists is stale and returns
None, which is the caller's cue to re-investigate. The machine is the
source of truth; the fact is a verified pointer into it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _dir() -> Path:
    from ..home import machine_dir

    return machine_dir()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "fact"


def save_fact(name: str, value: dict, *, evidence: str) -> Path:
    import datetime

    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{_slug(name)}.md"
    path.write_text(
        f"# {name}\n"
        f"verified: agent+RITA {datetime.date.today().isoformat()}\n"
        f"evidence: {evidence}\n\n"
        f"{json.dumps(value, indent=1)}\n")
    return path


def _parse(path: Path) -> tuple[str, dict, str] | None:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    name = lines[0].lstrip("# ").strip() if lines else path.stem
    evidence = ""
    body_start = 0
    for i, ln in enumerate(lines):
        if ln.lower().startswith("evidence:"):
            evidence = ln.split(":", 1)[1].strip()
        if not ln.strip() and i > 0:
            body_start = i + 1
            break
    try:
        value = json.loads("\n".join(lines[body_start:]))
    except Exception:
        return None
    return name, value if isinstance(value, dict) else {}, evidence


def _valid(value: dict) -> bool:
    """Cheap re-validation: any 'path' the fact points at must still
    exist. The machine changed -> the fact is stale, not truth."""
    p = value.get("path")
    if p is not None and not Path(p).exists():
        return False
    return True


def fact(name: str) -> dict | None:
    """The fact's value, re-validated — None when unknown or stale."""
    path = _dir() / f"{_slug(name)}.md"
    if not path.is_file():
        return None
    parsed = _parse(path)
    if parsed is None:
        return None
    _, value, _ = parsed
    return value if _valid(value) else None


def all_facts() -> dict[str, dict]:
    """Every currently-valid fact, by name."""
    out: dict[str, dict] = {}
    d = _dir()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.md")):
        parsed = _parse(f)
        if parsed is None:
            continue
        name, value, _ = parsed
        if _valid(value):
            out[name] = value
    return out


def describe() -> str:
    """Human-readable inventory for 'what did you learn'."""
    d = _dir()
    lines = []
    if d.is_dir():
        for f in sorted(d.glob("*.md")):
            parsed = _parse(f)
            if parsed is None:
                continue
            name, value, evidence = parsed
            state = "" if _valid(value) else " (stale — will re-check)"
            lines.append(f"{name}: {json.dumps(value)}{state}"
                         + (f" — {evidence}" if evidence else ""))
    if not lines:
        return "No machine facts learned yet."
    return "Machine facts I've learned and verified:\n" + "\n".join(lines)
