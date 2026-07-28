"""OS-level desktop actions: launch apps, focus windows, clipboard.

Platform-aware (Windows + macOS first pass) and dependency-light. Everything is
guarded and lazily imported so this module loads on headless Linux and in
dry-run, returning '[simulated]' results that keep the loop and tests running.
"""

from __future__ import annotations

import shutil
import subprocess

from .. import platform_support
from ..core.interfaces import ToolResult


class DesktopController:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    # -- launch apps --------------------------------------------------------
    def open_app(self, name: str) -> ToolResult:
        os_name = platform_support.current_os()
        if self.dry_run:
            return ToolResult(ok=True, output=f"[simulated] open app {name!r}")
        try:  # pragma: no cover - OS-specific, needs a desktop
            if os_name == platform_support.MACOS:
                subprocess.Popen(["open", "-a", name])
            elif os_name == platform_support.WINDOWS:
                subprocess.Popen(["cmd", "/c", "start", "", name], shell=False)
            else:
                if not shutil.which(name):
                    return ToolResult(ok=False, error=f"app not found: {name}")
                subprocess.Popen([name])
            return ToolResult(ok=True, output=f"launched {name}")
        except Exception as exc:  # pragma: no cover
            return ToolResult(ok=False, error=f"open_app failed: {exc}")

    # -- focus a window by title -------------------------------------------
    def focus_window(self, title: str) -> ToolResult:
        if self.dry_run:
            return ToolResult(ok=True, output=f"[simulated] focus window {title!r}")
        try:  # pragma: no cover - needs a desktop
            import pygetwindow as gw  # type: ignore
            wins = gw.getWindowsWithTitle(title)
            if not wins:
                return ToolResult(ok=False, error=f"no window titled {title!r}")
            wins[0].activate()
            return ToolResult(ok=True, output=f"focused {title!r}")
        except Exception as exc:  # pragma: no cover
            return ToolResult(ok=False, error=f"focus_window failed: {exc}")

    # -- clipboard ----------------------------------------------------------
    def clipboard_set(self, text: str) -> ToolResult:
        if self.dry_run:
            return ToolResult(ok=True, output=f"[simulated] clipboard <- {len(text)} chars")
        try:  # pragma: no cover - needs a desktop
            import pyperclip  # type: ignore
            pyperclip.copy(text)
            return ToolResult(ok=True, output=f"clipboard set ({len(text)} chars)")
        except Exception as exc:  # pragma: no cover
            return ToolResult(ok=False, error=f"clipboard_set failed: {exc}")

    def clipboard_get(self) -> ToolResult:
        if self.dry_run:
            return ToolResult(ok=True, output="[simulated] clipboard contents")
        try:  # pragma: no cover - needs a desktop
            import pyperclip  # type: ignore
            return ToolResult(ok=True, output=pyperclip.paste())
        except Exception as exc:  # pragma: no cover
            return ToolResult(ok=False, error=f"clipboard_get failed: {exc}")
