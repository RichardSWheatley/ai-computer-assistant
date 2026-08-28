"""scaffold module: application authoring behind RPC (wraps the coder seam)."""

from __future__ import annotations

from pathlib import Path

from ..modules.runtime import serve

_STATE: dict = {}


def start(params, emit):
    _STATE["workspace"] = params.get("workspace", ".")
    return {"ok": True}


def scaffold(params, emit):  # pragma: no cover - needs the coding-agent CLI
    from ..firmware.coder import CoderCli

    cli = CoderCli(_STATE.get("workspace", "."),
                          mcp_config=params.get("mcp_config"))
    res = cli.scaffold(params["goal"], params["board"], Path(params["dest"]))
    return {"ok": res.ok, "app_dir": res.app_dir, "detail": res.detail}


def status(params, emit):
    return {"workspace": _STATE.get("workspace")}


if __name__ == "__main__":  # pragma: no cover - exercised as a child process
    serve(name="scaffold", version="1.0.0",
          handlers={"start": start, "status": status, "scaffold": scaffold})
