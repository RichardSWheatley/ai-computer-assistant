"""Module IPC wire contract: newline JSON over stdio.

Same request/response shape as rita.workers.protocol (kept untouched for
the legacy eyes/hands worker), plus what modules need:

  request:  {"id": 1, "method": "start", "params": {...}}
  response: {"id": 1, "ok": true, "result": ..., "error": null}
  event:    {"event": "progress", "data": {...}}        # no id — async

The `hello` handshake is mandatory before anything else and carries the
protocol + version facts both sides verify.
"""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_VERSION = "2.0"

# Methods every module must serve.
M_HELLO = "hello"
M_START = "start"
M_STATUS = "status"
M_PAUSE_AT_CHECKPOINT = "pause_at_checkpoint"
M_RESUME = "resume"
M_STOP = "stop"
M_RESULT = "result"
M_SHUTDOWN = "shutdown"


def encode_request(req_id: int, method: str, params: dict | None = None) -> bytes:
    return (json.dumps({"id": req_id, "method": method,
                        "params": params or {}}) + "\n").encode()


def encode_response(req_id: int, *, ok: bool, result: Any = None,
                    error: str | None = None) -> bytes:
    return (json.dumps({"id": req_id, "ok": ok, "result": result,
                        "error": error}) + "\n").encode()


def encode_event(name: str, data: Any = None) -> bytes:
    return (json.dumps({"event": name, "data": data}) + "\n").encode()


def decode(line: str | bytes) -> dict:
    if isinstance(line, bytes):
        line = line.decode()
    return json.loads(line)


def is_event(msg: dict) -> bool:
    return "event" in msg and "id" not in msg
