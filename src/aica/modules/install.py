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
    "voice-in": ("aica.modules_impl.voice_in", "1.0.0",
                 ["listen"], 1, []),
    "voice-out": ("aica.modules_impl.voice_out", "1.0.0",
                  ["speak", "pause", "stop"], 1, []),
    "zephyr-runner": ("aica.modules_impl.zephyr_runner", "1.0.0",
                      ["build", "twister", "flash"], 4, ["serial_port"]),
    "claude-worker": ("aica.modules_impl.claude_worker", "1.0.0",
                      ["complete", "patch", "scaffold"], 4, []),
    "scaffold": ("aica.modules_impl.scaffold", "1.0.0",
                 ["scaffold"], 2, []),
    "cerberus": ("aica.modules_impl.cerberus", "0.1.0",
                 ["analyze"], 1, []),
    "joulescope": ("aica.modules_impl.joulescope", "0.1.0",
                   ["measure"], 1, []),   # one probe, ever
}


def dev_install(root: str | Path | None = None) -> list[Manifest]:
    if root is None:
        from ..home import modules_dir

        root = modules_dir()
    root = Path(root)
    installed: list[Manifest] = []
    for name, (mod, version, caps, max_inst, excl) in SHIPPED.items():
        d = root / name / version
        d.mkdir(parents=True, exist_ok=True)
        text = (f'name = "{name}"\nversion = "{version}"\n'
                f"entrypoint = {json.dumps([sys.executable, '-m', mod])}\n"
                f"capabilities = {json.dumps(caps)}\n"
                f"max_instances = {max_inst}\n"
                f'min_supervisor = "{_MIN_SUPERVISOR}"\n')
        if excl:
            text += f"\n[exclusivity]\nkeys = {json.dumps(excl)}\n"
        (d / "manifest.toml").write_text(text)
        (root / name / "current").write_text(version)
        installed.append(load_manifest(d / "manifest.toml"))
    return installed
