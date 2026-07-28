"""Voice loop tests with fake recorder/STT/TTS — no microphone or speaker needed."""

from dataclasses import dataclass, field

from rita.voice.loop import VoiceLoop, build_voice_loop, make_orchestrator_handler
from rita.voice.mic import FakeRecorder, MicRecorder, PushToTalkRecorder
from rita.voice.stt import FakeSTT
from rita.voice.trigger import FakeTrigger
from rita.voice.tts import FakeTTS


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


# --- push-to-talk trigger --------------------------------------------------

def test_trigger_gates_each_turn():
    runs = {"n": 0}

    def handler(text):
        runs["n"] += 1
        return "ok"

    # Proceed once, then quit at the prompt.
    loop = VoiceLoop(FakeRecorder(), FakeSTT("do something"), FakeTTS(),
                     handler, trigger=FakeTrigger([True, False]))
    loop.run()
    assert runs["n"] == 1                 # exactly one gated turn ran
    assert loop.trigger.calls == 2        # asked, ran, asked again -> quit


def test_trigger_quit_immediately_runs_no_turns():
    runs = {"n": 0}
    loop = VoiceLoop(FakeRecorder(), FakeSTT("anything"), FakeTTS(),
                     lambda t: runs.__setitem__("n", runs["n"] + 1) or "x",
                     trigger=FakeTrigger([False]))
    loop.run()
    assert runs["n"] == 0


def test_build_voice_loop_selects_backends():
    asst = _FakeAssistant(_Run(finished=True))
    ptt = build_voice_loop(asst, push_to_talk=True)
    assert isinstance(ptt.recorder, PushToTalkRecorder)
    assert ptt.trigger is not None       # press-Enter-to-talk gate wired in

    cont = build_voice_loop(asst, push_to_talk=False, seconds=3.0)
    assert isinstance(cont.recorder, MicRecorder)
    assert cont.recorder.seconds == 3.0
    assert cont.trigger is None          # continuous listening, no gate


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
