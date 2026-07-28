"""cerberus module: the static-check gate behind RPC.

`start {"command": "..."}` configures the CERBERUS invocation (falls back
to RitaConfig.cerberus_command); `check {"target": "..."}` runs the gate
and returns findings. Without a configured command it answers honestly
that CERBERUS is not wired up — never a fake pass.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..modules.runtime import serve

_STATE: dict = {}

_NOT_CONFIGURED = {"ok": False,
                   "error": "CERBERUS is not configured on this machine; "
                            "set its command in RITA's settings"}


def start(params, emit):
    command = params.get("command")
    if not command:
        from ..config import load_rita_config

        command = load_rita_config().cerberus_command
    if not command:
        return dict(_NOT_CONFIGURED)
    _STATE["command"] = command
    return {"ok": True, "command": command}


def check(params, emit):
    if "command" not in _STATE:
        return dict(_NOT_CONFIGURED)
    from ..firmware.static_check import CerberusCli

    result = CerberusCli(_STATE["command"]).check(Path(params["target"]))
    emit("progress", {"stage": "static", "ok": result.ok})
    return {"ok": result.ok,
            "findings": [asdict(f) for f in result.findings]}


def status(params, emit):
    if "command" not in _STATE:
        return dict(_NOT_CONFIGURED)
    return {"ok": True, "command": _STATE["command"]}


if __name__ == "__main__":  # pragma: no cover - exercised as a child process
    serve(name="cerberus", version="0.2.0",
          handlers={"start": start, "status": status, "check": check})
