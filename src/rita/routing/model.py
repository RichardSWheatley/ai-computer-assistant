"""Value types for the deterministic router (Fix 1).

Everything here is a frozen dataclass: the router and wake gate are pure
functions over these values, so tests are tables and behavior is replayable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

_TOKEN_RE = re.compile(r"[a-z0-9_]+")

Kind = Literal["wake_only", "work", "chat", "control", "rename", "project"]
Verb = Literal["build", "flash", "measure", "run_samples", "report", "scaffold"]
MatchedBy = Literal["verb", "verb+entity", "entity_only", "control", "fallback"]


def normalize(text: str) -> str:
    """Lowercase, punctuation collapsed — the router's working form."""
    return " ".join(_TOKEN_RE.findall(text.lower()))


@dataclass(frozen=True)
class Word:
    """One STT word with its timing (seconds from stream start)."""

    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Utterance:
    """A transcribed utterance; word timings are optional (STT-dependent)."""

    text: str
    words: tuple[Word, ...] = ()
    t_start: float = 0.0
    t_end: float = 0.0

    @staticmethod
    def from_text(text: str) -> "Utterance":
        return Utterance(text=text.strip())

    @property
    def norm(self) -> str:
        return normalize(self.text)

    @property
    def tokens(self) -> tuple[str, ...]:
        return tuple(self.norm.split())


@dataclass(frozen=True)
class Entities:
    board: str | None = None        # canonical board name (boards.json key)
    sample: str | None = None
    peripheral: str | None = None
    artifact: str | None = None     # "application", "app", ...


@dataclass(frozen=True)
class Dispatch:
    """The router's output: what to do with an utterance. Pure data."""

    kind: Kind
    verb: Verb | None = None
    entities: Entities = field(default_factory=Entities)
    matched_by: MatchedBy = "fallback"
    argument: str | None = None     # e.g. the new name for kind="rename"
    residual: str = ""              # utterance minus any wake prefix


@dataclass(frozen=True)
class WakeDecision:
    woke: bool
    residual: Utterance | None = None
