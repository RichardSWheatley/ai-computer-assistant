"""Simulated mouse/keyboard input, exposed as plugin tools.

Headless-safe: pyautogui is imported lazily. Without a display (or in dry-run)
the actions return a '[simulated]' result so the loop still runs and tests pass.
On a real desktop they drive the mouse/keyboard for real.
"""

from __future__ import annotations

from ..core.interfaces import ToolResult


class InputController:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._gui = None

    def _backend(self):
        if self.dry_run:
            return None
        if self._gui is not None:
            return self._gui
        try:  # pragma: no cover - needs a display + optional dep
            import pyautogui  # type: ignore
            pyautogui.FAILSAFE = True   # slam mouse to a corner to abort
            pyautogui.PAUSE = 0.02
            self._gui = pyautogui
        except Exception:
            self._gui = None
        return self._gui

    # -- helpers ------------------------------------------------------------
    def _do(self, sim: str, real):
        """Run `real(gui)` on a live backend, else return the simulated result."""
        gui = self._backend()
        if gui is None:
            return ToolResult(ok=True, output=f"[simulated] {sim}")
        real(gui)  # pragma: no cover - needs a display
        return ToolResult(ok=True, output=sim)  # pragma: no cover

    # -- mouse --------------------------------------------------------------
    def click(self, x: int, y: int, button: str = "left") -> ToolResult:
        return self._do(f"click {button} @ ({x},{y})",
                        lambda g: g.click(x=x, y=y, button=button))

    def double_click(self, x: int, y: int) -> ToolResult:
        return self._do(f"double-click @ ({x},{y})",
                        lambda g: g.doubleClick(x=x, y=y))

    def right_click(self, x: int, y: int) -> ToolResult:
        return self._do(f"right-click @ ({x},{y})",
                        lambda g: g.click(x=x, y=y, button="right"))

    def move(self, x: int, y: int) -> ToolResult:
        return self._do(f"move -> ({x},{y})", lambda g: g.moveTo(x, y))

    def scroll(self, amount: int) -> ToolResult:
        return self._do(f"scroll {amount}", lambda g: g.scroll(amount))

    # -- keyboard -----------------------------------------------------------
    def type_text(self, text: str) -> ToolResult:
        return self._do(f"type {text!r} ({len(text)} chars)",
                        lambda g: g.typewrite(text, interval=0.01))

    def press(self, key: str) -> ToolResult:
        return self._do(f"press {key}", lambda g: g.press(key))

    def hotkey(self, *keys: str) -> ToolResult:
        combo = "+".join(keys)
        return self._do(f"hotkey {combo}", lambda g: g.hotkey(*keys))
