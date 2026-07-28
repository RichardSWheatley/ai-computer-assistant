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

StageName = Literal["RESOLVE", "BUILD", "SIM_TEST", "DEVICE"]
Outcome = Literal["green", "blocked", "retries_exhausted", "failed"]


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
                 on_stage=None) -> None:
        self.runner = runner
        self.claude = claude
        self.index = index
        self.cfg = cfg
        self.workdir = Path(workdir)
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

        # 2/3. BUILD then SIM_TEST; a sim patch re-enters at BUILD.
        max_cycles = self.cfg.max_patch_cycles
        build_patches = sim_patches = 0
        while True:
            bres = self.runner.build(build_target, SIM_PLATFORM,
                                     self.workdir / "build")
            if not bres.ok:
                if build_patches >= max_cycles:
                    self._record(report, StageResult(
                        "BUILD", "retries_exhausted",
                        f"still failing after {build_patches} patch cycles",
                        failures=(bres.failure,)))
                    self._record(report, StageResult(
                        "DEVICE", "blocked", "not attempted: sim never went green"))
                    report.outcome = "retries_exhausted"
                    return report
                self.claude.patch(bres.failure, build_target)
                build_patches += 1
                continue
            self._record(report, StageResult(
                "BUILD", "green", f"after {build_patches} patch cycles"))
            self._checkpoint(ctl, "BUILD")

            tres = self.runner.twister(testsuite=suite_dir,
                                       platform=SIM_PLATFORM,
                                       outdir=self.workdir / "twister-sim")
            if tres.ok:
                self._record(report, StageResult(
                    "SIM_TEST", "green", f"after {sim_patches} patch cycles"))
                self._checkpoint(ctl, "SIM_TEST")
                break
            if sim_patches >= max_cycles:
                self._record(report, StageResult(
                    "SIM_TEST", "retries_exhausted",
                    f"still failing after {sim_patches} patch cycles",
                    failures=tres.failures))
                self._record(report, StageResult(
                    "DEVICE", "blocked", "not attempted: sim never went green"))
                report.outcome = "retries_exhausted"
                return report
            self.claude.patch(tres.failures[0], build_target)
            sim_patches += 1
            # goto BUILD: cheap in sim, and a patch can break the build.

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


def handle_work_dispatch(dispatch, pipeline: IteratePipeline) -> str:
    """Router work dispatch -> pipeline run -> spoken summary (Fix 1 -> Fix 3)."""
    e = dispatch.entities
    board = e.board or "native_sim"
    terms = [t for t in (e.sample, e.peripheral) if t]
    if not terms:
        terms = [t for t in dispatch.residual.split() if len(t) > 2]
    report = pipeline.run(goal=dispatch.residual or "firmware work",
                          board=board, terms=terms,
                          scaffold=dispatch.verb == "scaffold")
    return describe(report)
