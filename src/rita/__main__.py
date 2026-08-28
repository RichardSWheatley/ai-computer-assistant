"""CLI entry point.

Commands:
  rita doctor            Show detected hardware + the model recommendation.
  rita plugins           List built-in + discovered plugins and their tools.
  rita run "<goal>"      Run the agent loop toward a goal (mock-safe).
"""

from __future__ import annotations

import argparse
import sys

from . import platform_support
from .app import build_assistant
from .config import load_config
from .hardware import detect_hardware, recommend_model


def cmd_doctor(_args) -> int:
    hw = detect_hardware()
    rec = recommend_model(hw)
    print("=== RITA hardware doctor ===")
    print(f"platform        : {hw.platform}"
          f"  (first-pass supported: {platform_support.is_supported()})")
    print(f"a11y backend    : {platform_support.a11y_backend()}")
    print(f"input backend   : {platform_support.input_backend()}")
    print(f"system RAM (MB) : {hw.system_ram_mb or 'unknown'}")
    print(f"GPUs detected   : {len(hw.gpus)}")
    for g in hw.gpus:
        print(f"  - {g.name}: {g.vram_mb} MB VRAM ({g.backend})")
    print(f"VRAM present    : {hw.has_vram}  (total {hw.total_vram_mb} MB)")
    print(f"acceleration    : {hw.acceleration}")
    print(f"recommended tier: {rec['tier']}  ->  {rec['local_model']}")
    print(f"lean on cloud   : {rec['lean_on_cloud']}")
    print(f"note            : {rec['note']}")
    print(f"os note         : {platform_support.notes()}")
    cfg = load_config()
    print(f"default mode    : {cfg.mode}  (use `rita run --local-only` for privacy)")
    return 0


def cmd_plugins(_args) -> int:
    cfg = load_config()
    asst = build_assistant(cfg)
    print("=== Registered tools ===")
    for s in asst.registry.schemas():
        print(f"  {s.name:14} [{s.permission_tier:14}] {s.description}")
    return 0


def cmd_run(args) -> int:
    cfg = load_config(local_only=args.local_only)
    if args.live:
        cfg.dry_run = False          # actually move the mouse / type for real
    confirm = None
    if args.confirm:
        from .ui.console import make_console_confirmer
        confirm = make_console_confirmer()
    asst = build_assistant(cfg, confirm=confirm, headless=not args.live)
    mode_note = "LIVE (real input)" if args.live else "simulation (safe)"
    gate = "interactive" if args.confirm else "secure-default (block unattended)"
    print(f"=== Run: {args.goal!r}  [mode: {cfg.mode} | {mode_note} | approvals: {gate}] ===")
    result = asst.run(args.goal)
    for st in result.steps:
        flag = "ok " if st.ok else "ERR"
        print(f"  [{st.step:02d}] {flag} {st.call.tool:12} -> {st.detail}")
    if hasattr(asst.planner, "last_route"):
        print(f"last route      : {asst.planner.last_route}")
    print(f"finished: {result.finished} | {result.message}")
    return 0


def cmd_doc(args) -> int:
    import json
    spec = json.loads(open(args.spec).read())
    if args.kind == "deck":
        from .business.pptx_builder import build_deck
        out = args.out or "deck.pptx"
        path = build_deck(spec, out)
    elif args.kind == "report":
        from .business.docx_builder import build_report
        out = args.out or "report.docx"
        path = build_report(spec, out)
    else:  # sheet
        from .business.xlsx_builder import build_workbook
        out = args.out or "workbook.xlsx"
        path = build_workbook(spec, out)
    print(f"wrote {path}")
    return 0


def cmd_talk(args) -> int:
    from .config import load_rita_config
    from .supervisor import Supervisor

    sup = Supervisor()
    try:
        loop = sup.make_voice_loop(push_to_talk=args.push_to_talk,
                                   seconds=args.seconds, model=args.model)
    except Exception as exc:  # pragma: no cover
        print(f"voice deps missing: {exc}\n  pip install -e \".[voice]\"")
        return 1
    name = load_rita_config().assistant_name
    listen = "push-to-talk (Enter)" if args.push_to_talk else f"continuous ({args.seconds}s turns)"
    ws = sup.cfg.workspace or "not configured (run: sync --workspace <path>)"
    print(f"=== Talk to {name}  [{listen}] ===")
    print(f"workspace: {ws}")
    print(f"Wake with 'hello {name}'. Say 'stop listening' or press Ctrl+C to end.")
    loop.run()
    return 0


def cmd_cerberus(args) -> int:
    from .firmware.cerberus_setup import CERBERUS_REPO_URL, install_cerberus

    if args.action == "install":
        res = install_cerberus(url=args.url or CERBERUS_REPO_URL)
        print(res.detail)
        return 0 if res.ok else 1
    from .firmware.cerberus_setup import detect_cerberus
    clone = detect_cerberus()
    print(f"CERBERUS: {clone}" if clone else
          "CERBERUS: not installed (rita cerberus install)")
    return 0


