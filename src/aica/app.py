"""Application wiring — assemble the assistant from parts.

Keeps construction in one place so the CLI (and future GUI) stay thin. Chooses
real vs mock perception based on availability, registers built-in + discovered
plugins, and builds the routed planner.
"""

from __future__ import annotations

from .action.input import InputController
from .action.killswitch import KillSwitch
from .config import Config
from .core.events import EventBus
from .core.orchestrator import Orchestrator
from .core.registry import ToolRegistry
from .llm.router import build_default_planner
from .perception.mock import MockPerception
from .plugins.computer_use import ComputerUsePlugin
from .plugins.loader import discover


def build_assistant(config: Config, *, headless: bool = True,
                    confirm=None) -> Orchestrator:
    bus = EventBus()
    registry = ToolRegistry()

    # Built-in computer-use plugin (the 'hands').
    registry.register_plugin(
        ComputerUsePlugin(InputController(dry_run=config.dry_run)))

    # Discovered drop-in plugins.
    for lp in discover(config.plugins_dir):
        try:
            registry.register_plugin(lp.instance)
        except ValueError:
            pass  # duplicate tool name -> skip, keep loading the rest

    perception = MockPerception()  # swap to DesktopPerception on a real desktop

    planner = build_default_planner(config)
    kill = KillSwitch()
    if not headless:
        kill.bind_hotkey()

    return Orchestrator(
        perception=perception,
        planner=planner,
        registry=registry,
        bus=bus,
        kill_switch=kill,
        confirm=confirm,
        max_steps=config.max_steps,
    )
