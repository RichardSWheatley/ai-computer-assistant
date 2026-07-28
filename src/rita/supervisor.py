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

from pathlib import Path

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
                 tts=None, runner=None, claude=None, index=None,
                 registry: ModuleRegistry | None = None,
                 workdir: str | Path | None = None) -> None:
        self.cfg = rita_cfg or load_rita_config(config_path)
        self.config_path = config_path
        self.manager = TaskManager()
        self.registry = registry or ModuleRegistry()
        self.speaker = PausableSpeaker(tts) if tts is not None else None
        self._runner = runner
        self._claude = claude
        self._index = index
        if workdir is None:
            from .home import rita_home

            workdir = rita_home() / "work"
        self.workdir = Path(workdir)
        self._task_seq = 0
        self._facts: dict = {}   # lazy workspace-fact cache (cleared on sync)
        self.shell = RouterShell(
            vocab or Vocabulary.load(), config_path=config_path,
            work=self.handle_work, chat=self.handle_chat,
            control=make_control_handler(self.manager, self.speaker))

    # --- capability wiring (module process when installed, seam otherwise) --

    def _make_runner(self):
        if self._runner is not None:
            return self._runner
        from .firmware.west import WestCli

        return WestCli(self.cfg.workspace)

    def _make_claude(self):
        if self._claude is not None:
            return self._claude
        from .firmware.claude import ClaudeWorkerCli
        from .home import mcp_config_path

        mcp = mcp_config_path()
        return ClaudeWorkerCli(self.cfg.workspace,
                               mcp_config=mcp if mcp.exists() else None)

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
        return HostUnity(unity_src=unity) if unity is not None else None

    def _make_index(self):
        if self._index is not None:
            return self._index
        from .firmware.index import VerificationIndex
        from .home import verification_index_path

        if verification_index_path().exists():
            return VerificationIndex.load()
        return VerificationIndex.build(self.cfg.workspace)

    # --- dispatch handlers ---------------------------------------------------

    def handle_work(self, d: Dispatch) -> str:
        if not self.cfg.workspace:
            return ("No Zephyr workspace is configured yet. Run "
                    "sync with your workspace path first.")
        from .firmware.pipeline import IteratePipeline, describe

        self._task_seq += 1
        workdir = self.workdir / f"task-{self._task_seq}"
        pipeline = IteratePipeline(
            runner=self._make_runner(), claude=self._make_claude(),
            index=self._make_index(), cfg=self.cfg, workdir=workdir,
            static_checker=self._make_static_checker(),
            unit_runner=self._make_unit_runner())
        e = d.entities
        board = e.board or "native_sim"
        terms = [t for t in (e.sample, e.peripheral) if t] \
            or [t for t in d.residual.split() if len(t) > 2]
        goal = d.residual or "firmware work"
        tid = self.manager.submit(
            goal, lambda ctl: pipeline.run(goal=goal, board=board, terms=terms,
                                           scaffold=d.verb == "scaffold",
                                           ctl=ctl))
        verb = d.verb or "work"
        return (f"Started {verb} for {board}. Say pause or stop any time; "
                f"I'll report when the gates finish.")

    def _boards_data(self) -> dict:
        """Synced boards.json when present, else scanned from the workspace —
        Zephyr facts always come from the actual install, never baked in."""
        if "boards_data" not in self._facts:
            import json

            from .home import boards_json_path

            p = boards_json_path()
            if p.exists():
                self._facts["boards_data"] = json.loads(p.read_text())
            elif self.cfg.workspace:
                from .firmware.boards import build_boards_json

                self._facts["boards_data"] = build_boards_json(self.cfg.workspace)
            else:
                self._facts["boards_data"] = {"boards": {}}
        return self._facts["boards_data"]

    def handle_chat(self, text: str) -> str:
        data = self._boards_data()
        norm = text.lower()

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

    def task_summary(self, tid: str) -> str:
        from .firmware.pipeline import describe

        rep = self.manager.report(tid)
        if rep.state == "DONE" and rep.result is not None:
            return describe(rep.result)
        if rep.state == "STOPPED":
            done = ", ".join(rep.completed_stages) or "nothing"
            return f"Stopped. Completed before the stop: {done}."
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
