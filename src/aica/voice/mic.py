"""Microphone capture -> a .wav file the STT layer can read.

Uses `sounddevice` (PortAudio) and writes a 16 kHz mono WAV (what Whisper wants).
Guarded + lazy so the module imports without audio libs; `FakeRecorder` lets the
voice loop be tested with no hardware.
"""

from __future__ import annotations

import os
import wave
from typing import Protocol, runtime_checkable

SAMPLE_RATE = 16000


@runtime_checkable
class Recorder(Protocol):
    def record(self) -> str:  # returns path to a .wav
        ...


class MicRecorder:
    def __init__(self, seconds: float = 5.0, out_dir: str = ".aica/audio",
                 sample_rate: int = SAMPLE_RATE) -> None:
        self.seconds = seconds
        self.out_dir = out_dir
        self.sample_rate = sample_rate

    def record(self) -> str:  # pragma: no cover - needs a microphone
        import sounddevice as sd  # type: ignore
        import numpy as np  # type: ignore

        frames = int(self.seconds * self.sample_rate)
        audio = sd.rec(frames, samplerate=self.sample_rate, channels=1,
                       dtype="int16")
        sd.wait()
        os.makedirs(self.out_dir, exist_ok=True)
        path = os.path.join(self.out_dir, "utterance.wav")
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.sample_rate)
            wf.writeframes(np.asarray(audio, dtype="int16").tobytes())
        return path


class PushToTalkRecorder:
    """Press-to-talk: starts recording on record(), stops when you press Enter.
    No fixed window, so utterances can be any length."""

    def __init__(self, out_dir: str = ".aica/audio",
                 sample_rate: int = SAMPLE_RATE) -> None:
        self.out_dir = out_dir
        self.sample_rate = sample_rate

    def record(self) -> str:  # pragma: no cover - needs a microphone
        import sounddevice as sd  # type: ignore
        import numpy as np  # type: ignore

        chunks = []

        def _cb(indata, frames, time_info, status):
            chunks.append(indata.copy())

        print("  🎙️  Recording… press Enter to stop.")
        with sd.InputStream(samplerate=self.sample_rate, channels=1,
                            dtype="int16", callback=_cb):
            try:
                input()
            except EOFError:
                pass

        data = (np.concatenate(chunks) if chunks
                else np.zeros((0, 1), dtype="int16"))
        os.makedirs(self.out_dir, exist_ok=True)
        path = os.path.join(self.out_dir, "utterance.wav")
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(np.asarray(data, dtype="int16").tobytes())
        return path


class FakeRecorder:
    """Returns a preset path (tests / piping a pre-recorded clip)."""

    def __init__(self, path: str = "fake.wav") -> None:
        self.path = path
        self.calls = 0

    def record(self) -> str:
        self.calls += 1
        return self.path
