"""Built-in computer-use plugin: the assistant's hands (and a bit of reach).

Wraps the input + desktop controllers and (optionally) a locator so the planner
can drive the mouse/keyboard, launch apps, manage the clipboard, and click UI
elements by label (resolved via the accessibility tree) rather than guessing
coordinates.

All tools are local_write tier (gated by a confirmation callback when wired).
"""

from __future__ import annotations

from typing import Callable

from ..action.desktop import DesktopController
from ..action.input import InputController
from ..core.interfaces import Plugin, ToolResult, ToolSchema

# locator: label -> (x, y) | None  (backed by perception's accessibility tree)
Locator = Callable[[str], "tuple[int, int] | None"]


class ComputerUsePlugin(Plugin):
    name = "computer_use"

    def __init__(self, controller: InputController | None = None,
                 desktop: DesktopController | None = None,
                 locator: Locator | None = None) -> None:
        self.input = controller or InputController(dry_run=True)
        self.desktop = desktop or DesktopController(dry_run=True)
        self.locator = locator

    def describe(self) -> list[ToolSchema]:
        w = "local_write"
        return [
            ToolSchema("click", "Click the mouse at screen coordinates (x, y).",
                       {"x": "int", "y": "int", "button": "str=left"}, w),
            ToolSchema("double_click", "Double-click at (x, y).",
                       {"x": "int", "y": "int"}, w),
            ToolSchema("right_click", "Right-click at (x, y).",
                       {"x": "int", "y": "int"}, w),
            ToolSchema("click_label",
                       "Click a UI element by its visible label/name (resolved "
                       "via the accessibility tree). Prefer this over raw "
                       "coordinates when the element is listed.",
                       {"label": "str"}, w),
            ToolSchema("move", "Move the mouse to (x, y).", {"x": "int", "y": "int"}, w),
            ToolSchema("scroll", "Scroll vertically by amount (negative = down).",
                       {"amount": "int"}, w),
            ToolSchema("type_text", "Type a string via the keyboard.", {"text": "str"}, w),
            ToolSchema("press", "Press a single key, e.g. enter, tab, esc.", {"key": "str"}, w),
            ToolSchema("hotkey", "Press a key combination, e.g. ctrl+c.", {"keys": "list[str]"}, w),
            ToolSchema("open_app", "Launch an application by name.", {"name": "str"}, w),
            ToolSchema("focus_window", "Bring a window to the front by title.",
                       {"title": "str"}, w),
            ToolSchema("clipboard_set", "Put text on the system clipboard.", {"text": "str"}, w),
            ToolSchema("clipboard_get", "Read the system clipboard.", {}, "read_only"),
        ]

    def invoke(self, tool: str, args: dict) -> ToolResult:
        a = args
        if tool == "click":
            return self.input.click(int(a.get("x", 0)), int(a.get("y", 0)),
                                    a.get("button", "left"))
        if tool == "double_click":
            return self.input.double_click(int(a.get("x", 0)), int(a.get("y", 0)))
        if tool == "right_click":
            return self.input.right_click(int(a.get("x", 0)), int(a.get("y", 0)))
        if tool == "click_label":
            label = str(a.get("label", ""))
            if self.locator is None:
                return ToolResult(ok=False, error="no locator available (headless)")
            coords = self.locator(label)
            if coords is None:
                return ToolResult(ok=False, error=f"element not found: {label!r}")
            return self.input.click(coords[0], coords[1])
        if tool == "move":
            return self.input.move(int(a.get("x", 0)), int(a.get("y", 0)))
        if tool == "scroll":
            return self.input.scroll(int(a.get("amount", 0)))
        if tool == "type_text":
            return self.input.type_text(str(a.get("text", a.get("goal", ""))))
        if tool == "press":
            return self.input.press(str(a.get("key", "")))
        if tool == "hotkey":
            return self.input.hotkey(*(a.get("keys") or []))
        if tool == "open_app":
            return self.desktop.open_app(str(a.get("name", "")))
        if tool == "focus_window":
            return self.desktop.focus_window(str(a.get("title", "")))
        if tool == "clipboard_set":
            return self.desktop.clipboard_set(str(a.get("text", "")))
        if tool == "clipboard_get":
            return self.desktop.clipboard_get()
        return ToolResult(ok=False, error=f"unknown tool {tool}")


def create() -> Plugin:
    return ComputerUsePlugin()
