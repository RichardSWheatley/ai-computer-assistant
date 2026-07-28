"""Module manifests: name, semver, entrypoint argv, caps, instance rules.

Language-agnostic — the manifest declares the entrypoint (any argv), not
the runtime. Lives at ~/.rita/modules/<name>/<version>/manifest.toml with a
sibling `<name>/current` text file naming the active version.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Manifest:
    name: str
    version: str
    entrypoint: tuple[str, ...]
    capabilities: tuple[str, ...]
    max_instances: int
    min_supervisor: str
    exclusivity_keys: tuple[str, ...]
    path: str


def parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in v.strip().split("."))
    except ValueError as exc:
        raise ManifestError(f"bad semver {v!r}") from exc


def load_manifest(path: str | Path) -> Manifest:
    p = Path(path)
    try:
        data = tomllib.loads(p.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {p}: {exc}") from exc
    for req in ("name", "version", "entrypoint"):
        if req not in data:
            raise ManifestError(f"manifest {p} missing required field {req!r}")
    entrypoint = data["entrypoint"]
    if not isinstance(entrypoint, list) or not entrypoint:
        raise ManifestError(f"manifest {p}: entrypoint must be a non-empty argv list")
    parse_version(str(data["version"]))  # validate early
    excl = ((data.get("exclusivity") or {}).get("keys")) or []
    return Manifest(
        name=str(data["name"]),
        version=str(data["version"]),
        entrypoint=tuple(str(a) for a in entrypoint),
        capabilities=tuple(str(c) for c in data.get("capabilities", [])),
        max_instances=int(data.get("max_instances", 1)),
        min_supervisor=str(data.get("min_supervisor", "0.0.0")),
        exclusivity_keys=tuple(str(k) for k in excl),
        path=str(p),
    )
