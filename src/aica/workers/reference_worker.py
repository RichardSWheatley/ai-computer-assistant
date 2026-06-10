"""Reference worker — a Python stand-in for the future Rust binary.

It speaks the exact wire protocol (docs/WORKER-PROTOCOL.md), so it lets the
whole system run and be tested today. Replace it with a compiled Rust worker
by pointing WorkerClient.command at the binary — nothing else changes.

Run standalone:  python -m aica.workers.reference_worker
"""

from __future__ import annotations

import sys

from . import protocol as P


def _handle(req: P.Request) -> P.Response:
    m, p = req.method, req.params
    if m == P.M_PING:
        return P.ok(req.id, {"version": P.PROTOCOL_VERSION, "impl": "python-reference"})
    if m == P.M_CAPTURE:
        # A real worker captures the screen + accessibility tree here.
        return P.ok(req.id, {
            "summary": "reference desktop",
            "screenshot_path": None,
            "elements": [
                {"label": "Start", "role": "button", "x": 10, "y": 1060, "source": "a11y"},
            ],
        })
    if m == P.M_CLICK:
        return P.ok(req.id, {"detail": f"[ref] click {p.get('button','left')} "
                                       f"@ ({p.get('x')},{p.get('y')})"})
    if m == P.M_TYPE:
        return P.ok(req.id, {"detail": f"[ref] typed {len(str(p.get('text','')))} chars"})
    if m == P.M_HOTKEY:
        return P.ok(req.id, {"detail": f"[ref] hotkey {'+'.join(p.get('keys', []))}"})
    if m == P.M_KILL:
        return P.ok(req.id, {"detail": "[ref] kill switch engaged"})
    if m == P.M_SHUTDOWN:
        return P.ok(req.id, {"detail": "bye"})
    return P.err(req.id, f"unknown method: {m}")


def serve(stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    for raw in iter(stdin.readline, b""):
        if not raw.strip():
            continue
        try:
            req = P.parse_request(raw)
            resp = _handle(req)
        except Exception as exc:  # never crash the worker on a bad line
            resp = P.err(-1, f"{type(exc).__name__}: {exc}")
        stdout.write(resp.encode())
        stdout.flush()
        if req.method == P.M_SHUTDOWN:  # type: ignore[name-defined]
            break


if __name__ == "__main__":
    serve()
