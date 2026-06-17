"""Tamper-evident audit log.

Append-only record of observations, actions, and decisions. Each entry carries a
SHA-256 hash chained over the previous entry's hash, so any deletion or edit of a
past record breaks the chain and `verify()` detects it.

Attaches to the orchestrator's EventBus, recording compact, serializable fields
(never raw objects) — so it's safe to persist and inspect.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field

from ..core import events

_GENESIS = "0" * 64


def _hash(prev: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256((prev + body).encode()).hexdigest()


@dataclass
class AuditLog:
    path: str | None = None          # JSONL file; None => in-memory only
    entries: list[dict] = field(default_factory=list)
    _last: str = _GENESIS

    def record(self, kind: str, data: dict) -> dict:
        payload = {"ts": time.time(), "kind": kind, "data": data,
                   "prev": self._last}
        payload["hash"] = _hash(self._last, {k: payload[k] for k in
                                             ("ts", "kind", "data", "prev")})
        self._last = payload["hash"]
        self.entries.append(payload)
        if self.path:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a") as f:
                f.write(json.dumps(payload, default=str) + "\n")
        return payload

    def verify(self) -> bool:
        """Re-walk the chain; True iff no entry was edited, deleted, or inserted."""
        prev = _GENESIS
        for e in self.entries:
            expect = _hash(prev, {k: e[k] for k in ("ts", "kind", "data", "prev")})
            if e.get("prev") != prev or e.get("hash") != expect:
                return False
            prev = e["hash"]
        return True

    # -- bus integration ----------------------------------------------------
    def attach(self, bus) -> "AuditLog":
        bus.subscribe(events.TASK_STARTED,
                      lambda goal: self.record("task_started", {"goal": str(goal)}))
        bus.subscribe(events.SCREEN_CHANGED, self._on_screen)
        bus.subscribe(events.ACTION_EXECUTED, self._on_action)
        bus.subscribe(events.ERROR_RAISED,
                      lambda err: self.record("error", {"error": str(err)}))
        bus.subscribe(events.TASK_FINISHED, self._on_finished)
        return self

    def _on_screen(self, state) -> None:
        self.record("observation", {
            "summary": getattr(state, "summary", ""),
            "elements": len(getattr(state, "elements", []) or [])})

    def _on_action(self, payload) -> None:
        call, result = payload
        self.record("action", {
            "tool": call.tool, "args": call.args,
            "ok": getattr(result, "ok", None),
            "output": str(getattr(result, "output", ""))[:200]})

    def _on_finished(self, result) -> None:
        self.record("task_finished", {
            "finished": getattr(result, "finished", None),
            "message": getattr(result, "message", ""),
            "steps": len(getattr(result, "steps", []) or [])})
