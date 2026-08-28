"""The GUI's brain-stem: headless presenter over the Supervisor.

The window binds plain callables (`on_user`, `on_reply`, `on_screen`,
`on_task`, `on_status`) to Qt signals; everything else — quote stripping,
routing, the speech/screen split, pause/stop semantics, task-completion
announcements, workspace sync — happens here, testable without a display.
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import save_rita_config
from ..firmware.sync import SyncResult, sync_workspace
from ..routing.vocabulary import Vocabulary
from ..supervisor import Supervisor
from ..ui.channels import split_response

_QUOTES = "\"'“”‘’"


@dataclass(frozen=True)
class TaskSnapshot:
    id: str
    name: str
    state: str
    outcome: str | None = None       # PipelineReport outcome when DONE
    completed_stages: tuple[str, ...] = ()


@dataclass(frozen=True)
class StatusInfo:
    workspace: str | None
    zephyr_version: str | None
    modules: int
    coder_cli: bool                  # coding agent configured + resolvable
    sdk_version: str | None = None


def _noop(*_a, **_k) -> None:
    return None


def strip_quotes(text: str) -> str:
    """The user quotes commands; RITA routes the contents."""
    return text.strip().strip(_QUOTES).strip()


class GuiPresenter:
    def __init__(self, supervisor: Supervisor,
                 poll_interval: float = 0.05,
                 voice_backends=None) -> None:
        self.sup = supervisor
        self.on_user = _noop      # (text) echoed user entry, unquoted
        self.on_reply = _noop     # (speech) speech-channel text
        self.on_screen = _noop    # (text) screen-channel artifacts
        self.on_task = _noop      # (TaskSnapshot) state transitions
        self.on_status = _noop    # (StatusInfo)
        self._poll = poll_interval
        self._seen_states: dict[str, str] = {}
        self._closing = threading.Event()
        # Voice: injectable () -> (recorder, stt, tts|None); real ones lazy.
        self._voice_backends = voice_backends or self._default_voice_backends
        self._voice_stop = threading.Event()
        self._voice_thread: threading.Thread | None = None
        threading.Thread(target=self._watch_tasks, daemon=True,
                         name="gui-task-watch").start()

    # --- input ---------------------------------------------------------------

    def submit_text(self, text: str) -> None:
        clean = strip_quotes(text)
        if not clean:
            return
        self.on_user(clean)
        threading.Thread(target=self._handle, args=(clean,), daemon=True,
                         name="gui-handle").start()

    def _handle(self, clean: str) -> None:
        said = self.sup.shell.handle_typed(clean)
        self._emit_reply(said)

    def _emit_reply(self, said: str) -> None:
        if not said:
            return
        reply = split_response(said)
        self.on_reply(reply.speech)
        if reply.screen.strip() != reply.speech.strip():
            self.on_screen(reply.screen)
        if self.sup.speaker is not None:
            self.sup.speaker.say(reply.speech)

    # --- the two persistent buttons (Fix 4) ----------------------------------

    def _control(self, word: str) -> None:
        from ..routing.model import Utterance
        from ..routing.router import route

        d = route(Utterance.from_text(word), self.sup.shell.vocab,
                  self.sup.cfg.assistant_name)
        said = self.sup.shell.dispatch(d)
        self._emit_reply(said)

    def pause(self) -> None:
        self._control("pause")

    def resume(self) -> None:
        self._control("resume")

    def stop(self) -> None:
        self._control("stop")

    # --- voice: the microphone lives in the app, not a CLI -------------------

    def _default_voice_backends(self):
        # Probe deps EAGERLY so the failure lands at enable time ("Voice
        # isn't available: …"), never later from inside the listen thread.
        import importlib.util

        missing = [name for name in ("sounddevice", "faster_whisper")
                   if importlib.util.find_spec(name) is None]
        if missing:
            raise ImportError(
                "missing voice packages: " + ", ".join(missing)
                + " (reinstall with the Voice component)")
        from ..voice.mic import MicRecorder
        from ..voice.stt import WhisperSTT
        from ..voice.tts import Pyttsx3TTS

        try:
            tts = Pyttsx3TTS()
        except Exception:
            tts = None                 # listening still works, replies on screen
        return MicRecorder(seconds=5.0), WhisperSTT(model="base"), tts

    def start_voice(self) -> bool:
        """Begin wake-word listening on a background thread. Honest about
        unavailability: a missing backend is reported by name, never silent."""
        if self.voice_active:
            return True
        try:
            recorder, stt, tts = self._voice_backends()
        except Exception as exc:
            self._emit_reply(f"Voice isn't available: {exc}. Install the "
                             f"Voice component, then turn voice on again.")
            return False
        if tts is not None and self.sup.speaker is None:
            from ..core.tasks import make_control_handler
            from ..voice.tts import PausableSpeaker

            self.sup.speaker = PausableSpeaker(tts)
            self.sup.shell.control = make_control_handler(self.sup.manager,
                                                          self.sup.speaker)
        self._voice_stop.clear()
        self._voice_thread = threading.Thread(
            target=self._listen, args=(recorder, stt), daemon=True,
            name="gui-voice-listen")
        self._voice_thread.start()
        return True

    def stop_voice(self) -> None:
        self._voice_stop.set()

    @property
    def voice_active(self) -> bool:
        return self._voice_thread is not None and self._voice_thread.is_alive() \
            and not self._voice_stop.is_set()

    def _listen(self, recorder, stt) -> None:
        from ..voice.loop import _STOP_PHRASES
        from ..voice.stt import to_utterance

        while not self._voice_stop.is_set():
            try:
                wav = recorder.record()
                utt = to_utterance(stt, wav)
            except Exception as exc:
                self._emit_reply(f"Voice stopped: {exc}")
                break
            if self._voice_stop.is_set():
                break
            heard = utt.text.strip()
            if not heard:
                self._voice_stop.wait(0.05)
                continue
            if heard.lower().strip(" .!?") in _STOP_PHRASES:
                # Back to sleep; the mic keeps waiting for the wake word.
                self.sup.shell.awake = not self.sup.shell.require_wake
                self.on_user(f"🎤 {heard}")
                self._emit_reply("Going quiet — say my name when you need me.")
                continue
            said = self.sup.shell.handle(utt)
            if said:                    # asleep/ignored turns leave no trace
                self.on_user(f"🎤 {heard}")
                self._emit_reply(said)
            else:
                self._voice_stop.wait(0.05)

    # --- task announcements --------------------------------------------------

    def _watch_tasks(self) -> None:
        while not self._closing.wait(self._poll):
            for tid in self.sup.manager.tasks():
                rep = self.sup.manager.report(tid)
                if self._seen_states.get(tid) == rep.state:
                    continue
                self._seen_states[tid] = rep.state
                outcome = getattr(rep.result, "outcome", None)
                self.on_task(TaskSnapshot(
                    id=rep.id, name=rep.name, state=rep.state, outcome=outcome,
                    completed_stages=rep.completed_stages))
                if rep.state in ("DONE", "STOPPED", "FAILED"):
                    self._announce_finished(tid, rep)

    def _announce_finished(self, tid: str, rep) -> None:
        self._emit_reply(self.sup.task_summary(tid))
        result = rep.result
        if result is not None and getattr(result, "stages", None):
            lines = [f"[{s.stage}] {s.outcome}: {s.detail}" for s in result.stages]
            for stage in result.stages:
                for f in stage.failures:
                    lines.append(f.describe())
            self.on_screen("\n".join(lines))

    # --- workspace + status --------------------------------------------------

    def sync(self, path: str, hw_map: str | None = None) -> SyncResult:
        result = sync_workspace(path, hw_map=hw_map)
        self.sup.cfg.workspace = path
        if hw_map:
            self.sup.cfg.hardware_map = hw_map
        save_rita_config(self.sup.cfg, self.sup.config_path)
        self.sup._facts.clear()                       # facts changed
        self.sup.shell.vocab = Vocabulary.load()      # synced boards feed routing
        self.on_status(self.status())
        return result

    def maybe_auto_setup(self) -> None:
        """OpenClaw rule: launching RITA IS the setup. When the toggle is
        on and fixable gaps exist, RITA announces them and fixes them
        herself — the user does nothing."""
        if not self.sup.cfg.auto_setup:
            return
        try:
            gaps = self.sup._setup_steps()
        except Exception:
            return
        if gaps:
            self._emit_reply(self.sup.auto_setup())

    def login_coder(self) -> None:
        """One click: open the agent's own login window and say what to
        do next — the user never touches a terminal."""
        from ..firmware.coder import launch_login

        self._emit_reply(launch_login(self.sup.cfg))

    def _coder_available(self) -> bool:
        """The seam is honest: available only when a command is configured
        AND its executable resolves (PATH or a real file)."""
        cmd = self.sup.cfg.coder_command
        if self.sup._coder is not None:
            return True                       # injected worker (tests/modules)
        if not cmd:
            return False
        from ..firmware.static_check import split_command

        argv = split_command(cmd)
        exe = argv[0] if argv else ""
        return bool(exe) and (shutil.which(exe) is not None
                              or Path(exe).exists())

    def status(self) -> StatusInfo:
        from ..firmware.workspace import read_sdk_info, read_workspace_info

        zephyr_version = None
        if self.sup.cfg.workspace and Path(self.sup.cfg.workspace).exists():
            zephyr_version = read_workspace_info(
                self.sup.cfg.workspace)["zephyr_version"]
        sdk = read_sdk_info()
        return StatusInfo(
            workspace=self.sup.cfg.workspace,
            zephyr_version=zephyr_version,
            modules=len(self.sup.registry.discover()),
            coder_cli=self._coder_available(),
            sdk_version=sdk["version"] if sdk else None)

    def close(self) -> None:
        self._voice_stop.set()
        self._closing.set()
