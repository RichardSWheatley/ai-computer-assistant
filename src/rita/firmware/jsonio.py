"""The agent JSON contract, enforced in one place.

Agents drift into prose ("Sure! I'll create the files…") even when the
prompt demands JSON. The contract: parse; on failure remind ONCE —
JSON only, no prose, no fences — and retry; a second failure raises
with the reply's head QUOTED, so a live failure is diagnosable from
the message alone (never a bare "Expecting value: line 1 column 1").
"""

from __future__ import annotations

import json
import re

_RETRY_SUFFIX = (
    "\n\nYour previous reply was not a valid JSON object. Reply again "
    "with ONLY the JSON object — no prose, no code fences, no "
    "explanation before or after.")


def extract_json(raw: str):
    """The outermost JSON object in a reply (fenced or bare)."""
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    return json.loads(m.group(0) if m else (raw or ""))


def ask_json(complete, prompt: str, *, what: str) -> dict:
    """A JSON-object answer from the agent, or ValueError with evidence."""
    raw = complete(prompt)
    problem = ""
    for attempt in (0, 1):
        try:
            data = extract_json(raw)
        except Exception as exc:
            problem = str(exc)
        else:
            if isinstance(data, dict):
                return data
            problem = f"got a JSON {type(data).__name__}, not an object"
        if attempt == 0:
            raw = complete(prompt + _RETRY_SUFFIX)
    head = (raw or "").strip()
    head = head[:200] if head else "<empty reply>"
    raise ValueError(f"{what} returned unparseable output even after a "
                     f"JSON-only retry ({problem}); the reply began: "
                     f"{head!r}")
