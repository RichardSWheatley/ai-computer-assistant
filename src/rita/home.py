"""The RITA home directory: per-user config and data under ~/.rita.

Every path the assistant persists (config, boards.json, verification index,
modules, audio, screenshots, sandbox) lives under one root so installs are
relocatable and tests can point `RITA_HOME` at a temp dir. `migrate_legacy_home`
carries over an old ~/.aica directory once, without clobbering anything.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def rita_home() -> Path:
    """The RITA data root: $RITA_HOME if set, else ~/.rita. Created on demand."""
    root = Path(os.environ.get("RITA_HOME") or (Path.home() / ".rita"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def migrate_legacy_home(legacy_root: Path | None = None) -> bool:
    """Copy an old ~/.aica tree (boards.json and all) into the RITA home.

    Only runs when the legacy dir exists; never overwrites files already in the
    new home. Returns True if anything was copied.
    """
    legacy = Path(legacy_root) if legacy_root else Path.home() / ".aica"
    if not legacy.is_dir():
        return False
    new = rita_home()
    copied = False
    for src in legacy.rglob("*"):
        rel = src.relative_to(legacy)
        dst = new / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            continue
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied = True
    return copied


def _sub(name: str) -> Path:
    return rita_home() / name


def boards_json_path() -> Path:
    return _sub("boards.json")


def verification_index_path() -> Path:
    return _sub("verification-index.json")


def config_path() -> Path:
    return _sub("config")


def mcp_config_path() -> Path:
    return _sub("mcp.json")


def modules_dir() -> Path:
    return _sub("modules")


def audio_dir() -> Path:
    return _sub("audio")


def screens_dir() -> Path:
    return _sub("screens")


def sandbox_dir() -> Path:
    return _sub("sandbox")
