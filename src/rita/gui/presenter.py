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
        # Tabbed chats: every event also arrives tagged with the chat
        # that owns it — (chat_id, kind, text), kind in user/reply/screen.
        self.on_chat_event = _noop
        self.on_voice = _noop     # (bool) microphone state, for mic buttons
        self._task_chats: dict[str, str] = {}   # task id -> owning chat
        self._poll = poll_interval
        self._seen_states: dict[str, str] = {}
        self._closing = threading.Event()
        # Voice: injectable () -> (recorder, stt, tts|None); real ones lazy.
        self._voice_backends = voice_backends or self._default_voice_backends
        self._voice_stop = threading.Event()
        self._voice_thread: threading.Thread | None = None
        threading.Thread(target=self._watch_tasks, daemon=True,
                         name="gui-task-watch").start()
        # Agent narration ("asking the coding agent… / replied in Ns")
        # lands in the active chat's screen pane.
        supervisor.on_activity = self._activity

    def _activity(self, msg: str) -> None:
        try:
            self.on_screen(msg)
            self.on_chat_event(self._current_chat(), "screen", msg)
        except Exception:
            pass

    # --- input ---------------------------------------------------------------

    def _current_chat(self) -> str:
        from ..learning import chats

        return self.sup.active_chat or chats.current_chat()

    def set_active_chat(self, chat_id: str) -> None:
        """The GUI's tabs call this per interaction; the persisted
        current-chat marker follows so a restart lands where you were."""
        from ..learning import chats

        if self.sup.active_chat != chat_id:
            self.sup.active_chat = chat_id
            chats.set_current(chat_id)
            self.sup._facts.clear()

    def submit_text(self, text: str) -> None:
        clean = strip_quotes(text)
        if not clean:
            return
        chat = self._current_chat()
        self.on_user(clean)
        self.on_chat_event(chat, "user", clean)
        threading.Thread(target=self._handle, args=(clean, chat),
                         daemon=True, name="gui-handle").start()

    def _handle(self, clean: str, chat: str | None = None) -> None:
        if chat is not None:
            # Act FOR the chat that sent this, even if the user has
            # already clicked to another tab.
            self.sup.active_chat = chat
        before = set(self.sup.manager.tasks())
        said = self.sup.shell.handle_typed(clean)
        for tid in set(self.sup.manager.tasks()) - before:
            self._task_chats[tid] = chat or self._current_chat()
        self._emit_reply(said, chat=chat)

    def _emit_reply(self, said: str, chat: str | None = None) -> None:
        if not said:
            return
        chat = chat or self._current_chat()
        reply = split_response(said)
        self.on_reply(reply.speech)
        self.on_chat_event(chat, "reply", reply.speech)
        if reply.screen.strip() != reply.speech.strip():
            self.on_screen(reply.screen)
            self.on_chat_event(chat, "screen", reply.screen)
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
        return (MicRecorder(seconds=5.0,
                            device=self.sup.cfg.voice_input_device),
                WhisperSTT(model="base"), tts)

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
        self.on_voice(True)
        return True

    def stop_voice(self) -> None:
        self._voice_stop.set()
        self.on_voice(False)

    def restart_voice(self) -> bool:
        """Apply a changed microphone/settings: stop, then start fresh."""
        self.stop_voice()
        t = self._voice_thread
        if t is not None:
            t.join(timeout=0.2)        # best effort; recorder may be mid-window
        self._voice_thread = None
        return self.start_voice()

    @property
    def voice_active(self) -> bool:
        return self._voice_thread is not None and self._voice_thread.is_alive() \
            and not self._voice_stop.is_set()

    # Seconds of silence required after RITA speaks before the mic
    # re-arms — room echo of her own voice must fully decay.
    _ECHO_TAIL = 0.4

    def _speaker_busy(self) -> bool:
        sp = self.sup.speaker
        if sp is None:
            return False
        busy = getattr(sp, "busy", False)
        quiet = getattr(sp, "quiet_for", lambda: float("inf"))()
        return bool(busy) or quiet < self._ECHO_TAIL

    def _record(self, recorder):
        """One recording window; the stop event is passed to recorders
        that accept it, so mic-off takes effect immediately."""
        try:
            return recorder.record(stop=self._voice_stop)
        except TypeError:
            return recorder.record()

    def _listen(self, recorder, stt) -> None:
        import time as _time

        from ..voice.loop import _STOP_PHRASES
        from ..voice.stt import to_utterance

        from ..voice.mic import SILENCE_RMS, rms_level

        while not self._voice_stop.is_set():
            try:
                # HALF-DUPLEX: while RITA speaks (plus the echo tail)
                # the microphone is deaf — she must never hear her own
                # voice and type it back.
                if self._speaker_busy():
                    self._voice_stop.wait(0.05)
                    continue
                window_start = _time.monotonic()
                wav = self._record(recorder)
                sp = self.sup.speaker
                if sp is not None and getattr(sp, "spoke_after",
                                              lambda t: False)(
                        window_start - self._ECHO_TAIL):
                    continue        # she talked over this window: discard
                # Silence gate: Whisper hallucinates words on room
                # noise — a quiet recording never reaches it.
                level = rms_level(wav)
                if level is not None and level < SILENCE_RMS:
                    self._voice_stop.wait(0.05)
                    continue
                utt = to_utterance(stt, wav)
            except Exception as exc:
                self._emit_reply(f"Voice stopped: {exc}")
                self.on_voice(False)
                break
            if self._voice_stop.is_set():
                break
            heard = utt.text.strip()
            if not heard:
                self._voice_stop.wait(0.05)
                continue
            chat = self._current_chat()
            if heard.lower().strip(" .!?") in _STOP_PHRASES:
                self.on_user(f"🎤 {heard}")
                self.on_chat_event(chat, "user", f"🎤 {heard}")
                if self.sup.shell.require_wake:
                    # Wake-word mode: back to sleep, mic keeps waiting.
                    self.sup.shell.awake = False
                    self._emit_reply("Going quiet — say my name when you "
                                     "need me.", chat=chat)
                    continue
                # Mic-button mode: the stop phrase turns the mic OFF.
                self._emit_reply("Microphone off.", chat=chat)
                self.stop_voice()
                break
            said = self.sup.shell.handle(utt)
            if said:                    # asleep/ignored turns leave no trace
                self.on_user(f"🎤 {heard}")
                self.on_chat_event(chat, "user", f"🎤 {heard}")
                self._emit_reply(said, chat=chat)
            else:
                self._voice_stop.wait(0.05)

    # --- task announcements --------------------------------------------------

    def _watch_tasks(self) -> None:
        seen_stages: dict[str, int] = {}
        while not self._closing.wait(self._poll):
            for tid in self.sup.manager.tasks():
                rep = self.sup.manager.report(tid)
                # Stage-by-stage progress streams to the owning chat's
                # screen pane — the owner pressed Pause once just to
                # prove a task was alive. Never again.
                n = len(rep.completed_stages)
                if n > seen_stages.get(tid, 0):
                    fresh = rep.completed_stages[seen_stages.get(tid, 0):]
                    seen_stages[tid] = n
                    chat = self._task_chats.get(tid) or self._current_chat()
                    for stage in fresh:
                        line = f"▸ {rep.name}: {stage} done"
                        self.on_screen(line)
                        self.on_chat_event(chat, "screen", line)
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
        # The announcement lands in the chat that STARTED the task,
        # not whichever tab the user is looking at now.
        chat = self._task_chats.get(tid)
        self._emit_reply(self.sup.task_summary(tid), chat=chat)
        result = rep.result
        if result is not None and getattr(result, "stages", None):
            lines = [f"[{s.stage}] {s.outcome}: {s.detail}" for s in result.stages]
            for stage in result.stages:
                for f in stage.failures:
                    lines.append(f.describe())
            self.on_screen("\n".join(lines))
            self.on_chat_event(chat or self._current_chat(), "screen",
                               "\n".join(lines))

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
        # Syncing IS a learning pass: whatever RITA's own detection
        # can't see, the agent investigates (it may read this machine
        # and search online); RITA validates and remembers.
        try:
            if self.sup._make_coder() is not None and self.sup._discovery_gaps():
                self.sup.manager.submit(
                    "learn the system",
                    lambda ctl: self.sup.discover_system())
        except Exception:
            pass
        return result

    def sync_chat(self, chat_id: str | None = None) -> None:
        """Sync THIS chat's workspace — its bound folder, else the
        global default from Settings. Replies land in the chat like any
        other answer; safe to call from a worker thread."""
        from ..firmware.workspace import workspace_kind
        from ..learning import chats

        cid = chat_id or self._current_chat()
        bound = chats.bound_workspace(cid)
        path = bound or self.sup.cfg.workspace
        if not path:
            self._emit_reply(
                "This chat has no folder yet — bind one right above, or "
                "set a default workspace in Settings.", chat=cid)
            return
        if workspace_kind(path) != "zephyr":
            self._emit_reply(
                f"{path} isn't a Zephyr workspace — nothing to index; "
                "the coding agent works in it directly.", chat=cid)
            return
        try:
            if bound:
                # A chat-bound workspace: index it without clobbering
                # the global default other chats rely on.
                res = sync_workspace(path, hw_map=self.sup.cfg.hardware_map)
                self.sup._facts.clear()
                self.sup.shell.vocab = Vocabulary.load()
                self.on_status(self.status())
            else:
                res = self.sync(path, hw_map=self.sup.cfg.hardware_map)
            self._emit_reply(
                f"Synced {res.boards} boards and {res.entries} suites "
                f"from {path}.", chat=cid)
        except Exception as exc:
            self._emit_reply(f"Sync failed: {exc}", chat=cid)

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

    def mirror_screen(self, text: str) -> None:
        """Auxiliary output (e.g. the Modules install log) mirrored into
        the active chat's screen pane so results survive a page switch."""
        self.on_screen(text)
        self.on_chat_event(self._current_chat(), "screen", text)

    def chat_info(self, chat_id: str | None = None) -> str:
        """One line for a chat header: which chat, bound to what."""
        from ..learning import chats

        cid = chat_id or self._current_chat()
        bound = chats.bound_workspace(cid)
        return f"{cid} — {bound or 'global workspace'}"

    def new_chat(self) -> str:
        """Open a fresh chat, make it active, return its id."""
        msg = self.sup.new_chat()
        cid = self.sup.active_chat or self._current_chat()
        self._emit_reply(msg, chat=cid)
        return cid

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
