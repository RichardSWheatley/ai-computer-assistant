"""Platform-aware backend selection — first pass targets Windows + macOS.

Perception (a11y tree) and low-level input differ per OS:

  Windows : UI Automation (pywinauto/uiautomation) + pyautogui
  macOS   : Accessibility API (AXUIElement via pyobjc) + Quartz/pyautogui
  Linux   : best-effort (AT-SPI) — not a first-pass target

This module centralizes the choice so the rest of the code stays OS-agnostic.
"""

from __future__ import annotations

import platform

WINDOWS = "Windows"
MACOS = "Darwin"
LINUX = "Linux"

# First-pass supported desktops.
SUPPORTED = {WINDOWS, MACOS}


def current_os() -> str:
    return platform.system()


def is_supported() -> bool:
    return current_os() in SUPPORTED


def a11y_backend() -> str:
    """Name of the accessibility backend to use on this OS."""
    return {
        WINDOWS: "uiautomation",      # Windows UI Automation
        MACOS: "ax_accessibility",    # macOS AXUIElement
    }.get(current_os(), "none")


def input_backend() -> str:
    """Name of the simulated-input backend to use on this OS."""
    return {
        WINDOWS: "pyautogui+pydirectinput",
        MACOS: "pyautogui+quartz",
    }.get(current_os(), "pyautogui")


def notes() -> str:
    os_name = current_os()
    if os_name == WINDOWS:
        return ("Windows: grant the app input permissions; UI Automation works "
                "out of the box. NVIDIA GPU -> CUDA acceleration.")
    if os_name == MACOS:
        return ("macOS: grant Accessibility + Screen Recording permissions in "
                "System Settings > Privacy. Apple Silicon -> Metal acceleration.")
    return "Linux is not a first-pass target; perception/input are best-effort."