def cmd_unity(args) -> int:
    from .firmware.unity import UNITY_REPO_URL, detect_unity, install_unity

    if args.action == "install":
        res = install_unity(url=args.url or UNITY_REPO_URL)
        print(res.detail)
        return 0 if res.ok else 1
    found = detect_unity()
    print(f"Unity: {found}" if found else
          "Unity: not installed (rita unity install)")
    return 0


def cmd_module_run(args) -> int:
    """Host one capability module over stdio (what manifests point at).

    Works identically from a venv (`python -m rita module-run X`) and a
    frozen bundle (`rita.exe module-run X`) — no `python -m` needed."""
    import runpy

    from .modules.install import SHIPPED

    if args.name not in SHIPPED:
        print(f"unknown module: {args.name} (have: {', '.join(SHIPPED)})")
        return 2
    runpy.run_module(SHIPPED[args.name][0], run_name="__main__")
    return 0


def cmd_modules(args) -> int:
    from .modules.registry import ModuleRegistry

    if args.action == "install":
        from .modules.install import dev_install
        only = args.only.split(",") if args.only else None
        for m in dev_install(only=only):
            print(f"installed {m.name} {m.version}")
        return 0
    reg = ModuleRegistry()
    found = reg.discover()
    if not found:
        print("no modules installed (try: modules install --dev)")
        return 0
    for name, versions in found.items():
        cur = reg.current(name)
        marks = ", ".join(f"{v}*" if v == cur else v for v in versions)
        print(f"  {name:14} {marks}   (* = current)")
    return 0


def _workspace_from(args) -> str | None:
    from .config import load_rita_config

    return args.workspace or load_rita_config().workspace


def cmd_sync(args) -> int:
    from .config import load_rita_config, save_rita_config
    from .firmware.sync import sync_workspace

    ws = _workspace_from(args)
    if not ws:
        print("no workspace: pass --workspace or set it in ~/.rita/config")
        return 1
    try:
        res = sync_workspace(ws, hw_map=args.hardware_map)
    except ValueError as exc:
        print(f"sync failed: {exc}")
        return 1
    if args.workspace:  # remember it for next time
        cfg = load_rita_config()
        cfg.workspace = str(args.workspace)
        if args.hardware_map:
            cfg.hardware_map = str(args.hardware_map)
        save_rita_config(cfg)
    print(f"synced {res.boards} boards -> {res.boards_path}")
    print(f"indexed {res.entries} suites -> {res.index_path}")
    return 0


def cmd_toolchain(args) -> int:
    from .firmware.toolchain import detect_arm_gcc, install_arm_gcc

    if args.action == "install":
        res = install_arm_gcc(release=getattr(args, "release", None))
        print(res.detail)
        return 0 if res.ok else 1
    info = detect_arm_gcc()
    if info is None:
        print("no ARM toolchain found — `rita toolchain install` downloads "
              "the release matching your Zephyr SDK's gcc")
        return 1
    from .firmware.toolchain import zephyr_gcc_version

    ver = ".".join(map(str, info.version)) if info.version else "unknown"
    if info.mismatch:
        match = "MISMATCH vs Zephyr SDK"
    elif zephyr_gcc_version() is not None:
        match = "matches Zephyr's gcc"
    else:
        match = "no Zephyr SDK gcc to match"
    print(f"{info.cc} (gcc {ver}, from {info.source}; {match})")
    return 0


def cmd_check(args) -> int:
    """Setup report. Also the packaged-build smoke test: CI runs this from
    the frozen bundle so bundle-only breakage (a package PyInstaller
    couldn't see) fails the build instead of reaching a user."""
    from .config import load_rita_config
    from .diagnostics import report, run_checks

    cfg = load_rita_config()
    print(report(cfg, deep=args.deep))
    if not args.require:
        return 0
    wanted = {n.strip().lower() for n in args.require.split(",")}
    bad = [c for c in run_checks(cfg, deep=args.deep)
           if c.name.lower() in wanted and not c.ok]
    if bad:
        print("\nREQUIRED CHECKS FAILED: "
              + ", ".join(f"{c.name} ({c.detail})" for c in bad))
        return 1
    return 0


def cmd_mcp_serve(args) -> int:
    from .mcpserver.server import serve

    ws = _workspace_from(args)
    if not ws:
        print("no workspace: pass --workspace or set it in ~/.rita/config")
        return 1
    return serve(ws)


