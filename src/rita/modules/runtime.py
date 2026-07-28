"""serve(): the ~30-line loop that makes a Python file a module process.

Handlers are `fn(params, emit) -> result`; `emit(name, data)` streams an
async event mid-call. `hello` and `shutdown` are served automatically.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from . import rpc

Handler = Callable[[dict, Callable[[str, Any], None]], Any]


def serve(*, name: str, version: str, handlers: dict[str, Handler],
          stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout.buffer

    def emit(event: str, data: Any = None) -> None:
        stdout.write(rpc.encode_event(event, data))
        stdout.flush()

    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = rpc.decode(line)
        except Exception:
            continue
        req_id = msg.get("id", -1)
        method = msg.get("method", "")
        params = msg.get("params") or {}
        if method == rpc.M_HELLO:
            out = rpc.encode_response(req_id, ok=True, result={
                "name": name, "version": version,
                "protocol": rpc.PROTOCOL_VERSION})
        elif method == rpc.M_SHUTDOWN:
            stdout.write(rpc.encode_response(req_id, ok=True, result="bye"))
            stdout.flush()
            return
        elif method in handlers:
            try:
                out = rpc.encode_response(req_id, ok=True,
                                          result=handlers[method](params, emit))
            except Exception as exc:
                out = rpc.encode_response(req_id, ok=False,
                                          error=f"{type(exc).__name__}: {exc}")
        else:
            out = rpc.encode_response(req_id, ok=False,
                                      error=f"unknown method {method!r}")
        stdout.write(out)
        stdout.flush()
