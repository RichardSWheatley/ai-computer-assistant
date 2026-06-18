"""Spawn a worker subprocess and do synchronous request/response over stdio.

The worker `command` is configurable, so the same client drives:
  - the bundled Python reference worker (default, for dev/CI/this container), or
  - a compiled Rust worker binary (production) — same protocol, zero code change.
"""

from __future__ import annotations

import subprocess
import sys
from itertools import count
from typing import Any

from . import protocol as P


class WorkerError(RuntimeError):
    pass


class WorkerClient:
    def __init__(self, command: list[str] | None = None, sandbox=None) -> None:
        # Default: run the Python reference worker in-tree.
        self.command = command or [sys.executable, "-m",
                                   "aica.workers.reference_worker"]
        # Optional security.sandbox.SandboxPolicy — scrubs env, sets cwd + rlimits
        # so the worker never sees secrets and can't exceed resource bounds.
        self.sandbox = sandbox
        self._proc: subprocess.Popen | None = None
        self._ids = count(1)

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> "WorkerClient":
        if self._proc is not None:
            return self
        extra: dict = {}
        if self.sandbox is not None:
            from ..security.sandbox import spawn_kwargs
            extra = spawn_kwargs(self.sandbox)
        self._proc = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            bufsize=0, **extra,
        )
        return self

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self.call(P.M_SHUTDOWN, timeout=2)
        except Exception:
            pass
        try:
            self._proc.wait(timeout=2)
        except Exception:
            self._proc.kill()
        self._proc = None

    def __enter__(self) -> "WorkerClient":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- rpc ----------------------------------------------------------------
    def call(self, method: str, params: dict[str, Any] | None = None,
             timeout: float | None = None) -> Any:
        if self._proc is None:
            self.start()
        assert self._proc and self._proc.stdin and self._proc.stdout

        req = P.Request(id=next(self._ids), method=method, params=params or {})
        self._proc.stdin.write(req.encode())
        self._proc.stdin.flush()

        line = self._proc.stdout.readline()
        if not line:
            raise WorkerError(f"worker closed the pipe during {method!r}")
        resp = P.Response.decode(line)
        if not resp.ok:
            raise WorkerError(resp.error or f"{method} failed")
        return resp.result
