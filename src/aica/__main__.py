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
    asst = build_assistant(cfg)
    route = getattr(asst.planner, "mode", None)
    print(f"=== Run: {args.goal!r}  [mode: {cfg.mode}] ===")
    result = asst.run(args.goal)
    for st in result.steps:
        flag = "ok " if st.ok else "ERR"
        print(f"  [{st.step:02d}] {flag} {st.call.tool:12} -> {st.detail}")
    if hasattr(asst.planner, "last_route"):
        print(f"last route      : {asst.planner.last_route}")
    print(f"finished: {result.finished} | {result.message}")
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

    args = parser.parse_args(argv)
    return {"doctor": cmd_doctor, "plugins": cmd_plugins, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
