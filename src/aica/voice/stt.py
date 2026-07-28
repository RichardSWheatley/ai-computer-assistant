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

    def transcribe_utterance(self, wav_path: str) -> "Utterance":  # pragma: no cover
        """Transcribe with per-word timestamps (feeds the wake grammar)."""
        from ..routing.model import Utterance, Word

        segments, _ = self._load().transcribe(wav_path, word_timestamps=True)
        words: list[Word] = []
        for seg in segments:
            for w in (seg.words or []):
                words.append(Word(text=w.word.strip(), start=w.start, end=w.end))
        text = " ".join(w.text for w in words).strip()
        return Utterance(text=text, words=tuple(words),
                         t_start=words[0].start if words else 0.0,
                         t_end=words[-1].end if words else 0.0)


class FakeSTT:
    def __init__(self, text: str = "", utterances: list | None = None) -> None:
        self.text = text
        self.utterances = list(utterances) if utterances else None
        self.calls: list[str] = []

    def transcribe(self, wav_path: str) -> str:
        self.calls.append(wav_path)
        if self.utterances:
            return self.utterances.pop(0).text
        return self.text

    def transcribe_utterance(self, wav_path: str):
        from ..routing.model import Utterance

        self.calls.append(wav_path)
        if self.utterances:
            return self.utterances.pop(0)
        return Utterance.from_text(self.text)


def to_utterance(stt: SpeechToText, wav_path: str):
    """Get an Utterance from any STT backend (word timings when available)."""
    from ..routing.model import Utterance

    fn = getattr(stt, "transcribe_utterance", None)
    if fn is not None:
        return fn(wav_path)
    return Utterance.from_text(stt.transcribe(wav_path) or "")
