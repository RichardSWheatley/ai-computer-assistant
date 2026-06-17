"""Application wiring — assemble the assistant from parts.

Keeps construction in one place so the CLI (and future GUI) stay thin. Chooses
real vs mock perception based on availability, registers built-in + discovered
plugins, and builds the routed planner.
"""

from __future__ import annotations

from . import platform_support
from .action.desktop import DesktopController
from .action.input import InputController
from .action.killswitch import KillSwitch
from .config import Config
from .core.events import EventBus
from .core.orchestrator import Orchestrator
from .core.registry import ToolRegistry
from .llm.router import build_default_planner
from .perception.desktop import DesktopPerception
from .perception.mock import MockPerception
from .plugins.computer_use import ComputerUsePlugin
from .plugins.loader import discover
from .security.audit import AuditLog
from .security.policy import SecurityPolicy
from .security.quarantine import Quarantine


def build_assistant(config: Config, *, headless: bool = True,
                    confirm=None, planner=None) -> Orchestrator:
    bus = EventBus()
    registry = ToolRegistry()

    # Eyes + hands. Three cases:
    #   1. native worker process (polyglot boundary),
    #   2. a real desktop (Windows/Mac): DesktopPerception + live input,
    #   3. headless/dev: mock perception + simulated input.
    # The orchestrator can't tell which is in play.
    locator = None
    if config.use_native_worker:
        from .workers.client import WorkerClient
        from .workers.proxy import WorkerInputController, WorkerPerception
        worker_client = WorkerClient(config.worker_command).start()
        input_controller = WorkerInputController(worker_client)
        desktop = DesktopController(dry_run=config.dry_run)
        perception = WorkerPerception(worker_client)
    else:
        input_controller = InputController(dry_run=config.dry_run)
        desktop = DesktopController(dry_run=config.dry_run)
        if not headless and platform_support.is_supported():
            dp = DesktopPerception()
            perception = dp
            locator = dp.locate            # element-targeted clicks
        else:
            perception = MockPerception()  # headless/dev

    # Built-in computer-use plugin (the 'hands' + reach).
    registry.register_plugin(ComputerUsePlugin(input_controller, desktop, locator))

    # Discovered drop-in plugins.
    for lp in discover(config.plugins_dir):
        try:
            registry.register_plugin(lp.instance)
        except ValueError:
            pass  # duplicate tool name -> skip, keep loading the rest

    # Secure by default. The orchestrator gates actions via this policy: local
    # actions run unattended, but outward-facing / destructive ones (send mail,
    # post, delete) require a human `confirm` — and with none wired, are blocked.
    # Provenance binding: suspicious untrusted content escalates even local writes.
    policy = (SecurityPolicy.local_only() if config.mode == "local-only"
              else SecurityPolicy())

    # Quarantine: the planner only ever sees sanitized, typed observations.
    quarantine = Quarantine()

    # Tamper-evident audit log, fed by the event bus.
    audit = AuditLog(path=config.audit_path).attach(bus)

    planner = planner or build_default_planner(config)
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
        policy=policy,
        quarantine=quarantine,
        audit=audit,
    )
