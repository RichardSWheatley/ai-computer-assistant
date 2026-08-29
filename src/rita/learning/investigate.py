"""Agent investigation with deterministic validation.

The agent's answer is DATA — a strict-JSON claim about this machine.
RITA runs the caller's `validate` on it before the claim is used or
remembered; an unverifiable claim is discarded and reported, never
trusted. Gates own truth here exactly as they do in the pipeline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    question: str
    answer: dict           # the validated JSON claim
    evidence: str          # the validator's confirmation


_PROMPT = (
    "You are investigating THIS machine for RITA, a deterministic "
    "orchestrator. You may read files and directories on this machine "
    "and you may search online documentation when local information "
    "is not enough. Do not change anything. Answer with STRICT JSON "
    "only — no prose, no code fences — exactly this shape: {schema}\n"
    "Question: {question}")


def investigate(complete, question: str, *, schema: str,
                validate) -> tuple[Finding | None, str]:
    """(finding, note). `complete` is the agent's completion callable;
    `validate(claim) -> str | None` returns evidence when the claim
    checks out on this machine, None when it does not."""
    try:
        raw = complete(_PROMPT.format(schema=schema, question=question))
    except Exception as exc:
        return None, f"the agent could not be asked: {exc}"
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    try:
        claim = json.loads(m.group(0) if m else (raw or ""))
    except Exception as exc:
        return None, f"the agent's answer was not strict JSON ({exc})"
    if not isinstance(claim, dict):
        return None, "the agent's answer was not a JSON object"
    try:
        evidence = validate(claim)
    except Exception as exc:
        evidence = None
        note = f"validating the claim failed: {exc}"
    else:
        note = (f"the agent claimed {json.dumps(claim)[:200]} but RITA "
                f"could not verify it on this machine — discarded")
    if evidence is None:
        return None, note
    return Finding(question=question, answer=claim, evidence=evidence), evidence
