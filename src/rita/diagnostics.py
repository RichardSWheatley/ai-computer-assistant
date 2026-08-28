"""Self-checks: RITA reports her own setup from inside the app.

RITA is GUI-only — the user has no terminal to debug with. Every external
piece she drives is checked here and reported with the CONCRETE finding
(path, exit code, the tool's own output), never a guess and never a shrug.
`deep=True` additionally runs the coding agent for real on a trivial
prompt, because "configured" and "working" are different claims.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import RitaConfig

_SMOKE_TIMEOUT = 90.0

# Auth is the most common live-agent failure and its fix is specific.
_AUTH_HINTS = ("authenticate", "oauth", "unauthorized", "login", "api key",
               "session expired")


def _is_windows() -> bool:
    import os

    return os.name == "nt"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _tail(text: str, n: int = 400) -> str:
    return (text or "").strip()[-n:]


def _workspace(cfg: RitaConfig) -> Check:
    if not cfg.workspace:
        return Check("workspace", False,
                     "No Zephyr workspace set — pick one on the Workspace "
                     "page and press Sync.")
    p = Path(cfg.workspace)
    if not (p / "zephyr").is_dir():
        return Check("workspace", False,
                     f"{p} has no zephyr/ inside it — choose the folder that "
                     f"contains zephyr/, then Sync.")
    return Check("workspace", True, f"{p} (zephyr/ present)")


def _coder(cfg: RitaConfig) -> Check:
    if not cfg.coder_command:
        return Check("coding agent", False,
                     "Not configured — set the command on the Settings page.")
    from .firmware.static_check import resolve_argv, split_command

    argv = split_command(cfg.coder_command)
    try:
        resolved = resolve_argv(argv)
    except FileNotFoundError as exc:
        return Check("coding agent", False, str(exc))
    return Check("coding agent", True,
                 f"{cfg.coder_command!r} -> {resolved[0]}")


def _coder_live(cfg: RitaConfig) -> Check:
    """Actually run the agent. Configured != working."""
    name = "coding agent (live)"
    if not cfg.coder_command:
        return Check(name, False, "Not configured — nothing to run.")
    from .firmware.static_check import resolve_argv, split_command

    try:
        argv = resolve_argv(split_command(cfg.coder_command))
    except FileNotFoundError as exc:
        return Check(name, False, str(exc))
    args = [*argv, "Reply with the single word: ok", "--output-format", "text"]
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              cwd=cfg.workspace or None, timeout=_SMOKE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return Check(name, False,
                     f"no reply within {_SMOKE_TIMEOUT:.0f}s — is the agent "
                     f"waiting for a login or a prompt?")
    except OSError as exc:
        return Check(name, False, f"could not start: {exc}")
    out, err = _tail(proc.stdout), _tail(proc.stderr)
    if proc.returncode != 0 or not out:
        blob = f"{out} {err}".lower()
        hint = ""
        if any(h in blob for h in _AUTH_HINTS):
            hint = (" — the agent isn't logged in: run it once yourself in a "
                    "terminal and complete its login, then try again. RITA "
                    "can't do the login for you.")
        return Check(name, False,
                     f"exit {proc.returncode}. stdout: {out or '(empty)'} | "
                     f"stderr: {err or '(empty)'}{hint}")
    return Check(name, True, f"replied: {out[:120]}")


def _mcp(cfg: RitaConfig) -> Check:
    """The workspace MCP server: config present AND the command runs."""
    import json

    from .home import mcp_config_path

    p = mcp_config_path()
    if not p.exists():
        return Check("workspace MCP", False,
                     "Not wired yet — press Sync on the Workspace page. "
                     "(RITA still codes without it.)")
    try:
        server = json.loads(p.read_text())["mcpServers"]["rita-workspace"]
        command, args = server["command"], server.get("args", [])
    except Exception as exc:
        return Check("workspace MCP", False, f"{p} is unreadable: {exc}")
    if not (Path(command).exists() or command in ("python", "python3")):
        return Check("workspace MCP", False,
                     f"{command} does not exist — press Sync to rewrite "
                     f"{p.name} for this install.")
    # Stale config from an older build: the GUI exe can't run `-m rita`,
    # and a relative workspace breaks when the agent launches the server
    # from its own directory. Both look fine on a file-exists check alone.
    stale = ("-m" in args
             or Path(command).name.lower().startswith("ritaapp")
             or not any(Path(a).is_absolute() for a in args[-1:]))
    if stale:
        return Check("workspace MCP", False,
                     f"{p.name} was written by an older version "
                     f"({command} {' '.join(args[:3])}…) and cannot start — "
                     f"press Sync on the Workspace page to rewrite it.")
    from .mcpserver.server import mcp_available

    if not mcp_available():
        return Check("workspace MCP", False,
                     "the 'mcp' package isn't available to this build, so "
                     "the server can't start. RITA codes without workspace "
                     "tools; reinstall with the Workspace MCP component.")
    return Check("workspace MCP", True, f"{command} {' '.join(args[:2])}")


def _voice() -> Check:
    missing = []
    for mod in ("sounddevice", "faster_whisper"):
        try:                       # a REAL import: a spec probe misses
            __import__(mod)        # missing DLLs in a frozen bundle
        except Exception as exc:
            missing.append(f"{mod} ({type(exc).__name__}: {exc})")
    if missing:
        return Check("voice", False,
                     "not usable: " + "; ".join(missing)
                     + " — reinstall with the Voice component.")
    return Check("voice", True,
                 "sounddevice + faster-whisper import cleanly "
                 "(the speech model downloads on the first spoken turn).")


def _west(cfg: RitaConfig) -> Check:
    import shutil

    found = shutil.which("west")
    if not found:
        return Check("west", False,
                     "not on PATH — builds and twister runs need it "
                     "(install it in the same environment as your workspace).")
    return Check("west", True, found)


def _sdk() -> Check:
    from .firmware.workspace import read_sdk_info

    sdk = read_sdk_info()
    if not sdk:
        return Check("Zephyr SDK", False,
                     "not found — set ZEPHYR_SDK_INSTALL_DIR or install it "
                     "in a standard location.")
    return Check("Zephyr SDK", True, f"{sdk['version']} at {sdk['path']}")


def _cerberus() -> Check:
    from .firmware.cerberus_setup import detect_cerberus

    clone = detect_cerberus()
    if clone is None:
        return Check("CERBERUS", False,
                     "not installed — the static gate reports itself skipped. "
                     "Install it from the Modules page.")
    return Check("CERBERUS", True, str(clone))


def _arm_toolchain(cfg: RitaConfig) -> Check:
    """Zephyr's compiler family — the one the unit tier compiles with.
    The version must MATCH the Zephyr SDK's gcc (the owner's rule)."""
    from .firmware.toolchain import detect_arm_gcc, detect_qemu

    info = detect_arm_gcc()
    if info is None:
        return Check("ARM toolchain", False,
                     "arm-none-eabi-gcc not found anywhere — install it "
                     "from Modules → Install ARM toolchain; RITA downloads "
                     "the release matching your Zephyr SDK's gcc.")
    ver = ".".join(map(str, info.version)) if info.version else "unknown"
    qemu = detect_qemu()
    if info.mismatch:
        return Check("ARM toolchain", False,
                     f"{info.cc} (gcc {ver}, from {info.source}) does NOT "
                     f"match your Zephyr SDK's gcc version — reinstall from "
                     f"Modules → Install ARM toolchain to get the matching "
                     f"release.")
    if qemu is None:
        from .firmware.unity import NO_QEMU_REASON

        return Check("ARM toolchain", False,
                     f"{info.cc} (gcc {ver}) is ready, but {NO_QEMU_REASON}")
    return Check("ARM toolchain", True,
                 f"{info.cc} (gcc {ver}, from {info.source}); "
                 f"tests run under {qemu}")


def _unity(cfg: RitaConfig) -> Check:
    from .firmware import unity as _u

    found = _u.detect_unity()
    if found is None:
        return Check("Unity", False,
                     "not installed — the unit tier reports itself skipped. "
                     "Install it from the Modules page.")
    cc = _u.find_compiler(cfg.host_cc)
    if cc is None:
        return Check("Unity", False, f"{found}; {_u.no_compiler_reason()}")
    return Check("Unity", True, f"{found}; compiler: {cc.path} ({cc.source})")


def run_checks(cfg: RitaConfig | None = None, deep: bool = False) -> list[Check]:
    cfg = cfg or RitaConfig()
    checks = [_workspace(cfg), _coder(cfg)]
    if deep:
        checks.append(_coder_live(cfg))
    checks += [_mcp(cfg), _voice(), _west(cfg), _sdk(),
               _arm_toolchain(cfg), _cerberus(), _unity(cfg)]
    return checks


def report(cfg: RitaConfig | None = None, deep: bool = False) -> str:
    """A speakable summary line + the full findings for the screen pane."""
    checks = run_checks(cfg, deep=deep)
    bad = [c for c in checks if not c.ok]
    head = (f"Setup check: {len(checks) - len(bad)} of {len(checks)} good."
            + (f" Needs attention: {', '.join(c.name for c in bad)}."
               if bad else " Everything I need is in place."))
    lines = [f"[{'OK ' if c.ok else 'FIX'}] {c.name}: {c.detail}"
             for c in checks]
    return head + "\n\n" + "\n".join(lines)
