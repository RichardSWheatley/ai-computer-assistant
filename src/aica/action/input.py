"""Simulated mouse/keyboard input, exposed as a plugin's tools.

Headless-safe: pyautogui is imported lazily. Without a display the actions
return a 'simulated' result so the loop still runs and tests pass.
"""

from __future__ import annotations

from ..core.interfaces import ToolResult


class InputController:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._gui = None

    def _backend(self):
        if self._gui is not None:
            return self._gui
        try:  # pragma: no cover - needs a display + optional dep
            import pyautogui  # type: ignore
            pyautogui.FAILSAFE = True  # slam mouse to a corner to abort
            self._gui = pyautogui
        except Exception:
            self._gui = None
        return self._gui

    def click(self, x: int, y: int, button: str = "left") -> ToolResult:
        gui = None if self.dry_run else self._backend()
        if gui is None:
            return ToolResult(ok=True, output=f"[simulated] click {button} @ ({x},{y})")
        gui.click(x=x, y=y, button=button)  # pragma: no cover
        return ToolResult(ok=True, output=f"clicked {button} @ ({x},{y})")

    def type_text(self, text: str) -> ToolResult:
        gui = None if self.dry_run else self._backend()
        if gui is None:
            return ToolResult(ok=True, output=f"[simulated] type {text!r}")
        gui.typewrite(text, interval=0.01)  # pragma: no cover
        return ToolResult(ok=True, output=f"typed {len(text)} chars")

    def hotkey(self, *keys: str) -> ToolResult:
        gui = None if self.dry_run else self._backend()
        if gui is None:
            return ToolResult(ok=True, output=f"[simulated] hotkey {'+'.join(keys)}")
        gui.hotkey(*keys)  # pragma: no cover
        return ToolResult(ok=True, output=f"hotkey {'+'.join(keys)}")
