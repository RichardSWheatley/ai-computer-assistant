"""Sandbox policy for the native worker and any code-execution path.

The worker runs capture/input (and, in future, code). It must run with the
*least* it needs:

  - a scrubbed environment — no API keys, tokens, or Graph credentials, so
    code running in the worker can't read or exfiltrate a secret even if the
    privileged side is injected (the secret-isolation principle),
  - a constrained working directory,
  - resource limits (CPU / memory / file size) on POSIX,
  - a no-network signal the worker can honor.

`sandboxed_env()` is pure and unit-tested; the rlimit/spawn helpers are
guarded so this module is import-safe everywhere.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# Only these environment variables are passed through to a sandboxed child.
_DEFAULT_ALLOW_ENV = {
    "PATH", "HOME", "TMP", "TMPDIR", "TEMP", "LANG", "LC_ALL", "LC_CTYPE",
    "SystemRoot", "SystemDrive", "windir", "USERPROFILE", "PATHEXT",
    "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "PYTHONPATH",
}

# Even if allow-listed by name, drop anything that looks like a secret.
_SECRET_RE = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|SESSION|COOKIE|AUTH|"
    r"ANTHROPIC|AICA_GRAPH|RITA_GRAPH|AWS_|AZURE_|GCP_|OPENAI)", re.IGNORECASE)


def _default_sandbox_dir() -> str:
    from ..home import sandbox_dir

    return str(sandbox_dir())


@dataclass
class SandboxPolicy:
    allow_env: set[str] = field(default_factory=lambda: set(_DEFAULT_ALLOW_ENV))
    workdir: str = field(default_factory=_default_sandbox_dir)
    cpu_seconds: int = 30
    memory_mb: int = 1024
    file_size_mb: int = 64
    no_network: bool = True

    @classmethod
    def strict(cls) -> "SandboxPolicy":
        return cls(cpu_seconds=10, memory_mb=512, file_size_mb=16)


def sandboxed_env(policy: SandboxPolicy, base: dict | None = None) -> dict:
    """Return a scrubbed environment: allow-listed names, minus anything that
    looks secret. Adds RITA_SANDBOX / RITA_NO_NETWORK markers the worker reads
    (legacy AICA_* names are still set for one release)."""
    base = os.environ if base is None else base
    env = {
        k: v for k, v in base.items()
        if k in policy.allow_env and not _SECRET_RE.search(k)
    }
    env["RITA_SANDBOX"] = env["AICA_SANDBOX"] = "1"
    if policy.no_network:
        env["RITA_NO_NETWORK"] = env["AICA_NO_NETWORK"] = "1"
    return env


def _rlimit_preexec(policy: SandboxPolicy):
    """Build a preexec_fn that applies POSIX resource limits, or None."""
    try:
        import resource  # type: ignore  # POSIX only
    except Exception:  # pragma: no cover - non-POSIX
        return None

    def _apply():  # pragma: no cover - runs in the child process
        mb = 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_CPU,
                               (policy.cpu_seconds, policy.cpu_seconds))
            resource.setrlimit(resource.RLIMIT_AS,
                               (policy.memory_mb * mb, policy.memory_mb * mb))
            resource.setrlimit(resource.RLIMIT_FSIZE,
                               (policy.file_size_mb * mb, policy.file_size_mb * mb))
        except Exception:
            pass

    return _apply


def spawn_kwargs(policy: SandboxPolicy) -> dict:
    """subprocess kwargs that sandbox a child: scrubbed env, cwd, rlimits."""
    os.makedirs(policy.workdir, exist_ok=True)
    kwargs: dict = {"env": sandboxed_env(policy), "cwd": policy.workdir}
    preexec = _rlimit_preexec(policy)
    if preexec is not None:
        kwargs["preexec_fn"] = preexec
    return kwargs
