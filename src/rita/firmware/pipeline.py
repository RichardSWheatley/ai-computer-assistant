"""The iterate loop (Fix 3) — owned by the orchestrator, gated by twister.

Claude does one step per invocation (patch a concrete failure); this
pipeline decides what runs, where, and when to stop:

    RESOLVE -> BUILD -> SIM_TEST -> DEVICE
                 ^________|  (a sim patch re-enters at BUILD)

Sim-first always; bounded retries at every stage; exhaustion is a REPORTED
outcome; the device tier stays blocked until the bench milestone and is
never faked green. Between stages the optional TaskControl checkpoint makes
the pipeline pausable (Fix 4) — hardware operations themselves are atomic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..config import RitaConfig
from .boards import build_boards_json
from .claude import ClaudeWorker
from .index import VerificationIndex
from .resolve import Resolution, resolve_verification
from .twister_results import FailureArtifact
from .west import ZephyrRunner

SIM_PLATFORM = "native_sim"


def applications_root(cfg: RitaConfig) -> Path:
    """Where scaffolded applications live: inside the workspace, beside
    zephyr/ — never in it (see knowledge topic `app-locations`)."""
    if cfg.applications_dir:
        return Path(cfg.applications_dir)
    return Path(cfg.workspace or ".") / "applications"


def _app_slug(goal: str) -> str:
    words = [w for w in Utterance_norm(goal).split()
             if w not in ("an", "a", "the", "for", "me", "that", "with", "on",
                          "in", "please", "build", "write", "create", "make")]
    return "-".join(words[:4]) or "app"


def Utterance_norm(text: str) -> str:
    from ..routing.model import normalize

    return normalize(text)

StageName = Literal["RESOLVE", "STATIC", "UNIT_TEST", "FINAL_TEST", "DEVICE"]
Outcome = Literal["green", "blocked", "skipped", "retries_exhausted", "failed"]


@dataclass(frozen=True)
class StageResult:
    stage: StageName
    outcome: Outcome
    detail: str = ""
    failures: tuple[FailureArtifact, ...] = ()


@dataclass
class PipelineReport:
    goal: str
    outcome: Outcome
    stages: list[StageResult] = field(default_factory=list)
    resolution: Resolution | None = None


class IteratePipeline:
    def __init__(self, *, runner: ZephyrRunner, claude: ClaudeWorker,
                 index: VerificationIndex, cfg: RitaConfig,
                 workdir: str | Path, boards: dict | None = None,
                 static_checker=None, unit_runner=None, on_stage=None) -> None:
        self.runner = runner
        self.claude = claude
        self.index = index
        self.cfg = cfg
        self.workdir = Path(workdir)
        # The CERBERUS gate (StaticChecker). None = not configured: the
        # STATIC stage reports skipped — visible, never silently green.
        self.static_checker = static_checker
        # The unit tier (UnityRunner). None = Unity/compiler unavailable:
        # the UNIT_TEST stage reports skipped with the reason.
        self.unit_runner = unit_runner
        self.on_stage = on_stage      # callable(StageResult) -> None (events/UI)
        if boards is None and cfg.workspace:
            boards = build_boards_json(cfg.workspace).get("boards", {})
        self.boards = boards or {}

    # --- helpers ------------------------------------------------------------

    def _platform(self, board: str) -> str:
        info = self.boards.get(board) or {}
        return str(info.get("twister_platform") or board)

    def _record(self, report: PipelineReport, stage: StageResult) -> None:
        report.stages.append(stage)
        if self.on_stage is not None:
            self.on_stage(stage)

    @staticmethod
    def _checkpoint(ctl, completed_stage: str) -> None:
        # Fix 4 seam: checkpoints exist ONLY between stages; a running west/
        # flash/measure operation is atomic and never interrupted mid-op.
        if ctl is not None:
            ctl.checkpoint(completed_stage)

    # --- the loop -----------------------------------------------------------

    def run(self, *, goal: str, board: str, terms: list[str],
            scaffold: bool = False, ctl=None) -> PipelineReport:
        report = PipelineReport(goal=goal, outcome="failed")
        self.workdir.mkdir(parents=True, exist_ok=True)

        # 1. RESOLVE (and scaffold when the request is to write an app).
        # Scaffolded apps land under applications_dir (workspace convention),
        # with the shipped Zephyr conventions attached to the request.
        build_target: Path
        app_dir = self.workdir / "app"
        if scaffold:
            from . import knowledge

            app_dir = applications_root(self.cfg) / _app_slug(goal)
            notes = knowledge.notes_for(terms + goal.split())
            enriched = goal if not notes else f"{goal}\n\nZephyr notes:\n{notes}"
            scaffolded = self.claude.scaffold(enriched, board, app_dir)
            if not scaffolded.ok:
                self._record(report, StageResult("RESOLVE", "failed",
                                                 f"scaffold failed: {scaffolded.detail}"))
                return report
        resolution = resolve_verification(
            goal=goal, board=board, terms=terms, index=self.index,
            complete=self.claude.complete, write_dir=self.workdir / "authored",
            workspace=self.cfg.workspace)
        report.resolution = resolution
        if resolution.method == "existing":
            suite_dir = Path(self.cfg.workspace) / resolution.entry.path
        else:
            suite_dir = self.workdir / "authored"
        build_target = app_dir if scaffold else suite_dir
        self._record(report, StageResult(
            "RESOLVE", "green",
            f"{resolution.method}: "
            f"{resolution.entry.id if resolution.entry else resolution.written.test_id}"))
        self._checkpoint(ctl, "RESOLVE")

        # The user's flow: code -> STATIC (CERBERUS) -> UNIT_TEST (every
        # function's input/output parameters, host Unity) -> iterate ->
        # FINAL_TEST (the Zephyr samples/tests). EVERY patch re-enters at
        # STATIC: patched code re-passes every gate before moving on.
        max_cycles = self.cfg.max_patch_cycles
        static_patches = unit_patches = final_patches = 0
        static_skip_noted = unit_skip_noted = unit_authored = False
        while True:
            # --- STATIC: CERBERUS on the code -------------------------------
            if self.static_checker is None:
                if not static_skip_noted:
                    self._record(report, StageResult(
                        "STATIC", "skipped",
                        "CERBERUS not configured (set cerberus_command)"))
                    static_skip_noted = True
            else:
                sres = self.static_checker.check(build_target)
                if not sres.ok:
                    if static_patches >= max_cycles:
                        self._record(report, StageResult(
                            "STATIC", "retries_exhausted",
                            f"findings persist after {static_patches} patch cycles",
                            failures=sres.findings))
                        self._record(report, StageResult(
                            "DEVICE", "blocked",
                            "not attempted: static gate never passed"))
                        report.outcome = "retries_exhausted"
                        return report
                    self.claude.patch(sres.findings[0], build_target)
                    static_patches += 1
                    continue
                self._record(report, StageResult(
                    "STATIC", "green", f"after {static_patches} patch cycles"))
                self._checkpoint(ctl, "STATIC")

            # --- UNIT_TEST: every function, input/output parameters --------
            if not scaffold:
                if not unit_skip_noted:
                    self._record(report, StageResult(
                        "UNIT_TEST", "skipped",
                        "no authored code (existing sample run)"))
                    unit_skip_noted = True
            elif self.unit_runner is None:
                if not unit_skip_noted:
                    self._record(report, StageResult(
                        "UNIT_TEST", "skipped",
                        "Unity not installed — install it from the Modules "
                        "page (the compiler comes from PATH or your Zephyr SDK)"))
                    unit_skip_noted = True
            else:
                from .functions import list_functions, untested_functions
                from .testwriter import write_unity_tests

                src_dir = app_dir / "src"
                unit_dir = app_dir / "tests" / "unit"
                missing = untested_functions(src_dir, unit_dir)
                if missing and not unit_authored:
                    try:
                        write_unity_tests(goal, list_functions(src_dir),
                                          unit_dir, self.claude.complete)
                    except ValueError as exc:
                        self._record(report, StageResult(
                            "UNIT_TEST", "failed",
                            f"unit-test authorship rejected: {exc}"))
                        return report
                    unit_authored = True
                    missing = untested_functions(src_dir, unit_dir)
                if missing:
                    artifact = FailureArtifact(
                        kind="unit", suite="unit coverage", platform="host",
                        reason="functions without unit tests",
                        log_excerpt="every function must be tested for its "
                                    "input/output parameters; missing: "
                                    + ", ".join(f.name for f in missing),
                        file_hints=tuple(f.file for f in missing))
                    if unit_patches >= max_cycles:
                        self._record(report, StageResult(
                            "UNIT_TEST", "retries_exhausted",
                            "coverage still incomplete after "
                            f"{unit_patches} patch cycles",
                            failures=(artifact,)))
                        self._record(report, StageResult(
                            "DEVICE", "blocked",
                            "not attempted: unit tier never passed"))
                        report.outcome = "retries_exhausted"
                        return report
                    self.claude.patch(artifact, app_dir)
                    unit_patches += 1
                    continue
                ures = self.unit_runner.run(src_dir, unit_dir)
                if ures.unavailable:
                    if not unit_skip_noted:
                        self._record(report, StageResult(
                            "UNIT_TEST", "skipped", ures.reason))
                        unit_skip_noted = True
                elif not ures.ok:
                    if unit_patches >= max_cycles:
                        self._record(report, StageResult(
                            "UNIT_TEST", "retries_exhausted",
                            f"still failing after {unit_patches} patch cycles",
                            failures=ures.failures))
                        self._record(report, StageResult(
                            "DEVICE", "blocked",
                            "not attempted: unit tier never passed"))
                        report.outcome = "retries_exhausted"
                        return report
                    self.claude.patch(ures.failures[0], app_dir)
                    unit_patches += 1
                    continue
                else:
                    self._record(report, StageResult(
                        "UNIT_TEST", "green",
                        f"{ures.passed}/{ures.ran} function-contract tests "
                        f"passed after {unit_patches} patch cycles"))
                    self._checkpoint(ctl, "UNIT_TEST")

            # --- FINAL_TEST: the Zephyr samples/tests (twister) -------------
            bres = self.runner.build(build_target, SIM_PLATFORM,
                                     self.workdir / "build")
            if not bres.ok:
                if final_patches >= max_cycles:
                    self._record(report, StageResult(
                        "FINAL_TEST", "retries_exhausted",
                        f"build still failing after {final_patches} patch cycles",
                        failures=(bres.failure,)))
                    self._record(report, StageResult(
                        "DEVICE", "blocked",
                        "not attempted: final test never went green"))
                    report.outcome = "retries_exhausted"
                    return report
                self.claude.patch(bres.failure, build_target)
                final_patches += 1
                continue
            self._checkpoint(ctl, "FINAL_BUILD")

            tres = self.runner.twister(testsuite=suite_dir,
                                       platform=SIM_PLATFORM,
                                       outdir=self.workdir / "twister-final")
            if tres.ok:
                self._record(report, StageResult(
                    "FINAL_TEST", "green",
                    f"Zephyr suite green after {final_patches} patch cycles"))
                self._checkpoint(ctl, "FINAL_TEST")
                break
            if final_patches >= max_cycles:
                self._record(report, StageResult(
                    "FINAL_TEST", "retries_exhausted",
                    f"still failing after {final_patches} patch cycles",
                    failures=tres.failures))
                self._record(report, StageResult(
                    "DEVICE", "blocked",
                    "not attempted: final test never went green"))
                report.outcome = "retries_exhausted"
                return report
            self.claude.patch(tres.failures[0], build_target)
            final_patches += 1
            # loop -> STATIC: every patch re-passes every gate.

        # 4. DEVICE — blocked until the bench milestone; never faked green.
        if not self.cfg.device_tier_enabled:
            self._record(report, StageResult(
                "DEVICE", "blocked",
                "device tier blocked on the bench milestone (docs/BENCH-PLAN.md)"))
            report.outcome = "green"
            return report

        hw_map = Path(self.cfg.hardware_map) if self.cfg.hardware_map else None
        if hw_map is None or not hw_map.exists():
            hw_map = self.runner.generate_hardware_map(self.workdir / "map.yaml")
        device_patches = 0
        platform = self._platform(board)
        while True:
            dres = self.runner.twister(testsuite=suite_dir, platform=platform,
                                       outdir=self.workdir / "twister-device",
                                       device=True, hardware_map=hw_map)
            if dres.ok:
                self._record(report, StageResult(
                    "DEVICE", "green", f"after {device_patches} patch cycles"))
                report.outcome = "green"
                return report
            if device_patches >= max_cycles:
                self._record(report, StageResult(
                    "DEVICE", "retries_exhausted",
                    f"still failing after {device_patches} patch cycles",
                    failures=dres.failures))
                report.outcome = "retries_exhausted"
                return report
            self.claude.patch(dres.failures[0], build_target)
            device_patches += 1
            self._checkpoint(ctl, "DEVICE_PATCH")


def describe(report: PipelineReport) -> str:
    """One-sentence spoken summary; details belong to the screen channel."""
    if report.outcome == "green":
        device = next((s for s in report.stages if s.stage == "DEVICE"), None)
        if device is not None and device.outcome == "green":
            return "Green across build, simulation, and the device."
        return ("Build and simulation are green; the device tier is blocked "
                "pending the bench milestone.")
    if report.outcome == "retries_exhausted":
        bad = next(s for s in report.stages if s.outcome == "retries_exhausted")
        return (f"I stopped: {bad.stage.lower().replace('_', ' ')} is still "
                f"failing after the patch budget. The log is on screen.")
    return "The pipeline hit an infrastructure problem; details are on screen."


def dispatch_params(dispatch) -> dict:
    """Map a routed work dispatch to pipeline run() parameters."""
    e = dispatch.entities
    board = e.board or "native_sim"
    terms = [t for t in (e.sample, e.peripheral) if t]
    if not terms:
        terms = [t for t in dispatch.residual.split() if len(t) > 2]
    return {"goal": dispatch.residual or "firmware work", "board": board,
            "terms": terms, "scaffold": dispatch.verb == "scaffold"}


def handle_work_dispatch(dispatch, pipeline: IteratePipeline) -> str:
    """Router work dispatch -> pipeline run -> spoken summary (Fix 1 -> Fix 3)."""
    report = pipeline.run(**dispatch_params(dispatch))
    return describe(report)
