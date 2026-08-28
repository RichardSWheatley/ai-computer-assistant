"""The conversation loop: listen -> transcribe -> route -> act -> speak back.

VoiceLoop is backend-agnostic (recorder / STT / TTS / handler are injected), so
it's fully testable with fakes. `RouterShell` is the deterministic front end
(Fix 1): wake grammar first, then grammar routing — chat is the fallback, and
the LLM never decides intent. `make_orchestrator_handler` remains for the
legacy desktop-agent path (`run` command); the router never dispatches to it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..config import load_rita_config, save_rita_config
from ..routing.model import Dispatch, Utterance
from ..routing.router import route
from ..routing.vocabulary import Vocabulary
from ..routing.wake import WakeGate
from .mic import Recorder
from .stt import SpeechToText, to_utterance
from .trigger import Trigger
from .tts import TextToSpeech

# A handler turns a transcribed request into a spoken response.
Handler = Callable[[str], str]

# Spoken phrases that end the session.
_STOP_PHRASES = {"stop listening", "goodbye", "that's all", "exit", "quit"}


def make_orchestrator_handler(assistant) -> Handler:
    """Run the spoken request as a goal and summarize the outcome for speech."""

    def handle(request: str) -> str:
        result = assistant.run(request)
        if getattr(result, "finished", False):
            did = ", ".join(s.call.tool for s in getattr(result, "steps", [])
                            if s.call.tool != "task_complete")[:200]
            msg = result.message or "Done."
            return f"Done. {msg}" + (f" I used: {did}." if did else "")
        return f"I couldn't finish that. {getattr(result, 'message', '')}".strip()

    return handle


class RouterShell:
    """Wake gate + router + handler table. The shell owns control flow.

    Handlers: `work(dispatch) -> str`, `chat(text) -> str`,
    `control(dispatch) -> str`. All optional — safe placeholder replies are
    used until the corresponding fix lands. Rename dispatches persist the new
    name (config data, not code) and re-arm the wake gate immediately.
    """

    def __init__(self, vocab: Vocabulary | None = None, *,
                 config_path: str | Path | None = None,
                 require_wake: bool = True,
                 work: Callable[[Dispatch], str] | None = None,
                 chat: Callable[[str], str] | None = None,
                 control: Callable[[Dispatch], str] | None = None,
                 project: Callable[[str], str] | None = None) -> None:
        self.vocab = vocab or Vocabulary.load()
        self.config_path = config_path
        self.cfg = load_rita_config(config_path)
        self.gate = WakeGate(self.cfg.assistant_name)
        self.require_wake = require_wake
        self.awake = not require_wake
        self.work = work
        self.chat = chat
        self.control = control
        self.project = project

    def handle(self, utt: Utterance | str) -> str:
        if isinstance(utt, str):
            utt = Utterance.from_text(utt)

        decision = self.gate.feed(utt)
        if decision.woke:
            self.awake = True
            if decision.residual is None:
                return "Yes?"
            utt = decision.residual
        elif not self.awake:
            return ""  # asleep and not addressed: stay quiet

        return self.dispatch(route(utt, self.vocab, self.cfg.assistant_name))

    def handle_typed(self, text: str) -> str:
        """Typed input (the GUI prompt): no wake word required. A leading
        greeting/name still strips off so quoted spoken-style commands
        ("Rita, build blinky") route the same as voice."""
        utt = Utterance.from_text(text)
        decision = self.gate.feed(utt)
        if decision.woke:
            if decision.residual is None:
                return "Yes?"
            utt = decision.residual
        return self.dispatch(route(utt, self.vocab, self.cfg.assistant_name))

    def dispatch(self, d: Dispatch) -> str:
        if d.kind == "rename":
            self.cfg.assistant_name = d.argument.capitalize()
            save_rita_config(self.cfg, self.config_path)
            self.gate = WakeGate(self.cfg.assistant_name)
            return f"Okay — call me {self.cfg.assistant_name} from now on."
        if d.kind == "control":
            if self.control is not None:
                return self.control(d)
            return f"Noted: {d.argument}."
        if d.kind == "project":
            if self.project is not None:
                return self.project(d.argument)
            return "Project handoff isn't wired up in this shell."
        if d.kind == "work":
            if self.work is not None:
                return self.work(d)
            what = d.verb or "work"
            target = d.entities.board or d.entities.sample or "the workspace"
            return f"I heard a {what} request for {target}, but that pipeline isn't wired up yet."
        if self.chat is not None:
            return self.chat(d.residual)
        return "I'm listening."


class VoiceLoop:
    def __init__(self, recorder: Recorder, stt: SpeechToText, tts: TextToSpeech,
                 handler: Handler, trigger: Trigger | None = None,
                 utterance_handler: Callable[[Utterance], str] | None = None,
                 on_screen: Callable[[str], None] | None = None) -> None:
        self.recorder = recorder
        self.stt = stt
        self.tts = tts
        self.handler = handler
        self.trigger = trigger  # push-to-talk / wake-word gate; None = continuous
        # When set, turns flow as timed Utterances (wake grammar needs word
        # timings); `handler` is ignored for those turns.
        self.utterance_handler = utterance_handler
        # Screen-channel sink (Fix 5): receives the FULL response; the TTS
        # path only ever gets the deterministically stripped speech channel.
        self.on_screen = on_screen

    def _speak_reply(self, said: str) -> None:
        from ..ui.channels import split_response

        reply = split_response(said)
        if self.on_screen is not None:
            self.on_screen(reply.screen)
        self.tts.speak(reply.speech)

    def converse_once(self) -> tuple[str, str]:
        """One turn: record, transcribe, handle, speak. Returns (heard, said)."""
        wav = self.recorder.record()
        if self.utterance_handler is not None:
            utt = to_utterance(self.stt, wav)
            heard = utt.text.strip()
            if not heard:
                return "", ""
            if heard.lower().strip(" .!?") in _STOP_PHRASES:
                self.tts.speak("Goodbye.")
                return heard, "Goodbye."
            said = self.utterance_handler(utt)
            if said:  # empty reply = utterance ignored (e.g. not awake)
                self._speak_reply(said)
            return heard, said
        heard = (self.stt.transcribe(wav) or "").strip()
        if not heard:
            return "", ""
        if heard.lower().strip(" .!?") in _STOP_PHRASES:
            self.tts.speak("Goodbye.")
            return heard, "Goodbye."
        said = self.handler(heard)
        self._speak_reply(said)
        return heard, said

    def is_stop(self, heard: str) -> bool:
        return heard.lower().strip(" .!?") in _STOP_PHRASES

    def run(self, greeting: str = "I'm listening.") -> None:
        self.tts.speak(greeting)
        try:
            while True:
                if self.trigger is not None and not self.trigger.wait():
                    break  # user chose to quit at the push-to-talk prompt
                heard, _ = self.converse_once()
                if heard and self.is_stop(heard):
                    break
        except KeyboardInterrupt:  # pragma: no cover
            self.tts.speak("Stopping.")


def build_voice_loop(assistant, *, push_to_talk: bool = False,
                     seconds: float = 5.0, model: str = "base",
                     use_router: bool = True) -> "VoiceLoop":
    """Assemble a VoiceLoop with the real backends, lazily.

    With `use_router` (the default) turns flow through the deterministic
    RouterShell — wake grammar, then grammar routing, chat as fallback. Pass
    False to get the legacy direct-to-agent handler.
    """
    from .stt import WhisperSTT
    from .tts import Pyttsx3TTS

    tts = Pyttsx3TTS()
    handler = make_orchestrator_handler(assistant)
    utterance_handler = RouterShell().handle if use_router else None
    if push_to_talk:
        from .mic import PushToTalkRecorder
        from .trigger import EnterKeyTrigger
        return VoiceLoop(PushToTalkRecorder(), WhisperSTT(model=model), tts,
                         handler, trigger=EnterKeyTrigger(),
                         utterance_handler=utterance_handler)
    from .mic import MicRecorder
    return VoiceLoop(MicRecorder(seconds=seconds), WhisperSTT(model=model),
                     tts, handler, utterance_handler=utterance_handler)
