"""Text-to-speech. Default is pyttsx3 — fully offline, uses Windows SAPI5 (and
NSSpeechSynthesizer on macOS / espeak on Linux), no GPU. `FakeTTS` records what
would be spoken so the voice loop is testable."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TextToSpeech(Protocol):
    def speak(self, text: str) -> None: ...


class Pyttsx3TTS:
    def __init__(self, rate: int | None = None) -> None:
        self.rate = rate
        self._engine = None

    def _engine_(self):  # pragma: no cover - needs the package + an audio device
        if self._engine is None:
            import pyttsx3  # type: ignore
            self._engine = pyttsx3.init()
            if self.rate is not None:
                self._engine.setProperty("rate", self.rate)
        return self._engine

    def speak(self, text: str) -> None:  # pragma: no cover - needs a speaker
        if not text:
            return
        eng = self._engine_()
        eng.say(text)
        eng.runAndWait()


class FakeTTS:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)
