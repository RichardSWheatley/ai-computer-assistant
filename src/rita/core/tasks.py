"""The task manager (Fix 4): PAUSE / RESUME / STOP with safe checkpoints.

A task runs `fn(ctl)` on a worker thread; the pipeline (Fix 3) calls
`ctl.checkpoint(stage)` ONLY between stages, so hardware operations stay
atomic. PAUSE blocks the worker inside the run at the next checkpoint —
which is why RESUME needs no replay logic: execution continues exactly
where it stopped (a task paused after BUILD resumes into SIM_TEST without
rebuilding). STOP raises `TaskStopped` at the boundary and the task reports
partial results; the manager itself survives and keeps accepting work.

State machine:
  PENDING -> RUNNING -> DONE | FAILED
  RUNNING --pause--> PAUSING --checkpoint--> PAUSED --resume--> RUNNING
  RUNNING | PAUSING | PAUSED --stop--> STOPPING --boundary--> STOPPED
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

_ACTIVE = ("PENDING", "RUNNING", "PAUSING", "PAUSED", "STOPPING")


class TaskStopped(Exception):
    """Raised inside a task at its next checkpoint after a STOP request."""


@dataclass
class _Record:
    id: str
    name: str
    state: str = "PENDING"
    completed_stages: list[str] = field(default_factory=list)
    result: Any = None
    error: str = ""
    # Monotonic timestamps so status can say HOW LONG a task has been
    # at it — 0.0 means "hasn't happened yet".
    started_at: float = 0.0
    stage_at: float = 0.0


@dataclass(frozen=True)
class TaskReport:
    id: str
    name: str
    state: str
    completed_stages: tuple[str, ...]
    result: Any
    error: str
    started_at: float = 0.0
    stage_at: float = 0.0


class TaskControl:
    """Handed to the running task; `checkpoint` is the only safe boundary."""

    def __init__(self, record: _Record, cond: threading.Condition) -> None:
        self._record = record
        self._cond = cond

    def checkpoint(self, completed_stage: str) -> None:
        with self._cond:
            self._record.completed_stages.append(completed_stage)
            self._record.stage_at = time.monotonic()
            if self._record.state == "STOPPING":
                raise TaskStopped(completed_stage)
            if self._record.state == "PAUSING":
                self._record.state = "PAUSED"
                self._cond.notify_all()
                while self._record.state == "PAUSED":
                    self._cond.wait()
                if self._record.state == "STOPPING":
                    raise TaskStopped(completed_stage)


class TaskManager:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._records: dict[str, _Record] = {}
        self._ids = itertools.count(1)

    # --- lifecycle ----------------------------------------------------------

    def submit(self, name: str, fn: Callable[[TaskControl], Any]) -> str:
        with self._cond:
            tid = f"task-{next(self._ids)}"
            record = _Record(id=tid, name=name)
            self._records[tid] = record
        ctl = TaskControl(record, self._cond)
        thread = threading.Thread(target=self._run, args=(record, fn, ctl),
                                  daemon=True, name=tid)
        thread.start()
        return tid

    def _run(self, record: _Record, fn, ctl: TaskControl) -> None:
        with self._cond:
            record.state = "RUNNING"
            record.started_at = time.monotonic()
        try:
            result = fn(ctl)
        except TaskStopped:
            with self._cond:
                record.state = "STOPPED"
                self._cond.notify_all()
        except Exception as exc:  # crash isolation: FAILED, manager survives
            with self._cond:
                record.state = "FAILED"
                record.error = f"{type(exc).__name__}: {exc}"
                self._cond.notify_all()
        else:
            with self._cond:
                record.result = result
                record.state = "DONE"   # finished work is DONE even post-stop
                self._cond.notify_all()

    # --- controls -----------------------------------------------------------

    def pause(self, tid: str) -> bool:
        with self._cond:
            r = self._records[tid]
            if r.state == "RUNNING":
                r.state = "PAUSING"     # "pausing after current step…"
                self._cond.notify_all()
                return True
            return False

    def resume(self, tid: str) -> bool:
        with self._cond:
            r = self._records[tid]
            if r.state in ("PAUSED", "PAUSING"):
                r.state = "RUNNING"
                self._cond.notify_all()
                return True
            return False

    def stop(self, tid: str) -> bool:
        with self._cond:
            r = self._records[tid]
            if r.state in ("RUNNING", "PAUSING", "PAUSED"):
                r.state = "STOPPING"
                self._cond.notify_all()  # wakes a PAUSED task so it can cancel
                return True
            return False

    # --- introspection ------------------------------------------------------

    def state(self, tid: str) -> str:
        with self._cond:
            return self._records[tid].state

    def report(self, tid: str) -> TaskReport:
        with self._cond:
            r = self._records[tid]
            return TaskReport(id=r.id, name=r.name, state=r.state,
                              completed_stages=tuple(r.completed_stages),
                              result=r.result, error=r.error,
                              started_at=r.started_at, stage_at=r.stage_at)

    def tasks(self) -> list[str]:
        with self._cond:
            return list(self._records)

    def latest_active(self) -> str | None:
        with self._cond:
            for r in reversed(list(self._records.values())):
                if r.state in _ACTIVE:
                    return r.id
            return None

    def wait_state(self, tid: str, state: str, timeout: float = 5.0) -> bool:
        with self._cond:
            return self._cond.wait_for(
                lambda: self._records[tid].state == state, timeout=timeout)


def make_control_handler(manager: TaskManager, speaker=None):
    """Bind the router's `control` dispatches (Fix 1) to the manager/speaker."""

    def handle(dispatch) -> str:
        action = dispatch.argument
        tid = manager.latest_active()
        if action == "pause":
            if speaker is not None:
                speaker.pause()
            if tid and manager.pause(tid):
                return "Pausing after the current step."
            return "Paused. Nothing is running."
        if action in ("resume", "continue"):
            if speaker is not None:
                speaker.resume()
            if tid and manager.resume(tid):
                return "Resuming."
            return "Nothing is paused."
        # stop / cancel / halt
        if speaker is not None:
            speaker.stop()
        if tid and manager.stop(tid):
            return "Stopping at the next safe point; I'll report what finished."
        return "Nothing to stop."

    return handle
