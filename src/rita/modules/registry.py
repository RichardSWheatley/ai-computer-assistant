"""Module registry: discovery, `current` pointers, instance caps, claims.

Updates: drop a new version dir, flip `current` — running instances drain
on the version they started with; new spawns read `current` fresh.
Rollback = flip back. Exclusive resource claims (e.g. one runner per board
serial port) are enforced across live instances.
"""

from __future__ import annotations

import threading
from pathlib import Path

from .handle import ModuleError, ModuleHandle
from .manifest import Manifest, load_manifest, parse_version


class ModuleBusy(ModuleError):
    pass


class ModuleCompatError(ModuleError):
    pass


def _supervisor_version_default() -> str:
    from importlib.metadata import version

    for dist in ("rita", "aica"):   # legacy dist name during the transition
        try:
            return version(dist)
        except Exception:
            continue
    return "0.0.0"  # pragma: no cover - not installed


class ModuleRegistry:
    def __init__(self, root: str | Path | None = None,
                 supervisor_version: str | None = None) -> None:
        if root is None:
            from ..home import modules_dir

            root = modules_dir()
        self.root = Path(root)
        self.supervisor_version = supervisor_version or _supervisor_version_default()
        self._lock = threading.Lock()
        self._instances: list[ModuleHandle] = []

    # --- discovery ----------------------------------------------------------

    def discover(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        if not self.root.is_dir():
            return out
        for mod_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            versions = sorted(
                (v.name for v in mod_dir.iterdir()
                 if v.is_dir() and (v / "manifest.toml").exists()),
                key=parse_version)
            if versions:
                out[mod_dir.name] = versions
        return out

    def current(self, name: str) -> str:
        pointer = self.root / name / "current"
        if pointer.exists():
            return pointer.read_text().strip()
        versions = self.discover().get(name, [])
        if not versions:
            raise ModuleError(f"module {name!r} is not installed")
        return versions[-1]

    def set_current(self, name: str, version: str) -> None:
        (self.root / name / "current").write_text(version)

    def manifest(self, name: str) -> Manifest:
        version = self.current(name)
        return load_manifest(self.root / name / version / "manifest.toml")

    # --- launching ----------------------------------------------------------

    def _live(self, name: str) -> list[ModuleHandle]:
        self._instances = [h for h in self._instances if h.alive]
        return [h for h in self._instances if h.manifest.name == name]

    def launch(self, name: str, claims: dict[str, str] | None = None,
               handshake_timeout: float = 5.0,
               spawn_kwargs: dict | None = None) -> ModuleHandle:
        manifest = self.manifest(name)
        if parse_version(manifest.min_supervisor) > parse_version(self.supervisor_version):
            raise ModuleCompatError(
                f"{name} {manifest.version} needs supervisor >= "
                f"{manifest.min_supervisor}; this is {self.supervisor_version}")
        claims = dict(claims or {})
        with self._lock:
            live = self._live(name)
            if len(live) >= manifest.max_instances:
                raise ModuleBusy(
                    f"{name}: {len(live)}/{manifest.max_instances} instances busy")
            for key in manifest.exclusivity_keys:
                if key not in claims:
                    raise ModuleBusy(
                        f"{name} requires an exclusive claim for {key!r}")
                taken = {h.claims.get(key) for h in self._instances if h.alive}
                if claims[key] in taken:
                    raise ModuleBusy(
                        f"{name}: {key}={claims[key]!r} is already claimed")
        handle = ModuleHandle.spawn(manifest,
                                    supervisor_version=self.supervisor_version,
                                    handshake_timeout=handshake_timeout,
                                    spawn_kwargs=spawn_kwargs)
        handle.claims = claims
        with self._lock:
            self._instances.append(handle)
        return handle

    def drain(self, name: str) -> list[ModuleHandle]:
        """Live instances still on an older version than `current` — they
        keep running (they drain); new launches use the new version."""
        cur = self.current(name)
        return [h for h in self._live(name) if h.manifest.version != cur]

    def shutdown_all(self) -> None:
        with self._lock:
            handles, self._instances = self._instances, []
        for h in handles:
            if h.alive:
                h.shutdown()
