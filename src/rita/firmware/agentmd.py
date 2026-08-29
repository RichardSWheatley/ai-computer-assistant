"""AGENTS.md: RITA writes the coding agent's context at runtime.

Agent CLIs read an AGENTS.md from their working directory (the open
agent-context convention). RITA generates it DETERMINISTICALLY from her
own data — synced board facts, the coding contract, the gate sequence,
and the relevant knowledge-pack notes — into every directory the agent
works in, refreshed on every run. Never written into upstream workspace
directories; the pipeline only hands the agent directories RITA owns.
"""

from __future__ import annotations

import json
from pathlib import Path

_CONTRACT = """\
## Coding contract (enforced by RITA's gates)

- Every function must either RESTRICT its input and output parameters
  (constrained types, enforced ranges) or VALIDATE them before executing
  (guard clauses rejecting invalid input). Every function is unit-tested
  for its parameters — valid, boundary, invalid — before anything moves on.
- Do exactly one step per invocation. Do not run tests, do not judge
  success — the orchestrator re-runs the gates after every change.
- Gate sequence every change must pass: CERBERUS static check ->
  per-function Unity tests (compiled with arm-none-eabi-gcc, run under
  QEMU) -> the Zephyr suite under twister.
"""


def _board_facts(board: str) -> str:
    from ..home import boards_json_path

    p = boards_json_path()
    if not p.exists():
        return ""
    try:
        info = json.loads(p.read_text()).get("boards", {}).get(board)
    except Exception:
        return ""
    if not info:
        return ""
    supported = ", ".join(info.get("supported", [])[:12]) or "unknown"
    return (f"- vendor: {info.get('vendor', 'unknown')}\n"
            f"- arch: {info.get('arch', '?')}\n"
            f"- twister platform: {info.get('twister_platform', board)}\n"
            f"- supported peripherals: {supported}\n")


def write_agent_context(dest: str | Path, *, goal: str, board: str,
                        terms: list[str] | None = None) -> Path:
    """Write/refresh AGENTS.md in a directory RITA owns."""
    from . import knowledge

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    parts = [
        "# Context from RITA (generated — refreshed every run)",
        "",
        f"## Task\n\n{goal}\n\nTarget board: **{board}**",
    ]
    facts = _board_facts(board)
    if facts:
        parts.append(f"## Board facts (from the user's synced workspace)\n\n{facts}")
    parts.append(_CONTRACT)
    from ..learning import facts as machine_facts

    known = machine_facts.all_facts()
    if known:
        lines = "\n".join(f"- {name}: {json.dumps(value)}"
                          for name, value in known.items())
        parts.append("## Machine facts (agent-investigated, verified "
                     f"by RITA)\n\n{lines}\n")
    notes = knowledge.notes_for(list(terms or []) + goal.split(),
                                max_chars=3000)
    if notes.strip():
        parts.append(f"## Zephyr notes (curated, each topic cites its source)\n\n{notes}")
    path = dest / "AGENTS.md"
    path.write_text("\n".join(parts) + "\n")
    return path
