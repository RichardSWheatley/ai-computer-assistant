"""Speech-to-text. Default backend is local Whisper (faster-whisper), which runs
on CPU (small model) — no GPU needed. Pluggable so a cloud STT can drop in later.
`FakeSTT` returns canned text for tests."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SpeechToText(Protocol):
    def transcribe(self, wav_path: str) -> str: ...


class WhisperSTT:
    """Local transcription via faster-whisper. Lazy-loads the model on first use."""

    def __init__(self, model: str = "base", device: str = "auto",
                 compute_type: str = "int8") -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load(self):  # pragma: no cover - needs the package + a model download
        if self._model is None:
            from faster_whisper import WhisperModel  # type: ignore
            self._model = WhisperModel(self.model_name, device=self.device,
                                       compute_type=self.compute_type)
        return self._model

    def transcribe(self, wav_path: str) -> str:  # pragma: no cover - needs audio
        segments, _ = self._load().transcribe(wav_path)
        return " ".join(seg.text for seg in segments).strip()


class FakeSTT:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls: list[str] = []

    def transcribe(self, wav_path: str) -> str:
        self.calls.append(wav_path)
        return self.text
