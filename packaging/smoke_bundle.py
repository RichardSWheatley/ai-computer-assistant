"""End-to-end smoke test of the BUILT bundle — not the source tree.

Source tests cannot see bundle-only breakage: a package PyInstaller failed
to collect, an entry point that only exists under `python -m`, an SDK whose
import moved. Every RITA failure reported from a real install so far was of
exactly this kind, so the packaged artifact gets exercised here — locally
and in CI — before anyone installs it.

Usage:  python packaging/smoke_bundle.py <dist>/RITA [--require voice]
Exit 0 = the bundle works; nonzero prints what failed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WS = REPO / "tests" / "fixtures" / "zephyr_ws"
TIMEOUT = 120


def _exe(bundle: Path, name: str) -> str:
    win = bundle / f"{name}.exe"
    return str(win if win.exists() else bundle / name)


def _run(argv, env, **kw):
    return subprocess.run(argv, capture_output=True, text=True, env=env,
                          timeout=TIMEOUT, **kw)


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: smoke_bundle.py <dist>/RITA [--require name,name]")
        return 2
    bundle = Path(argv[0]).resolve()
    require = ""
    if "--require" in argv:
        require = argv[argv.index("--require") + 1]
    cli = _exe(bundle, "rita")
    if not Path(cli).exists():
        print(f"FAIL: no CLI executable in {bundle}")
        return 1

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="rita-smoke-") as tmp:
        env = {**os.environ, "RITA_HOME": tmp}

        # 1. The console entry point runs at all.
        p = _run([cli, "doctor"], env)
        if p.returncode != 0:
            failures.append(f"`rita doctor` exited {p.returncode}: "
                            f"{p.stdout[-400:]}{p.stderr[-400:]}")

        # 2. Sync writes real workspace data through the frozen app.
        p = _run([cli, "sync", "--workspace", str(WS)], env)
        if p.returncode != 0 or not (Path(tmp) / "boards.json").exists():
            failures.append(f"`rita sync` failed ({p.returncode}): "
                            f"{p.stdout[-400:]}{p.stderr[-400:]}")

        # 3. mcp.json must name an executable that EXISTS and an absolute
        #    workspace (the agent launches it from its own directory).
        mcp_json = Path(tmp) / "mcp.json"
        if not mcp_json.exists():
            failures.append("sync wrote no mcp.json")
        else:
            server = json.loads(mcp_json.read_text())["mcpServers"]["rita-workspace"]
            if not Path(server["command"]).exists():
                failures.append(f"mcp.json command does not exist: "
                                f"{server['command']}")
            ws_arg = server["args"][-1]
            if not Path(ws_arg).is_absolute():
                failures.append(f"mcp.json workspace is relative: {ws_arg}")

        # 4. THE big one: the MCP server must actually boot in the bundle.
        #    A crash here kills the coding agent that launches it.
        #    stdin stays OPEN: a stdio server exits cleanly on EOF, so
        #    closing it would look like a crash. Alive after a few seconds
        #    is the pass condition.
        out_f = Path(tmp) / "mcp_serve.log"
        try:
            with out_f.open("w") as sink:
                proc = subprocess.Popen(
                    [cli, "mcp-serve", "--workspace", str(WS)], env=env,
                    stdin=subprocess.PIPE, stdout=sink,
                    stderr=subprocess.STDOUT, text=True)
                try:
                    proc.wait(timeout=8)
                    failures.append(
                        f"`rita mcp-serve` exited {proc.returncode} instead "
                        f"of serving: {out_f.read_text()[-700:]}")
                except subprocess.TimeoutExpired:
                    proc.kill()      # still running == healthy stdio server
                    proc.wait(timeout=10)
        except OSError as exc:
            failures.append(f"could not start mcp-serve: {exc}")

        # 5. Module hosting works inside the bundle (no `python -m`).
        p = _run([cli, "modules", "install"], env)
        if p.returncode != 0:
            failures.append(f"`rita modules install` exited {p.returncode}: "
                            f"{p.stderr[-300:]}")

        # 6. The bundle's own self-check, with required checks enforced.
        args = [cli, "check"] + (["--require", require] if require else [])
        p = _run(args, env)
        print(p.stdout)
        if p.stderr.strip():
            print("stderr:", p.stderr[-800:])
        if p.returncode != 0:
            failures.append("`rita check` failed: "
                            f"{(p.stdout or p.stderr)[-500:]}")
        if "ARM toolchain" not in p.stdout:
            failures.append("`rita check` says nothing about the ARM "
                            "toolchain — the unit tier's compiler is "
                            "unaccounted for")

    if failures:
        print("\nBUNDLE SMOKE TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nBundle smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
