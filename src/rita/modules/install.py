"""Dev install: write manifests + `current` pointers for the shipped modules.

`rita modules install --dev` points every module's entrypoint at the
installed package via the running interpreter. A packaged install (PyInstaller
/ platform installer) ships version directories the same way — the registry
only ever reads manifests, so both layouts look identical to it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .manifest import Manifest, load_manifest

_MIN_SUPERVISOR = "0.7.0"

# name -> (module path, version, capabilities, max_instances, exclusivity keys)
SHIPPED: dict[str, tuple[str, str, list[str], int, list[str]]] = {
    "voice-in": ("rita.modules_impl.voice_in", "1.0.0",
                 ["listen"], 1, []),
    "voice-out": ("rita.modules_impl.voice_out", "1.0.0",
                  ["speak", "pause", "stop"], 1, []),
    "zephyr-runner": ("rita.modules_impl.zephyr_runner", "1.0.0",
                      ["build", "twister", "flash"], 4, ["serial_port"]),
    "coder-worker": ("rita.modules_impl.coder_worker", "1.0.0",
                      ["complete", "patch", "scaffold"], 4, []),
    "scaffold": ("rita.modules_impl.scaffold", "1.0.0",
                 ["scaffold"], 2, []),
    "cerberus": ("rita.modules_impl.cerberus", "0.2.0",
                 ["analyze"], 1, []),
    "joulescope": ("rita.modules_impl.joulescope", "0.1.0",
                   ["measure"], 1, []),   # one probe, ever
}


def _entrypoint(name: str) -> list[str]:
    """Interpreter-correct module entrypoint: a frozen bundle has no
    `python -m`, so its exe hosts modules directly via `module-run`."""
    if getattr(sys, "frozen", False):  # pragma: no cover - packaged app
        return [sys.executable, "module-run", name]
    return [sys.executable, "-m", "rita", "module-run", name]


def dev_install(root: str | Path | None = None,
                only: list[str] | None = None) -> list[Manifest]:
    if root is None:
        from ..home import modules_dir

        root = modules_dir()
    root = Path(root)
    selected = {n.strip() for n in only} if only else set(SHIPPED)
    unknown = selected - set(SHIPPED)
    if unknown:
        raise ValueError(f"unknown modules: {', '.join(sorted(unknown))}")
    installed: list[Manifest] = []
    for name, (mod, version, caps, max_inst, excl) in SHIPPED.items():
        if name not in selected:
            continue
        d = root / name / version
        d.mkdir(parents=True, exist_ok=True)
        text = (f'name = "{name}"\nversion = "{version}"\n'
                f"entrypoint = {json.dumps(_entrypoint(name))}\n"
                f"capabilities = {json.dumps(caps)}\n"
                f"max_instances = {max_inst}\n"
                f'min_supervisor = "{_MIN_SUPERVISOR}"\n')
        if excl:
            text += f"\n[exclusivity]\nkeys = {json.dumps(excl)}\n"
        (d / "manifest.toml").write_text(text)
        (root / name / "current").write_text(version)
        installed.append(load_manifest(d / "manifest.toml"))
    return installed
