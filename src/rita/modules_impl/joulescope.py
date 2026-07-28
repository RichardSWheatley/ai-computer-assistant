"""joulescope module — HONEST STUB (max_instances = 1: there is one probe).

Power measurement hardware is not attached in this install; start reports
the truth. The real implementation lands with the bench milestone
(docs/BENCH-PLAN.md) — measurements are gates, so they are never simulated.
"""

from __future__ import annotations

from ..modules.runtime import serve

_NOT_PRESENT = {"ok": False,
                "error": "Joulescope hardware is not present; the device "
                         "tier is blocked on the bench milestone"}


def start(params, emit):
    return dict(_NOT_PRESENT)


def status(params, emit):
    return dict(_NOT_PRESENT)


if __name__ == "__main__":  # pragma: no cover - exercised as a child process
    serve(name="joulescope", version="0.1.0",
          handlers={"start": start, "status": status})
