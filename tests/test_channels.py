"""Fix 5: speech vs screen channels — the shell strip is the guarantee."""

from __future__ import annotations

import re
import threading

import pytest

FORBIDDEN_IN_SPEECH = (
    re.compile(r"`"),                                  # any code fence/span
    re.compile(r"^\s*[+-]{1,3}(?![0-9 ])", re.M),      # diff lines
    re.compile(r"@@"),
    re.compile(r"(?:^|\s)(?:~?/|[A-Za-z]:\\)\S+"),     # absolute / home paths
    re.compile(r"\S+\.(?:c|h|py|yaml|json|log|md|conf)\b"),  # code-ish files
    re.compile(r"https?://"),
)

ADVERSARIAL = [
    "Here is the fix:\n```c\nint main(void) {\n  return 0;\n}\n```\nRebuilt and it passes.",
    "I changed /home/user/zephyr/samples/basic/blinky/src/main.c line 12. It builds now.",
    "```diff\n--- a/src/main.c\n+++ b/src/main.c\n@@ -1,3 +1,3 @@\n-old\n+new\n```\nDone.",
    "The build failed. See https://docs.zephyrproject.org/latest for details. "
    "Check prj.conf too.",
    "One thing. Two things. Three things. Four things. Five things happened today.",
]


class TestSplitResponse:
    @pytest.mark.parametrize("text", ADVERSARIAL)
    def test_speech_never_contains_forbidden_tokens(self, text):
        from aica.ui.channels import split_response
        r = split_response(text)
        for rx in FORBIDDEN_IN_SPEECH:
            assert not rx.search(r.speech), (rx.pattern, r.speech)

    @pytest.mark.parametrize("text", ADVERSARIAL)
    def test_screen_preserves_everything(self, text):
        from aica.ui.channels import split_response
        assert split_response(text).screen == text

    @pytest.mark.parametrize("text", ADVERSARIAL)
    def test_speech_is_at_most_two_sentences(self, text):
        from aica.ui.channels import split_response
        speech = split_response(text).speech
        assert len(re.findall(r"[.!?](?:\s|$)", speech)) <= 2

    def test_code_only_response_speaks_fallback(self):
        from aica.ui.channels import split_response
        r = split_response("```python\nprint('hi')\n```")
        assert r.speech == "The details are on your screen."

    def test_conversational_text_passes_through(self):
        from aica.ui.channels import split_response
        r = split_response("The build is green. Twister passed on native sim.")
        assert r.speech == "The build is green. Twister passed on native sim."


class TestVoiceLoopEnforcement:
    def test_loop_speaks_stripped_channel_and_screens_the_rest(self):
        from aica.routing.model import Utterance
        from aica.voice.loop import VoiceLoop
        from aica.voice.mic import FakeRecorder
        from aica.voice.stt import FakeSTT
        from aica.voice.tts import FakeTTS

        reply = "Fixed it:\n```c\nint x = 1;\n```\nThe build is green now."
        screens: list[str] = []
        tts = FakeTTS()
        loop = VoiceLoop(FakeRecorder(), FakeSTT(text="status report"), tts,
                         handler=lambda heard: reply,
                         on_screen=screens.append)
        loop.converse_once()
        assert screens == [reply]                      # full artifact on screen
        assert tts.spoken and "`" not in tts.spoken[0]
        assert "int x" not in tts.spoken[0]

    def test_utterance_path_is_also_enforced(self):
        from aica.routing.model import Utterance
        from aica.voice.loop import RouterShell, VoiceLoop
        from aica.voice.mic import FakeRecorder
        from aica.voice.stt import FakeSTT
        from aica.voice.tts import FakeTTS

        # A work handler that (wrongly) returns a diff — the shell must strip it.
        shell = RouterShell(require_wake=False,
                            work=lambda d: "Patched.\n```diff\n+led0\n```")
        tts = FakeTTS()
        loop = VoiceLoop(FakeRecorder(),
                         FakeSTT(utterances=[Utterance.from_text("build blinky")]),
                         tts, handler=lambda h: "",
                         utterance_handler=shell.handle)
        loop.converse_once()
        assert tts.spoken == ["Patched."]


class TestStreamingStart:
    def test_say_does_not_block_on_playback(self):
        from aica.voice.tts import PausableSpeaker

        release = threading.Semaphore(0)

        class SlowTTS:
            def __init__(self):
                self.spoken = []

            def speak(self, text):
                assert release.acquire(timeout=5)
                self.spoken.append(text)

        tts = SlowTTS()
        spk = PausableSpeaker(tts)
        spk.say("First sentence. Second sentence.")   # must return immediately
        assert tts.spoken == []                        # nothing played yet
        release.release()
        spk.wait_until(lambda: tts.spoken == ["First sentence."])
        release.release()
        spk.wait_until(lambda: len(tts.spoken) == 2)
