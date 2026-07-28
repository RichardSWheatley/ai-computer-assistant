"""ModuleHandle: one live module process — spawn, handshake, call, monitor.

A dedicated reader thread demultiplexes responses (have an `id`) from async
events (don't), so a module can stream progress while a call is in flight.
Per-call timeouts are enforced; a dead process fails the pending call with
its stderr tail and the supervisor stays up.
"""

from __future__ import annotations

import subprocess
import threading
from collections import deque
from typing import Any

from . import rpc
from .manifest import Manifest


class ModuleError(RuntimeError):
    pass


class ModuleCallTimeout(ModuleError):
    pass


class ModuleHandle:
    def __init__(self, manifest: Manifest, proc: subprocess.Popen) -> None:
        self.manifest = manifest
        self.proc = proc
        self.claims: dict[str, str] = {}
        self._cond = threading.Condition()
        self._responses: dict[int, dict] = {}
        self._events: deque[tuple[str, Any]] = deque()
        self._stderr: deque[str] = deque(maxlen=50)
        self._next_id = 0
        self._dead = False
        threading.Thread(target=self._read_stdout, daemon=True,
                         name=f"{manifest.name}-out").start()
        threading.Thread(target=self._read_stderr, daemon=True,
                         name=f"{manifest.name}-err").start()

    # --- spawn + handshake --------------------------------------------------

    @classmethod
    def spawn(cls, manifest: Manifest, *, supervisor_version: str,
              handshake_timeout: float = 5.0, spawn_kwargs: dict | None = None
              ) -> "ModuleHandle":
        kwargs = dict(spawn_kwargs or {})
        try:
            proc = subprocess.Popen(list(manifest.entrypoint),
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, **kwargs)
        except OSError as exc:
            raise ModuleError(f"cannot spawn {manifest.name}: {exc}") from exc
        handle = cls(manifest, proc)
        try:
            hello = handle.call(rpc.M_HELLO,
                                {"supervisor_version": supervisor_version,
                                 "protocol": rpc.PROTOCOL_VERSION},
                                timeout=handshake_timeout)
        except ModuleError as exc:
            handle.kill()
            raise ModuleError(
                f"{manifest.name} handshake failed: {exc}") from exc
        if not isinstance(hello, dict) \
                or hello.get("protocol") != rpc.PROTOCOL_VERSION \
                or hello.get("name") != manifest.name:
            handle.kill()
            raise ModuleError(
                f"{manifest.name} handshake mismatch: {hello!r}")
        return handle

    # --- reader threads -----------------------------------------------------

    def _read_stdout(self) -> None:
        stream = self.proc.stdout
        for line in iter(stream.readline, b""):
            try:
                msg = rpc.decode(line)
            except Exception:
                continue  # non-protocol noise on stdout is ignored
            with self._cond:
                if rpc.is_event(msg):
                    self._events.append((msg.get("event"), msg.get("data")))
                else:
                    self._responses[msg.get("id", -1)] = msg
                self._cond.notify_all()
        with self._cond:
            self._dead = True
            self._cond.notify_all()

    def _read_stderr(self) -> None:
        for line in iter(self.proc.stderr.readline, b""):
            self._stderr.append(line.decode(errors="replace").rstrip())

    # --- calls --------------------------------------------------------------

    def call(self, method: str, params: dict | None = None,
             timeout: float = 30.0) -> Any:
        with self._cond:
            if self._dead:
                raise ModuleError(f"{self.manifest.name} is dead: "
                                  f"{self.stderr_tail()}")
            self._next_id += 1
            req_id = self._next_id
        try:
            self.proc.stdin.write(rpc.encode_request(req_id, method, params))
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ModuleError(f"{self.manifest.name} pipe broken: "
                              f"{self.stderr_tail()}") from exc
        with self._cond:
            ok = self._cond.wait_for(
                lambda: req_id in self._responses or self._dead,
                timeout=timeout)
            if req_id in self._responses:
                msg = self._responses.pop(req_id)
            elif self._dead:
                raise ModuleError(f"{self.manifest.name} died during "
                                  f"{method!r}: {self.stderr_tail()}")
            elif not ok:
                raise ModuleCallTimeout(
                    f"{self.manifest.name}.{method} timed out after {timeout}s")
        if not msg.get("ok", False):
            raise ModuleError(f"{self.manifest.name}.{method}: "
                              f"{msg.get('error')}")
        return msg.get("result")

    def try_call(self, method: str, params: dict | None = None,
                 timeout: float = 30.0) -> Any:
        """Like call(), but a module-side error comes back as a value
        ({"ok": False, "error": ...}) instead of raising — for stub probing."""
        try:
            result = self.call(method, params, timeout)
        except ModuleCallTimeout:
            raise
        except ModuleError as exc:
            return {"ok": False, "error": str(exc)}
        if isinstance(result, dict) and "ok" in result:
            return result
        return {"ok": True, "result": result}

    # --- events + lifecycle -------------------------------------------------

    def drain_events(self) -> list[tuple[str, Any]]:
        with self._cond:
            out = list(self._events)
            self._events.clear()
            return out

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    def stderr_tail(self) -> str:
        return "\n".join(self._stderr)

    def shutdown(self, timeout: float = 3.0) -> None:
        try:
            self.call(rpc.M_SHUTDOWN, timeout=timeout)
        except ModuleError:
            pass
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:  # pragma: no cover - stuck child
            self.kill()

    def kill(self) -> None:
        if self.alive:
            self.proc.kill()
            self.proc.wait(timeout=5)
