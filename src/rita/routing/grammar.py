"""The routing grammar: RITA's own domain vocabulary as data.

These tables ARE the router's behavior — routing is matching against them,
never semantic judgment. Extend the tables, not the code.
"""

from __future__ import annotations

import re

# Work verbs: token -> canonical verb. First matching token in the utterance
# decides the verb.
VERB_TOKENS: dict[str, str] = {
    "build": "build", "rebuild": "build", "compile": "build",
    "flash": "flash", "reflash": "flash",
    "measure": "measure",
    "run": "run_samples",
    "report": "report",
    "write": "scaffold", "create": "scaffold", "make": "scaffold",
    "scaffold": "scaffold",
}

# Whole-utterance control words (filler like "please" is ignored).
CONTROL_TOKENS = {"pause", "resume", "continue", "stop", "cancel", "halt"}
_FILLER_TOKENS = {"please", "now", "it", "that"}

GREETING_TOKENS = {"hello", "hi", "hey"}

# Interrogative shapes stay chat even when they name a board/sample.
INTERROGATIVE_PREFIXES = (
    "tell me about", "tell me", "what", "whats", "who", "whos", "when",
    "where", "why", "how", "explain", "describe", "define",
)

ARTIFACT_TOKENS = {"application", "app", "program", "firmware", "project",
                   "example", "sample", "test"}

# Project handoff patterns; group 1 is the goal handed to RITA.
PROJECT_PATTERNS = (
    re.compile(r"^(?:start|create|plan|begin)(?: a| the)? project(?: to)?[:,]?\s+(.+)$"),
    re.compile(r"^take on\s+(.+)$"),
    re.compile(r"^hand(?:ing)? off\s+(.+)$"),
)


# Self-check phrases: a report, never a task.
DIAGNOSTIC_PATTERNS = (
    re.compile(r"^(?:run |do )?(?:a )?diagnostics?$"),
    re.compile(r"^check (?:your |the |my )?setup$"),
    re.compile(r"^(?:run |do )?(?:a )?(?:setup|self)[ -]?check$"),
    re.compile(r"^what(?:'?s| is) (?:wrong|broken|missing)$"),
)


def is_diagnostic(norm: str) -> bool:
    return any(p.match(norm) for p in DIAGNOSTIC_PATTERNS)


def project_goal(norm: str) -> str | None:
    for pat in PROJECT_PATTERNS:
        m = pat.match(norm)
        if m:
            return m.group(1)
    return None


# Rename patterns over normalized text; group 1 is the new name.
RENAME_PATTERNS = (
    re.compile(r"\byour name is (?:now )?(\w+)"),
    re.compile(r"\bcall yourself (\w+)"),
    re.compile(r"\bchange your name to (\w+)"),
)


def is_control(tokens: tuple[str, ...]) -> bool:
    meaningful = [t for t in tokens if t not in _FILLER_TOKENS]
    return len(meaningful) == 1 and meaningful[0] in CONTROL_TOKENS


def is_interrogative(norm: str) -> bool:
    return norm.startswith(INTERROGATIVE_PREFIXES)


def rename_target(norm: str) -> str | None:
    for pat in RENAME_PATTERNS:
        m = pat.search(norm)
        if m:
            return m.group(1)
    return None
