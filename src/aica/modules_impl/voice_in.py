"""voice-in module: mic capture + STT behind RPC."""

from __future__ import annotations

from dataclasses import asdict

from ..modules.runtime import serve

_STATE: dict = {}


def start(params, emit):
    _STATE["model"] = params.get("model", "base")
    _STATE["seconds"] = float(params.get("seconds", 5.0))
    return {"ok": True}


def listen_once(params, emit):  # pragma: no cover - needs mic + whisper
    from ..voice.mic import MicRecorder
    from ..voice.stt import WhisperSTT, to_utterance

    wav = MicRecorder(seconds=_STATE.get("seconds", 5.0)).record()
    utt = to_utterance(WhisperSTT(model=_STATE.get("model", "base")), wav)
    return asdict(utt)


def status(params, emit):
    return {"model": _STATE.get("model")}


if __name__ == "__main__":  # pragma: no cover - exercised as a child process
    serve(name="voice-in", version="1.0.0",
          handlers={"start": start, "status": status,
                    "listen_once": listen_once})
