"""Global kill switch — instantly halt all simulated input.

In headless/dev mode this is a simple flag. On a real desktop, bind a global
hotkey (e.g. Ctrl+Alt+Esc) via pynput to set `trigger()` from anywhere.
"""

from __future__ import annotations

import threading


class KillSwitch:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._listener = None

    @property
    def triggered(self) -> bool:
        return self._event.is_set()

    def trigger(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    def bind_hotkey(self, combo: str = "<ctrl>+<alt>+<esc>") -> None:
        """Bind a global hotkey if pynput is available (no-op otherwise)."""
        try:  # pragma: no cover - needs a display + optional dep
            from pynput import keyboard  # type: ignore
            self._listener = keyboard.GlobalHotKeys({combo: self.trigger})
            self._listener.start()
        except Exception:
            self._listener = None
