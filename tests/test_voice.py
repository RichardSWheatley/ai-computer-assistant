"""Voice loop tests with fake recorder/STT/TTS — no microphone or speaker needed."""

from dataclasses import dataclass, field

from aica.voice.loop import VoiceLoop, make_orchestrator_handler
from aica.voice.mic import FakeRecorder
from aica.voice.stt import FakeSTT
from aica.voice.tts import FakeTTS


def _loop(heard_text, handler):
    return VoiceLoop(FakeRecorder("u.wav"), FakeSTT(heard_text), FakeTTS(), handler)


def test_converse_once_runs_and_speaks():
    spoken_back = {}

    def handler(text):
        spoken_back["request"] = text
        return f"I did: {text}"

    loop = _loop("open notepad", handler)
    heard, said = loop.converse_once()
    assert heard == "open notepad"
    assert spoken_back["request"] == "open notepad"
    assert said == "I did: open notepad"
    assert loop.tts.spoken == ["I did: open notepad"]


def test_empty_transcription_is_ignored():
    called = {"n": 0}

    def handler(text):
        called["n"] += 1
        return "x"

    loop = _loop("   ", handler)          # silence / no speech
    heard, said = loop.converse_once()
    assert heard == "" and said == ""
    assert called["n"] == 0               # handler not invoked
    assert loop.tts.spoken == []


def test_stop_phrase_ends_without_running():
    ran = {"n": 0}

    def handler(text):
        ran["n"] += 1
        return "x"

    loop = _loop("stop listening", handler)
    heard, said = loop.converse_once()
    assert loop.is_stop(heard) and said == "Goodbye."
    assert ran["n"] == 0


# --- orchestrator handler --------------------------------------------------

@dataclass
class _Step:
    call: object


@dataclass
class _Call:
    tool: str


@dataclass
class _Run:
    finished: bool
    message: str = ""
    steps: list = field(default_factory=list)


class _FakeAssistant:
    def __init__(self, run):
        self._run = run
        self.goals = []

    def run(self, goal):
        self.goals.append(goal)
        return self._run


def test_handler_summarizes_success_for_speech():
    run = _Run(finished=True, message="Task complete.",
               steps=[_Step(_Call("open_app")), _Step(_Call("type_text")),
                      _Step(_Call("task_complete"))])
    a = _FakeAssistant(run)
    handler = make_orchestrator_handler(a)
    said = handler("open notepad and type hi")
    assert a.goals == ["open notepad and type hi"]
    assert said.startswith("Done.")
    assert "open_app" in said and "type_text" in said
    assert "task_complete" not in said   # internal tool not narrated


def test_handler_reports_failure_for_speech():
    handler = make_orchestrator_handler(
        _FakeAssistant(_Run(finished=False, message="Action declined.")))
    said = handler("send all my money")
    assert "couldn't finish" in said and "declined" in said
