"""Prompt-injection / jailbreak detection and neutralization for untrusted text.

Two jobs:
  - neutralize(): strip invisible / bidi / tag characters that hide injected
    instructions from a human reviewer but not from the model.
  - scan(): heuristic risk score + reasons for imperative content that tries to
    override the agent. Detection-only — used to quarantine or escalate
    confirmation, not to "clean" prose (you can't reliably sanitize natural
    language; you contain it).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Zero-width, BOM, bidi overrides, and Unicode "tag" chars used to smuggle text.
_INVISIBLE = re.compile(
    "[​-‏‪-‮⁠-⁤⁦-⁩﻿"
    "\U000e0000-\U000e007f]"
)

# Benign signatures of override attempts (detection only — not attack recipes).
_SUSPICIOUS = [
    r"ignore (all |the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (the |all )?(previous|above|system)",
    r"you are now\b",
    r"new (instructions|task|system prompt)",
    r"system prompt",
    r"developer mode",
    r"reveal (your |the )?(system prompt|instructions|secrets?|api key)",
    r"exfiltrate|send (it |this |them )?to\b|forward (this|it) to",
    r"\bcurl\b|\bwget\b|http[s]?://",
    r"delete (all|everything)|rm -rf",
    r"<untrusted_data|</untrusted_data|<\s*system\b|\[/?INST\]",
]
_SUSPICIOUS_RE = [re.compile(p, re.IGNORECASE) for p in _SUSPICIOUS]


@dataclass
class InjectionFinding:
    risk: float = 0.0           # 0.0 (clean) .. 1.0 (very likely injection)
    reasons: list[str] = field(default_factory=list)

    @property
    def suspicious(self) -> bool:
        return self.risk >= 0.5


def neutralize(text: str) -> str:
    """Remove invisible/bidi/tag characters; normalize to NFKC."""
    if not text:
        return text
    text = _INVISIBLE.sub("", text)
    return unicodedata.normalize("NFKC", text)


def scan(text: str) -> InjectionFinding:
    if not text:
        return InjectionFinding()
    reasons: list[str] = []
    risk = 0.0

    if _INVISIBLE.search(text):
        reasons.append("hidden/invisible characters")
        risk += 0.5

    hits = [p.pattern for p in _SUSPICIOUS_RE if p.search(text)]
    if hits:
        reasons.append(f"override-style phrases ({len(hits)})")
        risk += min(0.4 + 0.15 * len(hits), 0.6)

    return InjectionFinding(risk=min(risk, 1.0), reasons=reasons)
