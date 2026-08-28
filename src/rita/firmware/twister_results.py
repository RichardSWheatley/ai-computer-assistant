"""twister.json parsing — the ONLY source of gate truth (never stdout).

A failed suite becomes a `FailureArtifact`: the concrete thing the coding agent is
handed to produce a patch. No artifact, no coder invocation — that
invariant starts here, because artifacts can only be built from parsed gate
results.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_FILE_HINT_RE = re.compile(r"[\w./-]+\.(?:c|h|cpp|conf|overlay|yaml|cmake|ld)\b")

_OK_STATUSES = {"passed", "skipped", "filtered", "notrun"}


@dataclass(frozen=True)
class FailureArtifact:
    kind: Literal["compile", "test", "static", "unit"]
    suite: str
    platform: str
    reason: str
    log_excerpt: str
    file_hints: tuple[str, ...]
    testcase: str | None = None      # failing testcase id when known

    def describe(self) -> str:
        lines = [f"{self.kind} failure in {self.suite} on {self.platform}:",
                 f"reason: {self.reason}"]
        if self.testcase:
            lines.append(f"testcase: {self.testcase}")
        if self.file_hints:
            lines.append("files implicated: " + ", ".join(self.file_hints))
        lines.append("log:\n" + self.log_excerpt)
        return "\n".join(lines)


@dataclass(frozen=True)
class TwisterResult:
    ok: bool
    suites_run: int
    failures: tuple[FailureArtifact, ...]
    path: str                        # the twister.json this came from


def _artifact(suite: dict) -> FailureArtifact:
    reason = str(suite.get("reason") or suite.get("status") or "failed")
    log = str(suite.get("log") or "")[:4000]
    kind = "compile" if "build" in reason.lower() else "test"
    failing_case = next((c.get("identifier") for c in suite.get("testcases") or []
                         if str(c.get("status", "")).lower()
                         not in _OK_STATUSES and c.get("status")), None)
    return FailureArtifact(
        kind=kind,
        suite=str(suite.get("name") or "?"),
        platform=str(suite.get("platform") or "?"),
        reason=reason,
        log_excerpt=log or reason,
        file_hints=tuple(dict.fromkeys(_FILE_HINT_RE.findall(log))),
        testcase=failing_case,
    )


def parse_twister_json(path: str | Path) -> TwisterResult:
    p = Path(path)
    data = json.loads(p.read_text())
    suites = data.get("testsuites") or []
    failures = tuple(_artifact(s) for s in suites
                     if str(s.get("status", "")).lower() not in _OK_STATUSES)
    ran = [s for s in suites
           if str(s.get("status", "")).lower() not in ("skipped", "filtered")]
    return TwisterResult(ok=not failures and bool(ran), suites_run=len(ran),
                         failures=failures, path=str(p))
