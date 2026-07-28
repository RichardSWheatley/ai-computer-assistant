"""zephyr-runner module: west build / twister behind RPC (one per board port)."""

from __future__ import annotations

from pathlib import Path

from ..modules.runtime import serve

_STATE: dict = {}


def _cli():
    from ..firmware.west import WestCli

    if "cli" not in _STATE:
        _STATE["cli"] = WestCli(_STATE.get("workspace", "."))
    return _STATE["cli"]


def start(params, emit):
    _STATE["workspace"] = params.get("workspace", ".")
    _STATE.pop("cli", None)
    return {"ok": True}


def build(params, emit):  # pragma: no cover - needs a toolchain
    res = _cli().build(Path(params["app_dir"]), params["platform"],
                       Path(params["outdir"]))
    emit("progress", {"stage": "build", "ok": res.ok})
    return {"ok": res.ok,
            "failure": res.failure.describe() if res.failure else None}


def twister(params, emit):  # pragma: no cover - needs a toolchain
    res = _cli().twister(
        testsuite=Path(params["testsuite"]), platform=params["platform"],
        outdir=Path(params["outdir"]), device=bool(params.get("device")),
        hardware_map=Path(params["hardware_map"]) if params.get("hardware_map") else None)
    return {"ok": res.ok, "twister_json": res.path,
            "failures": [f.describe() for f in res.failures]}


def generate_hardware_map(params, emit):  # pragma: no cover - needs hardware
    return {"path": str(_cli().generate_hardware_map(Path(params["out"])))}


def status(params, emit):
    return {"workspace": _STATE.get("workspace")}


if __name__ == "__main__":  # pragma: no cover - exercised as a child process
    serve(name="zephyr-runner", version="1.0.0",
          handlers={"start": start, "status": status, "build": build,
                    "twister": twister,
                    "generate_hardware_map": generate_hardware_map})
