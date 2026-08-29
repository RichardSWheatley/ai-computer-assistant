"""Single-flight installs: one writer per component, process-wide.

Launch auto-setup, the Modules button, "set yourself up", and the CLI
can all fire the same install; two of them racing a delete-and-replace
window is exactly how the owner's machine produced WinError 5. The
second caller gets an immediate honest refusal and touches nothing.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

_LOCKS: dict[str, threading.Lock] = {}
_REGISTRY_LOCK = threading.Lock()


@contextmanager
def single_flight(name: str):
    """Yields True when this caller holds the install; False when an
    install of `name` is already running somewhere in this process."""
    with _REGISTRY_LOCK:
        lock = _LOCKS.setdefault(name, threading.Lock())
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()


def already_running_detail(name: str) -> str:
    return (f"an install of {name} is already running — watch the "
            f"Modules log; I won't start a second one on top of it")
