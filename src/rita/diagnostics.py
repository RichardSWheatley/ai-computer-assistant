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


# The transport check MUST be multi-line: the owner's agent received
# one-line "ok" checks perfectly for weeks while cmd.exe was truncating
# every real multi-line prompt at its first newline. A diagnostic that
# doesn't exercise the product's exact failure mode certifies nothing.
_TRANSPORT_PROMPT = (
    "This is a prompt-transport check and it has several lines.\n"
    "The middle line contains the codeword: LANTERN.\n"
    "If you can read the codeword on the middle line, reply with "
    "exactly: INTACT LANTERN. If this message seems cut off before "
    "the codeword, reply with exactly: TRUNCATED.")


def _coder_live(cfg: RitaConfig) -> Check:
    """Actually run the agent — through the SAME transport the pipeline
    uses (CoderCli), never a private invocation path: this check once
    said 'ok' over its own one-liner while the product's multi-line
    prompts were being truncated by the .CMD shim."""
    name = "coding agent (live)"
    if not cfg.coder_command:
        return Check(name, False, "Not configured — nothing to run.")
    from .firmware.coder import CoderCli
    from .firmware.static_check import split_command

    try:
        cli = CoderCli(cfg.workspace or ".",
                       command=tuple(split_command(cfg.coder_command)),
                       timeout=_SMOKE_TIMEOUT)
        out = cli.complete(_TRANSPORT_PROMPT).strip()
    except FileNotFoundError as exc:
        return Check(name, False, str(exc))
    except subprocess.TimeoutExpired:
        return Check(name, False,
                     f"no reply within {_SMOKE_TIMEOUT:.0f}s — is the agent "
                     f"waiting for a login or a prompt?")
    except RuntimeError as exc:
        blob = str(exc).lower()
        hint = ""
        if any(h in blob for h in _AUTH_HINTS):
            hint = (" — the agent isn't logged in: click 'Log in coding "
                    "agent' on the Settings page (RITA opens the login "
                    "window for you), then run this check again.")
        return Check(name, False, f"{exc}{hint}")
    upper = out.upper()
    if "TRUNCATED" in upper or "CUT OFF" in upper or "ENDS AT" in upper:
        return Check(name, False,
                     f"the agent runs, but MULTI-LINE PROMPTS ARE BEING "
                     f"TRUNCATED in transit (it replied: {out[:120]!r}). "
                     f"This happens when the agent command is a .cmd/.bat "
                     f"shim — update RITA (v0.29+ sends prompts via "
                     f"stdin), or configure the agent's real executable.")
    if "INTACT" in upper and "LANTERN" in upper:
        detail = ("replied correctly — multi-line prompt transport "
                  "verified end to end.")
        stderr = cli.last_stderr.strip()
        if stderr:
            # The agent CLI reporting its own config problems (e.g.
            # malformed permission rules) — it repeats this noise on
            # EVERY call, so name it here instead of letting it hide
            # until it pollutes a failure dump.
            detail += (f" NOTE — your agent CLI printed warnings about "
                       f"its own configuration (it repeats these on "
                       f"every call; fix them where the message says): "
                       f"{stderr[:300]}")
        return Check(name, True, detail)
    return Check(name, False,
                 f"the agent replied, but not to the question asked — "
                 f"transport is suspect. It said: {out[:160]!r}")


def _mcp(cfg: RitaConfig) -> Check:
    """The workspace MCP server: config present AND the command runs."""
    import json

    from .home import mcp_config_path

    p = mcp_config_path()
    if not p.exists():
        return Check("workspace MCP", False,
                     "Not wired yet — press Sync in your chat tab. "
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
                     f"press Sync in your chat tab to rewrite it.")
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
    from .firmware.toolchain import (detect_arm_gcc, detect_qemu,
                                     release_for, zephyr_gcc_probe)

    want, evidence = zephyr_gcc_probe()
    sdk_note = (f" Your Zephyr SDK's gcc is {want[0]}.{want[1]} "
                f"(release {release_for(want)})." if want else
                f" Your Zephyr SDK's gcc version could not be read — "
                f"{evidence}.")
    info = detect_arm_gcc()
    if info is None:
        return Check("ARM toolchain", False,
                     "arm-none-eabi-gcc not found anywhere — install it "
                     "from Modules → Install ARM toolchain; RITA downloads "
                     "the release matching your Zephyr SDK's gcc."
                     + sdk_note)
    ver = ".".join(map(str, info.version)) if info.version else "unknown"
    qemu = detect_qemu()
    if info.mismatch:
        return Check("ARM toolchain", False,
                     f"{info.cc} (gcc {ver}, from {info.source}) does NOT "
                     f"match your Zephyr SDK's gcc.{sdk_note} Reinstall "
                     f"from Modules → Install ARM toolchain to get the "
                     f"matching release.")
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
