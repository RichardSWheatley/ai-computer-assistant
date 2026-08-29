"""Voice in the GUI: the microphone lands in the app (no command line)."""

from __future__ import annotations

import time
from pathlib import Path

from rita.routing.model import Utterance

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def make_presenter(tmp_path, utterances):
    from rita.config import RitaConfig
    from rita.gui.presenter import GuiPresenter
    from rita.supervisor import Supervisor
    from rita.voice.mic import FakeRecorder
    from rita.voice.stt import FakeSTT
    from rita.voice.tts import FakeTTS

    tts = FakeTTS()
    sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                         voice_wake_word=True),
                     config_path=tmp_path / "config", tts=tts,
                     workdir=tmp_path / "work")
    stt = FakeSTT(utterances=[Utterance.from_text(u) for u in utterances])
    p = GuiPresenter(sup, voice_backends=lambda: (FakeRecorder(), stt, None))
    ev = {"user": [], "reply": []}
    p.on_user = ev["user"].append
    p.on_reply = ev["reply"].append
    return p, sup, tts, ev


class TestVoiceConfig:
    def test_voice_enabled_round_trips(self, tmp_path):
        from rita.config import RitaConfig, load_rita_config, save_rita_config
        cfg = RitaConfig(voice_enabled=True)
        save_rita_config(cfg, tmp_path / "config")
        assert load_rita_config(tmp_path / "config").voice_enabled is True
        assert RitaConfig().voice_enabled is False       # off by default


class TestListening:
    def test_wake_then_question_is_heard_answered_and_spoken(self, tmp_path):
        p, sup, tts, ev = make_presenter(
            tmp_path, ["hello rita", "what zephyr version are we on"])
        try:
            assert p.start_voice() is True
            assert p.voice_active
            assert wait_for(lambda: len(ev["reply"]) >= 2)
            assert ev["reply"][0] == "Yes?"
            assert any("zephyr" in r.lower() for r in ev["reply"][1:])
            assert any("🎤" in u for u in ev["user"])     # heard text echoed
            assert any("Yes?" in s for s in tts.spoken)   # actually spoken
        finally:
            p.close()

    def test_asleep_utterances_leave_no_trace(self, tmp_path):
        p, sup, tts, ev = make_presenter(
            tmp_path, ["what zephyr version are we on"])
        try:
            p.start_voice()
            time.sleep(0.3)
            assert ev["user"] == [] and ev["reply"] == []
            assert tts.spoken == []
        finally:
            p.close()

    def test_stop_phrase_sleeps_wake_word_rewakes(self, tmp_path):
        p, sup, tts, ev = make_presenter(
            tmp_path, ["hello rita", "goodbye",
                       "what zephyr version are we on",   # asleep: ignored
                       "rita"])                            # rewakes
        try:
            p.start_voice()
            assert wait_for(lambda: len(ev["reply"]) >= 3)
            assert ev["reply"][0] == "Yes?"
            assert "quiet" in ev["reply"][1].lower() or \
                   "goodbye" in ev["reply"][1].lower()
            # The ignored question produced nothing: reply 3 is the rewake.
            assert ev["reply"][2] == "Yes?"
        finally:
            p.close()

    def test_stop_voice_ends_the_thread(self, tmp_path):
        p, sup, tts, ev = make_presenter(tmp_path, ["hello rita"])
        try:
            p.start_voice()
            assert p.voice_active
            p.stop_voice()
            assert wait_for(lambda: not p.voice_active)
        finally:
            p.close()


class TestConfigResilience:
    def test_corrupt_config_backs_up_and_starts_fresh(self, tmp_path):
        # A config written by a pre-0.16.2 build (raw Windows backslashes)
        # must not wedge the app: back it up, start with defaults.
        from rita.config import load_rita_config
        bad = tmp_path / "config"
        bad.write_text('[rita]\nworkspace = "C:\\zephyrproject"\n')
        cfg = load_rita_config(bad)
        assert cfg.workspace is None                  # defaults, not a crash
        assert (tmp_path / "config.bad").exists()     # evidence preserved


class TestHonestUnavailability:
    def test_default_backends_probe_deps_eagerly(self, monkeypatch, tmp_path):
        # The error must land at enable time ("Voice isn't available"),
        # never later from inside the listen thread ("Voice stopped").
        import importlib.util

        from rita.config import RitaConfig
        from rita.gui.presenter import GuiPresenter
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS

        real_find = importlib.util.find_spec

        def find_spec(name, *a, **k):
            if name in ("sounddevice", "faster_whisper"):
                return None
            return real_find(name, *a, **k)

        monkeypatch.setattr(importlib.util, "find_spec", find_spec)
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                         voice_wake_word=True),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        p = GuiPresenter(sup)                  # default (real) backends
        replies = []
        p.on_reply = replies.append
        try:
            assert p.start_voice() is False
            assert p.voice_active is False
            joined = " ".join(replies)
            assert "sounddevice" in joined and "faster" in joined
        finally:
            p.close()

    def test_missing_deps_named_never_silent(self, tmp_path):
        from rita.config import RitaConfig
        from rita.gui.presenter import GuiPresenter
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS

        def boom():
            raise ImportError("No module named 'sounddevice'")

        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                         voice_wake_word=True),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        p = GuiPresenter(sup, voice_backends=boom)
        replies = []
        p.on_reply = replies.append
        try:
            assert p.start_voice() is False
            assert p.voice_active is False
            assert any("voice" in r.lower() and "sounddevice" in r
                       for r in replies)
        finally:
            p.close()
