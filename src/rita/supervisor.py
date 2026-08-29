"""The thin supervisor (Fix 6): UI shell, router, task manager, modules.

Owns exactly what the directive says a supervisor owns — the voice/console
shell, the deterministic router (Fix 1), the TaskManager with PAUSE/STOP
(Fix 4), the output-channel split (Fix 5), and the module registry. Work
goes through the iterate pipeline (Fix 3) as managed tasks; the module
registry runs capabilities as versioned child processes, with in-process
seams as the fallback when a module isn't installed (dev/CI) — the same
pattern the legacy worker boundary uses.
"""

from __future__ import annotations

import os
from pathlib import Path

# Module-level so tests can pin the platform; the POSIX-only native_sim
# was the hardcoded default board — useless on the owner's Windows box.
_WINDOWS = os.name == "nt"

from .config import RitaConfig, load_rita_config
from .core.tasks import TaskManager, make_control_handler
from .modules.registry import ModuleRegistry
from .routing.model import Dispatch
from .routing.vocabulary import Vocabulary
from .voice.loop import RouterShell
from .voice.tts import PausableSpeaker


class Supervisor:
    def __init__(self, *, rita_cfg: RitaConfig | None = None,
                 config_path: str | Path | None = None,
                 vocab: Vocabulary | None = None,
                 tts=None, runner=None, coder=None, index=None,
                 registry: ModuleRegistry | None = None,
                 workdir: str | Path | None = None) -> None:
        self.cfg = rita_cfg or load_rita_config(config_path)
        self.config_path = config_path
        self.manager = TaskManager()
        self.registry = registry or ModuleRegistry()
        self.speaker = PausableSpeaker(tts) if tts is not None else None
        self._runner = runner
        self._coder = coder
        self._index = index
        if workdir is None:
            from .home import rita_home

            workdir = rita_home() / "work"
        self.workdir = Path(workdir)
        self._task_seq = 0
        self._facts: dict = {}   # lazy workspace-fact cache (cleared on sync)
        # Agent-activity narration sink (the GUI presenter subscribes).
        self.on_activity = None
        self.shell = RouterShell(
            vocab or Vocabulary.load(), config_path=config_path,
            work=self.handle_work, chat=self.handle_chat,
            control=make_control_handler(self.manager, self.speaker),
            project=self.hand_off)
        # The mic button is the gate; the wake word is opt-in config.
        self.shell.require_wake = bool(self.cfg.voice_wake_word)
        self.shell.awake = not self.shell.require_wake

    # --- capability wiring (module process when installed, seam otherwise) --

    def _make_runner(self):
        if self._runner is not None:
            return self._runner
        from .firmware.west import WestCli

        return WestCli(self.effective_workspace())

    def _make_coder(self):
        """The coding-agent seam: injected worker first, else the CLI named
        by config. Which CLI is config data, never code — None means RITA
        can't code and says so."""
        if self._coder is not None:
            return self._coder
        if not self.cfg.coder_command:
            return None
        from .firmware.coder import CoderCli
        from .firmware.static_check import split_command
        from .home import mcp_config_path

        mcp = mcp_config_path()
        cli = CoderCli(self.cfg.workspace,
                       command=tuple(split_command(self.cfg.coder_command)),
                       mcp_config=mcp if mcp.exists() else None)
        # Narrate agent activity into the GUI's screen pane when a
        # presenter has subscribed (self.on_activity set by the GUI).
        cli.on_activity = lambda msg: (self.on_activity(msg)
                                       if self.on_activity else None)
        return cli

    _NO_CODER = ("No coding agent is configured, so I can't write or patch "
                 "code yet. Set the coding agent command on the Settings "
                 "page (any CLI that takes a prompt and can edit files).")

    def _make_static_checker(self):
        """The CERBERUS gate: explicit command wins, else the acquired
        ~/.rita/cerberus clone (Head 1 scan — deterministic, keyless), else
        None and the STATIC stage reports skipped."""
        if self.cfg.cerberus_command:
            from .firmware.static_check import CerberusCli

            return CerberusCli(self.cfg.cerberus_command)
        from .firmware.cerberus_setup import default_checker, detect_cerberus

        clone = detect_cerberus()
        if clone is not None:
            return default_checker(clone, deep=self.cfg.cerberus_deep)
        return None

    def _make_unit_runner(self):
        """The unit tier: host Unity when the framework is on this machine.
        None = the UNIT_TEST stage reports skipped with the reason."""
        from .firmware.unity import HostUnity, detect_unity

        unity = detect_unity()
        if unity is None:
            return None
        return HostUnity(unity_src=unity, cc=self.cfg.host_cc)

    def _make_index(self):
        if self._index is not None:
            return self._index
        from .firmware.index import VerificationIndex
        from .home import verification_index_path

        ws = self.effective_workspace()
        if ws and ws != self.cfg.workspace:
            # A chat-bound workspace: index IT, not the global sync data.
            return VerificationIndex.build(ws)
        if verification_index_path().exists():
            return VerificationIndex.load()
        return VerificationIndex.build(self.cfg.workspace)

    # --- dispatch handlers ---------------------------------------------------

    def _default_board(self) -> str:
        # No table: one machine-aware line. native_sim is POSIX-only.
        return "qemu_x86" if _WINDOWS else "native_sim"

    def _build_pipeline(self, ws: str):
        from .firmware.pipeline import IteratePipeline

        self._task_seq += 1
        workdir = self.workdir / f"task-{self._task_seq}"
        cfg = self.cfg
        if ws != self.cfg.workspace:
            import dataclasses

            cfg = dataclasses.replace(self.cfg, workspace=ws)
        return IteratePipeline(
            runner=self._make_runner(), coder=self._make_coder(),
            index=self._make_index(), cfg=cfg, workdir=workdir,
            static_checker=self._make_static_checker(),
            unit_runner=self._make_unit_runner())

    def handle_work(self, d: Dispatch, raw: str | None = None) -> str:
        ws = self.effective_workspace()
        if not ws:
            return ("No Zephyr workspace is configured yet. Run "
                    "sync with your workspace path first.")
        from .firmware.workspace import workspace_kind

        if workspace_kind(ws) != "zephyr":
            return (f"This chat's workspace ({ws}) is not a Zephyr "
                    f"workspace, so the firmware pipeline doesn't apply "
                    f"— toolsets and learning still do. Bind a Zephyr "
                    f"workspace for firmware work.")
        coder = self._make_coder()
        if coder is None:
            return self._NO_CODER

        # The intelligent manager (the owner's rule): the agent decides
        # what to do; RITA validates the order against synced reality,
        # states the decision, and runs the gates.
        text = (raw or d.residual or "").strip()
        order = None
        note = ""
        if self.cfg.ai_routing:
            from .firmware.interpret import interpret_request

            boards = list(self._boards_data().get("boards", {}))
            try:
                samples = [(en.id, en.path)
                           for en in self._make_index().entries][:80]
            except Exception:
                samples = []
            machine = ("Windows; native_sim is POSIX-only and cannot run "
                       "here — qemu_* boards run under the SDK's QEMU"
                       if _WINDOWS else
                       "POSIX (Linux/macOS); native_sim runs natively")
            order, note = interpret_request(coder.complete, text,
                                            boards=boards, samples=samples,
                                            machine=machine)
        if order is not None and order.action == "chat":
            return self.handle_chat(text)

        if order is not None:
            board = order.board or d.entities.board or self._default_board()
            goal = order.goal or text
            terms = [t for t in goal.split() if len(t) > 2]
            modify_from = None
            if order.action == "modify":
                entry = next(
                    (en for en in self._make_index().entries
                     if en.id == order.sample or order.sample in en.id
                     or order.sample in en.path), None)
                if entry is not None:
                    modify_from = Path(ws) / entry.path
            pipeline = self._build_pipeline(ws)
            self.manager.submit(
                goal, lambda ctl: pipeline.run(
                    goal=goal, board=board, terms=terms,
                    scaffold=order.action == "scaffold",
                    modify_from=modify_from, ctl=ctl))
            what = order.action + (f" {order.sample}" if order.sample else "")
            why = f" — {order.why}" if order.why else ""
            extra = (" I'll work on a copy; your tree stays untouched."
                     if modify_from is not None else "")
            return (f"The agent read that as: {what} for {board}{why}."
                    f"{extra} Say pause or stop any time; I'll report "
                    f"when the gates finish.")

        # Grammar fallback: no manager (ai_routing off) or its order
        # didn't validate — say so, then route the old way.
        e = d.entities
        board = e.board or self._default_board()
        terms = [t for t in (e.sample, e.peripheral) if t] \
            or [t for t in d.residual.split() if len(t) > 2]
        goal = d.residual or "firmware work"
        pipeline = self._build_pipeline(ws)
        self.manager.submit(
            goal, lambda ctl: pipeline.run(goal=goal, board=board,
                                           terms=terms,
                                           scaffold=d.verb == "scaffold",
                                           ctl=ctl))
        verb = d.verb or "work"
        prefix = ""
        if self.cfg.ai_routing and note and note != "ok":
            prefix = (f"(the routing manager's answer didn't validate — "
                      f"{note[:140]} — using grammar routing) ")
        return (f"{prefix}Started {verb} for {board}. Say pause or stop "
                f"any time; I'll report when the gates finish.")

    def _boards_data(self) -> dict:
        """Synced boards.json when present, else scanned from the workspace —
        Zephyr facts always come from the actual install, never baked in."""
        if "boards_data" not in self._facts:
            import json

            from .home import boards_json_path

            ws = self.effective_workspace()
            p = boards_json_path()
            if ws and ws != self.cfg.workspace:
                # Chat-bound workspace: its facts, not the global sync.
                from .firmware.workspace import workspace_kind

                if workspace_kind(ws) == "zephyr":
                    from .firmware.boards import build_boards_json

                    self._facts["boards_data"] = build_boards_json(ws)
                else:
                    self._facts["boards_data"] = {"boards": {}}
            elif p.exists():
                self._facts["boards_data"] = json.loads(p.read_text())
            elif self.cfg.workspace:
                from .firmware.boards import build_boards_json

                self._facts["boards_data"] = build_boards_json(self.cfg.workspace)
            else:
                self._facts["boards_data"] = {"boards": {}}
        return self._facts["boards_data"]

    # --- self-setup: RITA installs her own missing pieces --------------------

    def _setup_steps(self):
        """(name, fix) for every FIXABLE gap. Detection at call time so
        tests and reruns see current state. The firmware machinery
        (CERBERUS, Unity, toolchain, board sync) queues only for Zephyr
        workspaces — Zephyr is a flavor RITA detects, not an assumption."""
        from .firmware import cerberus_setup as cs
        from .firmware import toolchain as tc
        from .firmware import unity as un
        from .firmware.workspace import workspace_kind
        from .home import mcp_config_path

        steps = []
        if not self.registry.discover():
            from .modules.install import dev_install

            steps.append(("modules", lambda: (
                f"registered {len(dev_install())} capability modules")))
        ws = self.effective_workspace()
        zephyr = bool(ws) and workspace_kind(ws) == "zephyr"
        if zephyr and cs.detect_cerberus() is None:
            steps.append(("CERBERUS", lambda: cs.install_cerberus().detail))
        if zephyr and un.detect_unity() is None:
            steps.append(("Unity", lambda: un.install_unity().detail))
        if zephyr and tc.detect_arm_gcc() is None \
                and tc.zephyr_gcc_version() is not None:
            steps.append(("ARM toolchain",
                          lambda: tc.install_arm_gcc().detail))
        if zephyr and self.cfg.workspace and not mcp_config_path().exists():
            from .firmware.sync import sync_workspace

            steps.append(("workspace sync", lambda: (
                f"synced {sync_workspace(self.cfg.workspace).boards} boards")))
        return steps

    def _human_setup_items(self):
        items = []
        if not self.cfg.workspace:
            items.append("pick your Zephyr workspace on the Workspace page")
        if not self.cfg.coder_command and self._coder is None:
            items.append("enter your coding agent's command on the "
                         "Settings page (then log it in from there)")
        return items

    def auto_setup(self) -> str:
        """OpenClaw rule: launching RITA IS the setup. Everything fixable
        is fixed by RITA herself, as a task; only genuinely-human steps
        are handed back, named."""
        steps = self._setup_steps()
        human = self._human_setup_items()
        if not steps:
            msg = "Everything I can set up is already in place — I'm ready."
            if human:
                msg += " Still needs you: " + "; ".join(human) + "."
            return msg

        def run(ctl=None):
            lines = []
            for name, fix in steps:
                try:
                    lines.append(f"{name}: {fix()}")
                except Exception as exc:
                    lines.append(f"{name} FAILED: {type(exc).__name__}: {exc}")
                if ctl is not None:
                    ctl.checkpoint(f"SETUP:{name}")
            if human:
                lines.append("Still needs you: " + "; ".join(human) + ".")
            return "Setup finished.\n" + "\n".join(lines)

        self.manager.submit("setup", run)
        names = ", ".join(n for n, _ in steps)
        msg = (f"Setting myself up — missing: {names}. Downloads may take "
               f"a while; I'll report as I go.")
        if human:
            msg += " Meanwhile: " + "; ".join(human) + "."
        return msg

    # --- per-chat work areas -------------------------------------------------

    # The chat this supervisor is acting FOR right now. The GUI's tabs
    # set it per interaction; None falls back to the persisted current-
    # chat marker, so the single-chat flow keeps working.
    active_chat: str | None = None

    def effective_workspace(self) -> str | None:
        """The active chat's bound workspace, else the global default —
        each chat can have its own repo/area; unbound chats keep today's
        single-workspace behavior."""
        from .learning import chats

        return chats.bound_workspace(self.active_chat) or self.cfg.workspace

    def bind_chat(self, spec: str) -> str:
        from .learning import chats

        path, msg = chats.bind(spec, self.active_chat)
        if path is not None:
            self._facts.clear()               # workspace facts changed
        return msg

    def new_chat(self) -> str:
        from .learning import chats

        cid = chats.new_chat()
        self.active_chat = cid
        self._facts.clear()
        return (f"Started {cid}. It uses the global workspace until you "
                f"bind one — say 'use <path or git url> for this chat'.")

    # --- system discovery: the agent investigates, RITA validates ------------

    def _discovery_gaps(self):
        """(fact name, question, schema, validate) for everything RITA's
        own detection can't see on this machine right now."""
        from pathlib import Path as _P

        from .firmware import toolchain as tc
        from .firmware import workspace as wsmod

        gaps = []
        ws = self.effective_workspace()
        if not ws:
            return gaps
        if wsmod.workspace_kind(ws) == "zephyr":
            sdk = wsmod.read_sdk_info()
            if sdk and tc.zephyr_gcc_version() is None:
                def validate_gcc(claim):
                    p = str(claim.get("path", ""))
                    if not _P(p).is_file():
                        return None
                    ver, _raw = tc._gcc_version_raw(p)
                    if ver is None:
                        return None
                    return f"{p} runs and reports gcc {ver[0]}.{ver[1]}"

                gaps.append((
                    "sdk-arm-gcc",
                    f"Find the arm-zephyr-eabi cross-compiler executable "
                    f"inside the Zephyr SDK at {sdk['path']} on this "
                    f"machine. Its layout may be newer than you expect — "
                    f"look at the actual directories, and search online "
                    f"for this SDK version's layout if needed.",
                    '{"path": "<absolute path to arm-zephyr-eabi-gcc>"}',
                    validate_gcc))
            if tc.detect_qemu() is None:
                def validate_qemu(claim):
                    p = _P(str(claim.get("path", "")))
                    if p.is_file() and p.name.startswith("qemu-system-arm"):
                        return f"{p} exists"
                    return None

                gaps.append((
                    "qemu-system-arm",
                    "Find the qemu-system-arm executable on this machine "
                    "(the Zephyr SDK ships one in its host tools).",
                    '{"path": "<absolute path>"}', validate_qemu))
        else:
            def validate_cmds(claim):
                import shutil as _sh

                build = claim.get("build")
                if not isinstance(build, list) or not build:
                    return None
                exe = str(build[0])
                if _sh.which(exe) is None and not _P(exe).exists():
                    return None
                return f"build tool {exe} resolves on this machine"

            gaps.append((
                f"workspace-{_P(ws).name}-commands",
                f"Inspect the repository at {ws} and determine how it is "
                f"built and tested — read its build files, and search "
                f"online for the build system's documentation if needed.",
                '{"build": ["<argv>"], "test": ["<argv>"]}', validate_cmds))
        return gaps

    def discover_system(self) -> str:
        """The sync learning pass: the agent (which may read this machine
        and search online) investigates each gap; RITA validates every
        claim herself and remembers only what checked out."""
        from .learning import facts
        from .learning.investigate import investigate

        coder = self._make_coder()
        if coder is None:
            return ("No coding agent is configured, so I can't "
                    "investigate this machine — set one on the Settings "
                    "page and sync again.")
        gaps = self._discovery_gaps()
        if not gaps:
            return ("Nothing to investigate — my own detection covers "
                    "this system.")
        lines = []
        for name, question, schema, validate in gaps:
            finding, note = investigate(coder.complete, question,
                                        schema=schema, validate=validate)
            if finding is not None:
                facts.save_fact(name, finding.answer, evidence=note)
                lines.append(f"learned {name}: {note}")
            else:
                lines.append(f"{name}: {note}")
        return "System discovery finished.\n" + "\n".join(lines)

    def _learn(self, question: str) -> str:
        """Ask the coding agent a Zephyr question ONCE; remember the
        answer as markdown and serve it deterministically ever after."""
        from .firmware import knowledge

        coder = self._make_coder()
        answer = coder.complete(
            "Answer this Zephyr development question concisely and "
            "concretely (name the Kconfig options, APIs, and commands): "
            + question)
        path = knowledge.save_learned(question, answer)
        return (f"I asked the coding agent and I'll remember it "
                f"(saved to {Path(path).name}): {answer.strip()[:400]}")

    # --- projects: hand off -> plan (data) -> RITA executes -------------------

    def _make_item_pipeline(self, project_id: str):
        from .firmware.pipeline import IteratePipeline

        def factory(item_id: str) -> IteratePipeline:
            return IteratePipeline(
                runner=self._make_runner(), coder=self._make_coder(),
                index=self._make_index(), cfg=self.cfg,
                workdir=self.workdir / project_id / item_id,
                static_checker=self._make_static_checker(),
                unit_runner=self._make_unit_runner())

        return factory

    def hand_off(self, goal: str) -> str:
        """Hand RITA a task: she figures it out herself, or gets an AI to
        write the plan — then SHE completes the items through her gates."""
        from .projects.model import ProjectStore
        from .projects.planner import PlanError, plan_project, quick_plan
        from .projects.runner import run_project

        if not self.cfg.workspace:
            return ("No Zephyr workspace is configured yet — point me at one "
                    "on the Workspace page first.")
        if self._make_coder() is None:
            return self._NO_CODER
        store = ProjectStore()
        project = quick_plan(goal, self.shell.vocab, store)
        if project is None:
            try:
                project = plan_project(goal, self._make_coder().complete,
                                       self.shell.vocab, store)
            except PlanError as exc:
                return (f"I couldn't get a usable plan for that: {exc}. "
                        f"Rephrase it, or break it up for me.")
        store.save(project)

        factory = self._make_item_pipeline(project.id)
        self.manager.submit(
            f"project: {project.goal[:40]}",
            lambda ctl: run_project(project, store,
                                    pipeline_factory=factory,
                                    chat=self.handle_chat,
                                    vocab=self.shell.vocab, ctl=ctl))
        titles = "; ".join(i.title for i in project.items[:6])
        flagged = sum(1 for i in project.items if i.status == "needs_user")
        note = (f" {flagged} item(s) need you — they're outside what I can "
                f"do myself." if flagged else "")
        return (f"Project {project.id}: {len(project.items)} items — "
                f"{titles}. I'll work through them and report.{note}")

    def _project_status(self) -> str | None:
        from .projects.model import ProjectStore

        projects = ProjectStore().all()
        if not projects:
            return "No projects yet — hand one off with 'start a project: …'."
        p = projects[-1]
        counts: dict[str, int] = {}
        for i in p.items:
            counts[i.status] = counts.get(i.status, 0) + 1
        done = counts.get("done", 0) + counts.get("answered", 0)
        parts = [f"{done} of {len(p.items)} items done"]
        for status in ("running", "blocked", "needs_user", "pending", "stopped"):
            if counts.get(status):
                parts.append(f"{counts[status]} {status.replace('_', ' ')}")
        return f"Project {p.id} ({p.goal[:40]}): " + ", ".join(parts) + "."

    def handle_chat(self, text: str) -> str:
        from .routing.model import normalize

        norm = text.lower()
        # Self-check: RITA is GUI-only, so she must be able to report her
        # own setup without a terminal. A report, never a task.
        from .routing import grammar as _grammar

        if _grammar.is_setup(normalize(text)):
            return self.auto_setup()

        if _grammar.is_status(normalize(text)):
            return self._live_status()

        if _grammar.is_diagnostic(normalize(text)):
            from .diagnostics import report

            return report(self.cfg, deep=bool(self.cfg.coder_command))

        # Raw-lowered matching for phrases carrying paths/names that
        # normalization would mangle (slashes, hyphens, URLs).
        low = text.strip().lower()
        req = _grammar.toolset_request(low)
        if req:
            return self._handle_toolset(req)
        if _grammar.is_learning_question(normalize(text)):
            return self._learning_report()
        target = _grammar.chat_bind_target(text.strip())
        if target:
            return self.bind_chat(target)
        if _grammar.CHAT_NEW.match(low):
            return self.new_chat()

        data = self._boards_data()

        if "project" in norm:
            status = self._project_status()
            if status:
                return status

        # Questions about a known board answer from its real metadata.
        board = self.shell.vocab.find_board(norm)
        if board and board in data.get("boards", {}):
            b = data["boards"][board]
            supported = ", ".join(b.get("supported", [])[:8]) or "unknown peripherals"
            conn = b.get("connected")
            attached = (f" It is connected on {conn['serial']}." if conn and
                        conn.get("serial") else "")
            return (f"{board} is a {b.get('vendor', 'unknown-vendor')} "
                    f"{b.get('arch', '?')} board, twister platform "
                    f"{b.get('twister_platform', board)}, supporting "
                    f"{supported}.{attached}")

        # How-do-I questions answer from the shipped knowledge pack
        # (deterministic keyword match; full topics via MCP zephyr_howto).
        if norm.startswith(("how do i", "how can i", "how do you", "how to")):
            from .firmware import knowledge

            summary = knowledge.summary_for(norm.split())
            if summary:
                return summary
            # Unknown: ask the coding agent ONCE and remember the answer.
            if self._make_coder() is not None:
                question = text.strip()
                self.manager.submit(f"learn: {norm[:40]}",
                                    lambda ctl: self._learn(question))
                return ("I don't know that one yet — I'm asking the coding "
                        "agent now and I'll remember the answer.")
            return ("I don't know that one, and no coding agent is "
                    "configured to ask — set one on the Settings page.")

        # Zephyr version questions answer from the install's VERSION file.
        if "zephyr" in norm and "version" in norm:
            version = data.get("zephyr_version")
            if version is None and self.cfg.workspace:
                from .firmware.workspace import read_workspace_info

                version = read_workspace_info(self.cfg.workspace)["zephyr_version"]
            if version:
                return f"This workspace is on Zephyr {version}."
            return ("I can't find a zephyr/VERSION file in the workspace, "
                    "so I won't guess the version.")

        return ("We can chat, but nothing in that matched a work command. "
                "Name a board or sample to put me to work.")

    def _live_status(self) -> str:
        """What's happening RIGHT NOW — the owner must never have to
        press Pause to find out whether a task is alive."""
        lines = []
        for tid in self.manager.tasks():
            rep = self.manager.report(tid)
            if rep.state in ("RUNNING", "PAUSING", "PAUSED", "STOPPING"):
                done = ", ".join(rep.completed_stages) or "just started"
                lines.append(f"{rep.name} ({tid}): "
                             f"{rep.state.lower()} — done so far: {done}")
        if lines:
            return "Yes — still on it:\n" + "\n".join(lines)
        msg = "Nothing is running right now."
        status = self._project_status()
        if status and "No projects yet" not in status:
            msg += " " + status
        return msg

    def _handle_toolset(self, req) -> str:
        from .learning import toolsets

        kind, arg = req
        if kind == "list":
            items = toolsets.list_toolsets()
            if not items:
                return ("No toolsets yet — say 'make a toolset that …' "
                        "and I'll have the coding agent build one, "
                        "validate it, and keep it for reuse.")
            return "Toolsets I keep:\n" + "\n".join(
                f"{t.name}: {t.purpose}" for t in items)
        if kind == "run":
            name, args = arg
            ok, output = toolsets.run_toolset(
                name, tuple(a for a in (args or "").split() if a))
            return output
        coder = self._make_coder()
        if coder is None:
            return self._NO_CODER
        request = arg

        def build(ctl=None):
            _info, detail = toolsets.create_toolset(coder.complete, request)
            return detail

        self.manager.submit(f"toolset: {request[:40]}", build)
        return ("I'm having the coding agent build that toolset now — "
                "I'll validate it with a real run before keeping it.")

    def _learning_report(self) -> str:
        from .firmware.knowledge import _learned
        from .learning import facts

        text = facts.describe()
        learned = _learned()
        if learned:
            titles = ", ".join(v["title"] for v in learned.values())
            text += f"\nLearned answers I keep: {titles}"
        from .learning import toolsets

        items = toolsets.list_toolsets()
        if items:
            text += "\nToolsets: " + ", ".join(t.name for t in items)
        return text

    def task_summary(self, tid: str) -> str:
        from .firmware.pipeline import describe
        from .projects.runner import ProjectResult, describe_project

        rep = self.manager.report(tid)
        if rep.state == "DONE" and rep.result is not None:
            if isinstance(rep.result, str):        # setup / learn tasks
                return rep.result
            if isinstance(rep.result, ProjectResult):
                return describe_project(rep.result)
            return describe(rep.result)
        if rep.state == "STOPPED":
            done = ", ".join(rep.completed_stages) or "nothing"
            return f"Stopped. Completed before the stop: {done}."
        if rep.state == "FAILED":
            # Exhaustion and failure are REPORTED outcomes, never hidden —
            # the exception is the report.
            return f"Task {tid} failed: {rep.error or 'unknown error'}"
        return f"Task {tid} is {rep.state.lower()}."

    # --- the talk loop -------------------------------------------------------

    def make_voice_loop(self, *, push_to_talk: bool = False,
                        seconds: float = 5.0, model: str = "base",
                        on_screen=print):  # pragma: no cover - real audio path
        from .voice.loop import VoiceLoop
        from .voice.stt import WhisperSTT
        from .voice.tts import Pyttsx3TTS

        if self.speaker is None:
            self.speaker = PausableSpeaker(Pyttsx3TTS())
            self.shell.control = make_control_handler(self.manager, self.speaker)
        if push_to_talk:
            from .voice.mic import PushToTalkRecorder
            from .voice.trigger import EnterKeyTrigger

            return VoiceLoop(PushToTalkRecorder(), WhisperSTT(model=model),
                             self.speaker, handler=lambda h: "",
                             trigger=EnterKeyTrigger(),
                             utterance_handler=self.shell.handle,
                             on_screen=on_screen)
        from .voice.mic import MicRecorder

        return VoiceLoop(MicRecorder(seconds=seconds), WhisperSTT(model=model),
                         self.speaker, handler=lambda h: "",
                         utterance_handler=self.shell.handle,
                         on_screen=on_screen)
