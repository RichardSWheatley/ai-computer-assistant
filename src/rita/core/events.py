"""A tiny synchronous event bus for decoupled extensibility.

Plugins publish/subscribe without the core knowing about them. Add a future
feature (e.g. an activity logger) by subscribing to an event — zero core edits.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

# Canonical event names.
SCREEN_CHANGED = "screen_changed"
TASK_STARTED = "task_started"
TASK_FINISHED = "task_finished"
ACTION_EXECUTED = "action_executed"
ESCALATION_REQUESTED = "escalation_requested"
ERROR_RAISED = "error_raised"


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable[[Any], None]) -> None:
        self._subs[event].append(handler)

    def publish(self, event: str, payload: Any = None) -> None:
        for handler in list(self._subs.get(event, [])):
            try:
                handler(payload)
            except Exception:  # a misbehaving subscriber must not break the loop
                pass
