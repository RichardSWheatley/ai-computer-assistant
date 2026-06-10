"""Discover and load plugins from a folder.

Each plugin lives in `plugins/<name>/` with a `plugin.toml` manifest and a
`plugin.py` exposing `def create() -> Plugin`. Drop a folder in, restart, and
its tools appear in the registry — no core changes (see docs/MODULARITY.md).
"""

from __future__ import annotations

import importlib.util
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..core.interfaces import Plugin


@dataclass
class Manifest:
    name: str
    version: str = "0.0.0"
    permission_tier: str = "read_only"
    scopes: list[str] = field(default_factory=list)
    isolation: str = "in_process"  # "in_process" | "process"
    enabled: bool = True

    @classmethod
    def from_file(cls, path: Path) -> "Manifest":
        data = tomllib.loads(path.read_text())
        p = data.get("plugin", data)
        return cls(
            name=p["name"],
            version=p.get("version", "0.0.0"),
            permission_tier=p.get("permission_tier", "read_only"),
            scopes=p.get("scopes", []),
            isolation=p.get("isolation", "in_process"),
            enabled=p.get("enabled", True),
        )


@dataclass
class LoadedPlugin:
    manifest: Manifest
    instance: Plugin


def discover(plugins_dir: str | Path) -> list[LoadedPlugin]:
    root = Path(plugins_dir)
    loaded: list[LoadedPlugin] = []
    if not root.is_dir():
        return loaded

    for entry in sorted(root.iterdir()):
        manifest_path = entry / "plugin.toml"
        module_path = entry / "plugin.py"
        if not (manifest_path.exists() and module_path.exists()):
            continue
        manifest = Manifest.from_file(manifest_path)
        if not manifest.enabled:
            continue
        instance = _load_module(manifest.name, module_path)
        if instance is not None:
            loaded.append(LoadedPlugin(manifest=manifest, instance=instance))
    return loaded


def _load_module(name: str, path: Path) -> Plugin | None:
    spec = importlib.util.spec_from_file_location(f"aica_plugin_{name}", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "create", None)
    return factory() if callable(factory) else None
