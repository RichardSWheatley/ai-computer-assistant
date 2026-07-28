"""Turn triggers — decide *when* a listening turn starts.

Default push-to-talk is the keyboard: press Enter to talk, type 'q' to quit.
A wake-word trigger can implement this same interface later. `FakeTrigger`
drives the loop in tests.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Trigger(Protocol):
    def wait(self) -> bool:  # True = start a turn, False = quit the loop
        ...


class EnterKeyTrigger:
    """Push-to-talk via the keyboard: press Enter to start a turn."""

    def __init__(self, prompt: str = "\n[Press Enter to talk — or type 'q' then Enter to quit] ") -> None:
        self.prompt = prompt

    def wait(self) -> bool:  # pragma: no cover - reads stdin
        try:
            return input(self.prompt).strip().lower() not in {"q", "quit", "exit"}
        except EOFError:
            return False


class FakeTrigger:
    """Yields a preset sequence of decisions, then quits (tests)."""

    def __init__(self, results: list[bool]) -> None:
        self._results = list(results)
        self.calls = 0

    def wait(self) -> bool:
        self.calls += 1
        return self._results.pop(0) if self._results else False
