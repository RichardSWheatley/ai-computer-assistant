"""Fit judging (Fix 2, step 2): Claude judges fit ONLY.

One bounded call over the top index matches — README + yaml facts in, a
choice + reason out. Claude cannot introduce candidates the index didn't
return, and the answer never schedules anything: the orchestrator does.
`complete` is any text-completion callable (the claude-worker in production,
a lambda in tests).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .index import IndexEntry

Complete = Callable[[str], str]

_PROMPT = """You are judging which existing Zephyr suite verifies a user's intent.
Intent: {goal}

Candidates:
{candidates}

Answer with ONLY a JSON object: {{"fit": "<candidate id or none>", "reason": "<one sentence>"}}.
Pick a candidate only if running it would genuinely verify the intent."""


@dataclass(frozen=True)
class FitDecision:
    entry: IndexEntry | None
    reason: str


def _describe(e: IndexEntry, workspace: Path | None) -> str:
    lines = [f"- id: {e.id}", f"  path: {e.path}",
             f"  tags: {' '.join(e.tags)}", f"  harness: {e.harness or 'ztest'}"]
    if e.description:
        lines.append(f"  description: {e.description}")
    if workspace and e.readme_path:
        readme = (workspace / e.readme_path)
        if readme.exists():
            lines.append("  readme: " + readme.read_text()[:2000].replace("\n", " "))
    return "\n".join(lines)


def judge_fit(goal: str, candidates: Sequence[IndexEntry], complete: Complete,
              workspace: str | Path | None = None) -> FitDecision:
    if not candidates:
        return FitDecision(entry=None, reason="no candidates from the index")
    ws = Path(workspace) if workspace else None
    prompt = _PROMPT.format(goal=goal,
                            candidates="\n".join(_describe(e, ws) for e in candidates))
    raw = complete(prompt)
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        answer = json.loads(m.group(0) if m else raw)
        chosen_id = str(answer.get("fit", "none"))
        reason = str(answer.get("reason", ""))
    except Exception:
        return FitDecision(entry=None, reason=f"unparseable judgment: {raw[:120]}")
    entry = next((e for e in candidates if e.id == chosen_id), None)
    if entry is None and chosen_id not in ("none", ""):
        reason = f"judge named a non-candidate ({chosen_id}); treated as no fit"
    return FitDecision(entry=entry, reason=reason)
