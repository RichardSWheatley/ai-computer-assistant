"""The conversation loop: listen -> transcribe -> run the task -> speak back.

VoiceLoop is backend-agnostic (recorder / STT / TTS / handler are injected), so
it's fully testable with fakes. `make_orchestrator_handler` turns a spoken
request into a goal for the assistant and returns a short spoken summary of what
it did — security gates (confirmation, quarantine, audit) still apply because it
runs through the normal Orchestrator.
"""

from __future__ import annotations

from typing import Callable

from .mic import Recorder
from .stt import SpeechToText
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


class VoiceLoop:
    def __init__(self, recorder: Recorder, stt: SpeechToText, tts: TextToSpeech,
                 handler: Handler, trigger: Trigger | None = None) -> None:
        self.recorder = recorder
        self.stt = stt
        self.tts = tts
        self.handler = handler
        self.trigger = trigger  # push-to-talk / wake-word gate; None = continuous

    def converse_once(self) -> tuple[str, str]:
        """One turn: record, transcribe, handle, speak. Returns (heard, said)."""
        wav = self.recorder.record()
        heard = (self.stt.transcribe(wav) or "").strip()
        if not heard:
            return "", ""
        if heard.lower().strip(" .!?") in _STOP_PHRASES:
            self.tts.speak("Goodbye.")
            return heard, "Goodbye."
        said = self.handler(heard)
        self.tts.speak(said)
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
                     seconds: float = 5.0, model: str = "base") -> "VoiceLoop":
    """Assemble a VoiceLoop with the real backends, lazily."""
    from .stt import WhisperSTT
    from .tts import Pyttsx3TTS

    tts = Pyttsx3TTS()
    handler = make_orchestrator_handler(assistant)
    if push_to_talk:
        from .mic import PushToTalkRecorder
        from .trigger import EnterKeyTrigger
        return VoiceLoop(PushToTalkRecorder(), WhisperSTT(model=model), tts,
                         handler, trigger=EnterKeyTrigger())
    from .mic import MicRecorder
    return VoiceLoop(MicRecorder(seconds=seconds), WhisperSTT(model=model),
                     tts, handler)
