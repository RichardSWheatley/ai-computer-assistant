"""Text-to-speech. Default is pyttsx3 — fully offline, uses Windows SAPI5 (and
NSSpeechSynthesizer on macOS / espeak on Linux), no GPU. `FakeTTS` records what
would be spoken so the voice loop is testable."""

from __future__ import annotations

import re
import threading
import time
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


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class PausableSpeaker:
    """PAUSE / RESUME / STOP for any TextToSpeech (Fix 4).

    Text is split into sentence chunks spoken on a worker thread. PAUSE
    takes effect immediately: the engine's `stop()` (when it has one) aborts
    the in-flight chunk and no further chunk starts; the queue position is
    kept, so RESUME replays from exactly there. STOP flushes the queue.
    Sub-300 ms responsiveness is architectural — short chunks + immediate
    engine stop — so the first sentence can play while the rest streams.
    """

    def __init__(self, tts: TextToSpeech) -> None:
        self.tts = tts
        self._cond = threading.Condition()
        self._chunks: list[str] = []
        self._pos = 0
        self._paused = False
        self._interrupted = False
        self._worker: threading.Thread | None = None

    # --- queueing -----------------------------------------------------------

    def say(self, text: str) -> None:
        chunks = [c.strip() for c in _SENTENCE_SPLIT.split(text or "") if c.strip()]
        if not chunks:
            return
        with self._cond:
            self._chunks.extend(chunks)
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._loop, daemon=True,
                                                name="pausable-speaker")
                self._worker.start()
            self._cond.notify_all()

    def _loop(self) -> None:
        while True:
            with self._cond:
                while self._paused or self._pos >= len(self._chunks):
                    self._cond.wait()
                chunk = self._chunks[self._pos]
            # Speak OUTSIDE the lock so pause()/stop() stay instant.
            self.tts.speak(chunk)
            with self._cond:
                if self._interrupted:
                    self._interrupted = False   # aborted chunk replays on resume
                else:
                    self._pos += 1

    # --- controls -----------------------------------------------------------

    def _halt_engine(self) -> None:
        stop = getattr(self.tts, "stop", None)
        if callable(stop):
            stop()

    def pause(self) -> None:
        with self._cond:
            if self._pos < len(self._chunks):
                self._interrupted = True
            self._paused = True
        self._halt_engine()

    def resume(self) -> None:
        with self._cond:
            self._paused = False
            self._cond.notify_all()

    def stop(self) -> None:
        with self._cond:
            in_flight = self._pos < len(self._chunks)
            self._chunks = []
            self._pos = 0
            self._paused = False
            self._interrupted = in_flight
            self._cond.notify_all()
        self._halt_engine()

    # --- introspection ------------------------------------------------------

    @property
    def position(self) -> int:
        with self._cond:
            return self._pos

    @property
    def pending(self) -> int:
        with self._cond:
            return len(self._chunks) - self._pos

    def wait_until(self, pred, timeout: float = 5.0) -> None:
        """Test/UI helper: poll until pred() holds or fail loudly."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if pred():
                return
            time.sleep(0.005)
        raise AssertionError("PausableSpeaker.wait_until: condition not met")
