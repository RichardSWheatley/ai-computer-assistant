"""CLI entry point.

Commands:
  aica doctor            Show detected hardware + the model recommendation.
  aica plugins           List built-in + discovered plugins and their tools.
  aica run "<goal>"      Run the agent loop toward a goal (mock-safe).
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
    print("=== AICA hardware doctor ===")
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
    print(f"lean on Claude  : {rec['lean_on_claude']}")
    print(f"note            : {rec['note']}")
    print(f"os note         : {platform_support.notes()}")
    cfg = load_config()
    print(f"default mode    : {cfg.mode}  (use `aica run --local-only` for privacy)")
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
    cfg = load_config(local_only=args.local_only)
    if args.live:
        cfg.dry_run = False
    confirm = None
    if args.confirm:
        from .ui.console import make_console_confirmer
        confirm = make_console_confirmer()
    asst = build_assistant(cfg, confirm=confirm, headless=not args.live)
    try:
        from .voice.loop import build_voice_loop
    except Exception as exc:  # pragma: no cover
        print(f"voice deps missing: {exc}\n  pip install -e \".[voice]\"")
        return 1
    loop = build_voice_loop(asst, push_to_talk=args.push_to_talk,
                            seconds=args.seconds, model=args.model)
    mode_note = "LIVE (real input)" if args.live else "simulation (safe)"
    listen = "push-to-talk (Enter)" if args.push_to_talk else f"continuous ({args.seconds}s turns)"
    print(f"=== Talk to AICA  [mode: {cfg.mode} | {mode_note} | {listen}] ===")
    print("Say 'stop listening' or press Ctrl+C to end.")
    loop.run()
    return 0


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
    parser = argparse.ArgumentParser(prog="aica",
                                     description="Local AI computer assistant")
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

    args = parser.parse_args(argv)
    return {"doctor": cmd_doctor, "plugins": cmd_plugins, "run": cmd_run,
            "doc": cmd_doc, "workflow": cmd_workflow, "talk": cmd_talk}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
