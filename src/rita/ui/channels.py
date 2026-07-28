"""Speech vs screen output channels (Fix 5).

The brain is prompted to emit both channels, but this deterministic strip
is the GUARANTEE: whatever the model returns, code never reaches the TTS
path. Reading code aloud is a test failure, not a style issue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FALLBACK_SPEECH = "The details are on your screen."

_FENCED_RE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]*`?")
_URL_RE = re.compile(r"https?://\S+")
_PATH_RE = re.compile(r"(?:~?/|[A-Za-z]:\\)[\w./\\-]+")
_CODE_FILE_RE = re.compile(
    r"\S+\.(?:c|h|cpp|hpp|py|rs|yaml|yml|json|log|md|rst|conf|overlay|cmake|txt|ld|sh|bat)\b")
_DIFF_LINE_RE = re.compile(r"^\s*(?:diff |index |@@|[+-])")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Reply:
    speech: str   # <= max_sentences conversational sentences, zero code tokens
    screen: str   # the full response, byte-for-byte


def _mostly_symbols(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 8:
        return False
    plain = sum(ch.isalnum() or ch.isspace() for ch in stripped)
    return plain / len(stripped) < 0.6


def split_response(text: str, max_sentences: int = 2) -> Reply:
    screen = text or ""

    cleaned = _FENCED_RE.sub(" ", screen)
    kept_lines = []
    for line in cleaned.splitlines():
        if _DIFF_LINE_RE.match(line) or _mostly_symbols(line):
            continue
        kept_lines.append(line)
    flat = " ".join(kept_lines)
    for rx in (_INLINE_CODE_RE, _URL_RE, _PATH_RE, _CODE_FILE_RE):
        flat = rx.sub(" ", flat)
    flat = re.sub(r"\s+", " ", flat).strip()
    # A stripped token can leave dangling connectives ("See  for details.").
    flat = re.sub(r"\s+([.,;:!?])", r"\1", flat)

    sentences = [s for s in _SENTENCE_SPLIT.split(flat) if any(c.isalpha() for c in s)]
    speech = " ".join(sentences[:max_sentences]).strip()
    if not speech:
        speech = FALLBACK_SPEECH
    return Reply(speech=speech, screen=screen)
