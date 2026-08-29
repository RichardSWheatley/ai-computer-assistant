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

# Below this full-scale RMS a recording is room noise: Whisper
# hallucinates words on silence, so it never reaches the transcriber.
SILENCE_RMS = 0.005


def rms_level(wav_path) -> float | None:
    """RMS of a 16-bit wav as a 0..1 full-scale fraction; None when the
    file can't be judged (missing/odd format) — unknown is never gated."""
    import array
    import math

    try:
        with wave.open(str(wav_path), "rb") as wf:
            if wf.getsampwidth() != 2:
                return None
            raw = wf.readframes(wf.getnframes())
    except (OSError, wave.Error, EOFError):
        return None
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0


def list_input_devices() -> list[str]:
    """Names of input-capable audio devices; [] when audio is
    unavailable — the Settings page shows what there is, never crashes."""
    try:
        import sounddevice as sd  # type: ignore

        return [d["name"] for d in sd.query_devices()
                if d.get("max_input_channels", 0) > 0]
    except Exception:
        return []


@runtime_checkable
class Recorder(Protocol):
    def record(self) -> str:  # returns path to a .wav
        ...


def _default_audio_dir() -> str:
    from ..home import audio_dir

    return str(audio_dir())


class MicRecorder:
    def __init__(self, seconds: float = 5.0, out_dir: str | None = None,
                 sample_rate: int = SAMPLE_RATE,
                 device: str | int | None = None) -> None:
        self.seconds = seconds
        self.out_dir = out_dir or _default_audio_dir()
        self.sample_rate = sample_rate
        # The user picks WHICH microphone on the Settings page — the
        # system default once transcribed a whole living room.
        self.device = device

    def _resolve_device(self):
        d = self.device
        if d in (None, ""):
            return None
        if isinstance(d, str) and d.isdigit():
            return int(d)
        return d

    def record(self, stop=None) -> str:  # pragma: no cover - needs a microphone
        """One listening window. `stop` (a threading.Event) aborts the
        window within ~0.1 s — the mic button's OFF must feel instant,
        not 'whenever the current 5-second window ends'."""
        import sounddevice as sd  # type: ignore
        import numpy as np  # type: ignore

        chunks = []

        def _cb(indata, frames, time_info, status):
            chunks.append(indata.copy())

        deadline = self.seconds
        elapsed = 0.0
        with sd.InputStream(samplerate=self.sample_rate, channels=1,
                            dtype="int16", device=self._resolve_device(),
                            callback=_cb):
            step = 0.1
            while elapsed < deadline:
                if stop is not None and stop.wait(step):
                    break
                elif stop is None:
                    import time as _time

                    _time.sleep(step)
                elapsed += step

        data = (np.concatenate(chunks) if chunks
                else np.zeros((0, 1), dtype="int16"))
        os.makedirs(self.out_dir, exist_ok=True)
        path = os.path.join(self.out_dir, "utterance.wav")
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.sample_rate)
            wf.writeframes(np.asarray(data, dtype="int16").tobytes())
        return path


class PushToTalkRecorder:
    """Press-to-talk: starts recording on record(), stops when you press Enter.
    No fixed window, so utterances can be any length."""

    def __init__(self, out_dir: str | None = None,
                 sample_rate: int = SAMPLE_RATE) -> None:
        self.out_dir = out_dir or _default_audio_dir()
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
