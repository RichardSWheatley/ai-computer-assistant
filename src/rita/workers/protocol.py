"""The wire contract shared by every worker implementation (Python or Rust).

A request/response is one JSON object per line:

  -> {"id": 1, "method": "capture", "params": {}}
  <- {"id": 1, "ok": true, "result": {...}, "error": null}

Keep this file the single source of truth for method names and shapes so the
native worker and the Python proxy never drift.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

PROTOCOL_VERSION = "1.0"

# --- Methods (the worker must implement these) -----------------------------
M_PING = "ping"            # params: {}                 -> {"version": str}
M_CAPTURE = "capture"      # params: {}                 -> {"summary","screenshot_path","elements"}
M_CLICK = "click"          # params: {x,y,button}       -> {"detail"}
M_TYPE = "type_text"       # params: {text}             -> {"detail"}
M_HOTKEY = "hotkey"        # params: {keys: [str]}      -> {"detail"}
M_KILL = "kill"            # params: {}                 -> {"detail"}  (engage kill switch)
M_SHUTDOWN = "shutdown"    # params: {}                 -> {"detail"}  (exit worker)


@dataclass
class Request:
    id: int
    method: str
    params: dict[str, Any] = field(default_factory=dict)

    def encode(self) -> bytes:
        return (json.dumps({"id": self.id, "method": self.method,
                            "params": self.params}) + "\n").encode()


@dataclass
class Response:
    id: int
    ok: bool
    result: Any = None
    error: str | None = None

    def encode(self) -> bytes:
        return (json.dumps({"id": self.id, "ok": self.ok,
                            "result": self.result, "error": self.error}) + "\n").encode()

    @staticmethod
    def decode(line: str | bytes) -> "Response":
        if isinstance(line, bytes):
            line = line.decode()
        d = json.loads(line)
        return Response(id=d.get("id", -1), ok=d.get("ok", False),
                        result=d.get("result"), error=d.get("error"))


def ok(req_id: int, result: Any = None) -> Response:
    return Response(id=req_id, ok=True, result=result)


def err(req_id: int, message: str) -> Response:
    return Response(id=req_id, ok=False, error=message)


def parse_request(line: str | bytes) -> Request:
    if isinstance(line, bytes):
        line = line.decode()
    d = json.loads(line)
    return Request(id=d.get("id", -1), method=d.get("method", ""),
                   params=d.get("params", {}) or {})


# Re-export for convenience in workers written in Python.
__all__ = [
    "PROTOCOL_VERSION", "Request", "Response", "ok", "err", "parse_request",
    "M_PING", "M_CAPTURE", "M_CLICK", "M_TYPE", "M_HOTKEY", "M_KILL", "M_SHUTDOWN",
    "asdict",
]
