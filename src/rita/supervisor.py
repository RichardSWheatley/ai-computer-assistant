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

        return ClaudeWorkerCli(self.cfg.workspace)

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
            index=self._make_index(), cfg=self.cfg, workdir=workdir)
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

    def handle_chat(self, text: str) -> str:
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
