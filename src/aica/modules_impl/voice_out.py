"""voice-out module: pausable TTS behind RPC (PAUSE/RESUME/STOP native)."""

from __future__ import annotations

from ..modules.runtime import serve

_STATE: dict = {}


def _speaker():  # pragma: no cover - needs an audio device
    from ..voice.tts import PausableSpeaker, Pyttsx3TTS

    if "speaker" not in _STATE:
        _STATE["speaker"] = PausableSpeaker(Pyttsx3TTS())
    return _STATE["speaker"]


def start(params, emit):
    return {"ok": True}


def say(params, emit):  # pragma: no cover - needs an audio device
    _speaker().say(params["text"])
    return {"queued": True}


def pause_at_checkpoint(params, emit):  # pragma: no cover
    _speaker().pause()
    return {"paused": True}


def resume(params, emit):  # pragma: no cover
    _speaker().resume()
    return {"resumed": True}


def stop(params, emit):  # pragma: no cover
    _speaker().stop()
    return {"stopped": True}


def status(params, emit):
    spk = _STATE.get("speaker")
    return {"pending": spk.pending if spk else 0}


if __name__ == "__main__":  # pragma: no cover - exercised as a child process
    serve(name="voice-out", version="1.0.0",
          handlers={"start": start, "status": status, "say": say,
                    "pause_at_checkpoint": pause_at_checkpoint,
                    "resume": resume, "stop": stop})