def cmd_workflow(args) -> int:
    from .workflows.engine import BUILTINS, WorkflowEngine
    if args.name not in BUILTINS:
        print(f"unknown workflow: {args.name}")
        print("available:", ", ".join(BUILTINS))
        return 1
    cfg = load_config(local_only=args.local_only)
    confirm = None
    if args.confirm:
        from .ui.console import make_console_confirmer
        confirm = make_console_confirmer()
    asst = build_assistant(cfg, confirm=confirm)
    print(f"=== Workflow: {args.name} ===")
    res = WorkflowEngine(asst).run_named(args.name)
    for i, step in enumerate(res.step_results, 1):
        print(f"  step {i}: finished={getattr(step, 'finished', '?')} "
              f"| {getattr(step, 'message', '')}")
    print(f"completed: {res.completed} | {res.message}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # A console tool must survive ANY console encoding: Windows terminals
    # are cp1252, and a diagnostic that crashes while PRINTING the
    # diagnostic (e.g. a → in a check detail) helps nobody. Degrade
    # unencodable characters instead of dying.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(prog="rita",
                                     description="RITA: deterministic firmware orchestrator with a speech front end")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="show hardware + model recommendation")
    sub.add_parser("plugins", help="list registered tools")
    run = sub.add_parser("run", help="run the agent toward a goal")
    run.add_argument("goal", help="natural-language goal")
    run.add_argument("--local-only", action="store_true",
                     help="privacy mode: never use the cloud (nothing leaves the machine)")
    run.add_argument("--confirm", action="store_true",
                     help="prompt for approval on high-risk actions instead of blocking them")
    run.add_argument("--live", action="store_true",
                     help="drive the real screen/mouse/keyboard (default is a safe simulation)")

    doc = sub.add_parser("doc", help="generate a document from a JSON spec (no GPU/key needed)")
    doc.add_argument("kind", choices=["deck", "report", "sheet"],
                     help="deck=.pptx, report=.docx, sheet=.xlsx")
    doc.add_argument("spec", help="path to a JSON spec file")
    doc.add_argument("-o", "--out", help="output path (default chosen by kind)")

    wf = sub.add_parser("workflow", help="run a saved multi-step workflow")
    wf.add_argument("name", help="workflow name (e.g. daily_brief, meeting_prep)")
    wf.add_argument("--local-only", action="store_true")
    wf.add_argument("--confirm", action="store_true")

    talk = sub.add_parser("talk", help="voice mode: speak to the assistant, it speaks back")
    talk.add_argument("--live", action="store_true",
                      help="drive the real screen (default is a safe simulation)")
    talk.add_argument("--confirm", action="store_true",
                      help="prompt for approval on high-risk actions")
    talk.add_argument("--local-only", action="store_true")
    talk.add_argument("--push-to-talk", action="store_true",
                      help="press Enter to start each turn (vs continuous listening)")
    talk.add_argument("--seconds", type=float, default=5.0,
                      help="seconds to record per turn in continuous mode (default 5)")
    talk.add_argument("--model", default="base",
                      help="Whisper model size: tiny|base|small|medium (default base)")

    sync = sub.add_parser("sync", help="index the Zephyr workspace into ~/.rita "
                                       "(boards.json + verification index)")
    sync.add_argument("--workspace", help="Zephyr workspace root (persisted to config)")
    sync.add_argument("--hardware-map", help="twister map.yaml for connected boards")

    mcp = sub.add_parser("mcp-serve", help="serve the workspace MCP server over stdio")
    mcp.add_argument("--workspace", help="Zephyr workspace root (default from config)")

    mods = sub.add_parser("modules", help="list or install capability modules")
    mods.add_argument("action", nargs="?", default="list",
                      choices=["list", "install"])
    mods.add_argument("--dev", action="store_true",
                      help="install manifests pointing at this package")
    mods.add_argument("--only", help="comma-separated module names to install")

    mrun = sub.add_parser("module-run",
                          help="host one capability module over stdio")
    mrun.add_argument("name", help="module name (e.g. zephyr-runner)")

    cerb = sub.add_parser("cerberus",
                          help="install or inspect the CERBERUS static gate")
    cerb.add_argument("action", nargs="?", default="status",
                      choices=["status", "install"])
    cerb.add_argument("--url", help="override the CERBERUS repo URL")

    uni = sub.add_parser("unity",
                         help="install or inspect the Unity unit-test framework")
    uni.add_argument("action", nargs="?", default="status",
                     choices=["status", "install"])
    uni.add_argument("--url", help="override the Unity repo URL")

    tc = sub.add_parser("toolchain",
                        help="install or inspect the ARM toolchain "
                             "(Zephyr's compiler family)")
    tc.add_argument("action", nargs="?", default="status",
                    choices=["status", "install"])
    tc.add_argument("--release",
                    help="exact Arm GNU release (e.g. 14.3.rel1); "
                         "default = derived from your SDK's gcc")

    chk = sub.add_parser("check", help="report this install's setup")
    chk.add_argument("--deep", action="store_true",
                     help="also run the coding agent for real")
    chk.add_argument("--require",
                     help="comma-separated check names that must pass "
                          "(exit 1 otherwise) — used by the packaged build")

    args = parser.parse_args(argv)
    return {"doctor": cmd_doctor, "plugins": cmd_plugins, "run": cmd_run,
            "check": cmd_check, "toolchain": cmd_toolchain,
            "doc": cmd_doc, "workflow": cmd_workflow, "talk": cmd_talk,
            "sync": cmd_sync, "mcp-serve": cmd_mcp_serve,
            "modules": cmd_modules, "module-run": cmd_module_run,
            "cerberus": cmd_cerberus, "unity": cmd_unity}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
