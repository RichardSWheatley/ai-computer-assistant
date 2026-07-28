"""CERBERUS acquisition: the repo is a needed install part of RITA.

github.com/RichardSWheatley/cerberus (G.U.A.R.D.) is cloned into
~/.rita/cerberus by the installer's component, the GUI button, or
`rita cerberus install`. Head 1 (`scan`, 94 deterministic MISRA/CERT
checks) needs no API key — RITA's default gate. Deep mode (`analyze`,
Oracle LLM + Unity tests — Claude's seat inside CERBERUS) is opt-in and
reads its own env (CERBERUS_LLM_*/ANTHROPIC_API_KEY), passed through.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .static_check import CerberusCli

CERBERUS_REPO_URL = "https://github.com/RichardSWheatley/cerberus"


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    path: str
    detail: str


def _default_dest() -> Path:
    from ..home import cerberus_dir

    return cerberus_dir()


def detect_cerberus(dest: str | Path | None = None) -> Path | None:
    """The clone, iff it actually carries the CLI — never guessed."""
    d = Path(dest) if dest else _default_dest()
    return d if (d / "cerberus" / "cli.py").is_file() else None


def install_cerberus(dest: str | Path | None = None,
                     url: str = CERBERUS_REPO_URL,
                     git: str = "git",
                     timeout: float = 300.0) -> InstallResult:
    """Clone (or update) the CERBERUS repo. Honest failures, never fake."""
    d = Path(dest) if dest else _default_dest()
    try:
        if (d / ".git").is_dir():
            proc = subprocess.run([git, "-C", str(d), "pull", "--ff-only"],
                                  capture_output=True, text=True,
                                  timeout=timeout)
            action = "updated (git pull)"
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run([git, "clone", "--depth", "1", url, str(d)],
                                  capture_output=True, text=True,
                                  timeout=timeout)
            action = "cloned"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return InstallResult(ok=False, path=str(d),
                             detail=f"git unavailable or failed: {exc}")
    if proc.returncode != 0:
        return InstallResult(ok=False, path=str(d),
                             detail=(proc.stderr or proc.stdout or
                                     f"git exited {proc.returncode}")[-500:])
    if detect_cerberus(d) is None:
        return InstallResult(ok=False, path=str(d),
                             detail="clone succeeded but cerberus/cli.py is "
                                    "missing — wrong repo?")
    return InstallResult(ok=True, path=str(d), detail=f"CERBERUS {action} at {d}")


def default_checker(clone: str | Path, *, deep: bool = False,
                    unity_dir: str | Path | None = None) -> CerberusCli:
    """The pinned invocation, run from the clone (it isn't pip-installed):
    scan = Head 1, deterministic and keyless (RITA's default gate);
    analyze = all three heads (opt-in)."""
    clone = Path(clone)
    if deep:
        unity = Path(unity_dir) if unity_dir else clone / "unity"
        argv = [sys.executable, "-m", "cerberus.cli", "analyze",
                "--unity-dir", str(unity)]
    else:
        argv = [sys.executable, "-m", "cerberus.cli", "scan"]
    return CerberusCli(argv, cwd=str(clone))
