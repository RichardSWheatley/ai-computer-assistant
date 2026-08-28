"""coder-worker module: the coding agent behind RPC (one per task)."""

from __future__ import annotations

from pathlib import Path

from ..modules.runtime import serve

_STATE: dict = {}


def _cli():
    from ..firmware.coder import CoderCli
    from ..firmware.static_check import split_command

    if "cli" not in _STATE:
        command = _STATE.get("command")
        if not command:
            from ..config import load_rita_config

            command = load_rita_config().coder_command
        if not command:
            raise RuntimeError("no coding agent configured "
                               "(set coder_command in the RITA config)")
        _STATE["cli"] = CoderCli(_STATE.get("workspace", "."),
                                 tuple(split_command(command)),
                                 mcp_config=_STATE.get("mcp_config"))
    return _STATE["cli"]


def start(params, emit):
    _STATE.update(workspace=params.get("workspace", "."),
                  mcp_config=params.get("mcp_config"),
                  command=params.get("command"))
    _STATE.pop("cli", None)
    return {"ok": True}


def complete(params, emit):  # pragma: no cover - needs the coding-agent CLI
    return {"text": _cli().complete(params["prompt"])}


def patch(params, emit):  # pragma: no cover - needs the coding-agent CLI
    from ..firmware.twister_results import FailureArtifact

    failure = FailureArtifact(**params["failure"])
    res = _cli().patch(failure, Path(params["workdir"]))
    return {"ok": res.ok, "detail": res.detail}


def scaffold(params, emit):  # pragma: no cover - needs the coding-agent CLI
    res = _cli().scaffold(params["goal"], params["board"], Path(params["dest"]))
    return {"ok": res.ok, "app_dir": res.app_dir, "detail": res.detail}


def status(params, emit):
    return {"workspace": _STATE.get("workspace")}


if __name__ == "__main__":  # pragma: no cover - exercised as a child process
    serve(name="coder-worker", version="1.0.0",
          handlers={"start": start, "status": status, "complete": complete,
                    "patch": patch, "scaffold": scaffold})
