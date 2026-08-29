"""Voice guards + GUI affordances (the owner's living-room bugs).

RITA transcribed speech nobody said to her: the default input device
picked up the house, silence/noise hallucinated words, and once woken
she stayed awake forever. And the install buttons gave no visible
feedback. Mic selection, a silence gate, an awake window, and buttons
that act like buttons.
"""

from __future__ import annotations

import math
import struct
import time
import wave
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def write_wav(path: Path, *, level: float, seconds: float = 0.3,
              rate: int = 16000) -> Path:
    """A mono 16-bit wav: a sine at the given full-scale level."""
    n = int(seconds * rate)
    amp = int(level * 32767)
    frames = b"".join(
        struct.pack("<h", int(amp * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(n))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(frames)
    return path


class TestSilenceGate:
    def test_rms_levels(self, tmp_path):
        from rita.voice.mic import SILENCE_RMS, rms_level
        quiet = write_wav(tmp_path / "quiet.wav", level=0.001)
        loud = write_wav(tmp_path / "loud.wav", level=0.3)
        assert rms_level(quiet) < SILENCE_RMS
        assert rms_level(loud) > SILENCE_RMS

    def test_unreadable_wav_is_not_gated(self, tmp_path):
        from rita.voice.mic import rms_level
        assert rms_level(tmp_path / "missing.wav") is None

    def test_silence_never_reaches_the_transcriber(self, tmp_path):
        # Whisper hallucinates words on room noise; a silent recording
        # must be dropped BEFORE transcription.
        from rita.config import RitaConfig
        from rita.gui.presenter import GuiPresenter
        from rita.supervisor import Supervisor
        from rita.voice.mic import FakeRecorder
        from rita.voice.tts import FakeTTS

        silent = write_wav(tmp_path / "silent.wav", level=0.001)

        class CountingSTT:
            calls = 0

            def transcribe_words(self, wav):
                CountingSTT.calls += 1
                return "phantom words", []

            def transcribe(self, wav):
                CountingSTT.calls += 1
                return "phantom words"

        recorder = FakeRecorder(path=str(silent))
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                             auto_setup=False),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        p = GuiPresenter(
            sup, voice_backends=lambda: (recorder, CountingSTT(), None))
        assert p.start_voice()
        deadline = time.time() + 3
        while time.time() < deadline and recorder.calls < 3:
            time.sleep(0.02)
        p.stop_voice()
        assert recorder.calls >= 3          # the mic kept listening
        assert CountingSTT.calls == 0       # silence never transcribed


class TestAwakeWindow:
    def _shell(self, tmp_path, clock, awake_seconds=120):
        from rita.config import RitaConfig, save_rita_config
        from rita.voice.loop import RouterShell

        cfg = RitaConfig(voice_awake_seconds=awake_seconds)
        save_rita_config(cfg, tmp_path / "config")
        return RouterShell(config_path=tmp_path / "config", clock=clock)

    def test_awake_expires_and_chatter_goes_silent(self, tmp_path):
        now = {"t": 1000.0}
        shell = self._shell(tmp_path, lambda: now["t"])
        assert shell.handle("rita") == "Yes?"          # woke
        assert shell.handle("this is the second house") != ""   # in window
        now["t"] += 121
        assert shell.handle("one point five kg") == ""  # window closed
        assert shell.handle("rita") == "Yes?"           # wakes again

    def test_commands_extend_the_window_chatter_does_not(self, tmp_path):
        now = {"t": 0.0}
        shell = self._shell(tmp_path, lambda: now["t"])
        shell.handle("rita")
        now["t"] += 100
        assert shell.handle("pause") != ""              # a real command
        now["t"] += 100                                 # 200 total, 100 since
        assert shell.handle("random words") != ""       # still in window
        now["t"] += 110                                 # chat did NOT extend
        assert shell.handle("more random words") == ""

    def test_always_awake_shell_never_expires(self, tmp_path):
        now = {"t": 0.0}
        from rita.voice.loop import RouterShell
        shell = RouterShell(config_path=tmp_path / "c2", require_wake=False,
                            clock=lambda: now["t"])
        now["t"] += 10_000
        assert shell.handle("hello there") != ""


class TestMicSelection:
    def test_recorder_carries_the_device(self):
        from rita.voice.mic import MicRecorder
        r = MicRecorder(device="USB Microphone (2)")
        assert r.device == "USB Microphone (2)"
        assert MicRecorder(device="3")._resolve_device() == 3
        assert MicRecorder()._resolve_device() is None

    def test_device_listing_degrades_to_empty(self):
        # No PortAudio on this machine -> an empty list, never a crash.
        from rita.voice.mic import list_input_devices
        assert isinstance(list_input_devices(), list)

    def test_config_persists_the_choice(self, tmp_path):
        from rita.config import RitaConfig, load_rita_config, save_rita_config
        cfg = RitaConfig(voice_input_device="USB Microphone",
                         voice_awake_seconds=60)
        save_rita_config(cfg, tmp_path / "config")
        back = load_rita_config(tmp_path / "config")
        assert back.voice_input_device == "USB Microphone"
        assert back.voice_awake_seconds == 60


class TestMicButtonModel:
    """The owner's model: the MIC BUTTON is the gate. No wake word by
    default — mic on means every utterance is a command; Send turns
    the mic off; the wake word is opt-in config."""

    def _sup(self, tmp_path, **cfg_kw):
        from rita.config import RitaConfig
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        return Supervisor(
            rita_cfg=RitaConfig(workspace=str(WS), auto_setup=False,
                                **cfg_kw),
            config_path=tmp_path / "config", tts=FakeTTS(),
            workdir=tmp_path / "work")

    def test_no_wake_word_by_default(self, tmp_path):
        from rita.config import RitaConfig
        assert RitaConfig().voice_wake_word is False
        sup = self._sup(tmp_path)
        assert sup.shell.require_wake is False
        # Heard speech routes immediately — no name needed.
        assert sup.shell.handle("what zephyr version are we on") != ""

    def test_wake_word_is_opt_in(self, tmp_path):
        sup = self._sup(tmp_path, voice_wake_word=True)
        assert sup.shell.require_wake is True
        assert sup.shell.handle("what zephyr version are we on") == ""
        assert sup.shell.handle("rita") == "Yes?"

    def test_chat_tab_has_a_mic_button_and_send_kills_it(self, tmp_path,
                                                         monkeypatch):
        pytest.importorskip("PySide6")
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from rita.gui.main_window import RitaWindow
        from rita.gui.presenter import GuiPresenter
        from rita.routing.model import Utterance
        from rita.voice.mic import FakeRecorder
        from rita.voice.stt import FakeSTT

        app = QApplication.instance() or QApplication([])
        sup = self._sup(tmp_path)
        stt = FakeSTT(utterances=[Utterance.from_text("hello there")])
        p = GuiPresenter(sup, voice_backends=lambda: (FakeRecorder(), stt,
                                                      None))
        w = RitaWindow(p)
        try:
            tab = w.chat_tabs.widget(0)
            assert hasattr(tab, "mic_btn")       # the mic lives IN the chat
            tab.mic_btn.setChecked(True)
            tab._mic_toggled()
            assert p.voice_active
            tab.prompt.setText("list your toolsets")
            tab._send()                          # Send turns the mic OFF
            deadline = time.time() + 5
            while time.time() < deadline and p.voice_active:
                app.processEvents()
                time.sleep(0.02)
            assert not p.voice_active
            while time.time() < deadline and tab.mic_btn.isChecked():
                app.processEvents()
                time.sleep(0.02)
            assert not tab.mic_btn.isChecked()   # the button follows
        finally:
            p.close()
            w.close()

    def test_unavailable_voice_unchecks_the_button(self, tmp_path,
                                                   monkeypatch):
        pytest.importorskip("PySide6")
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from rita.gui.main_window import RitaWindow
        from rita.gui.presenter import GuiPresenter

        app = QApplication.instance() or QApplication([])
        sup = self._sup(tmp_path)

        def boom():
            raise ImportError("missing voice packages: sounddevice")

        p = GuiPresenter(sup, voice_backends=boom)
        w = RitaWindow(p)
        try:
            tab = w.chat_tabs.widget(0)
            tab.mic_btn.setChecked(True)
            tab._mic_toggled()
            assert not p.voice_active
            assert not tab.mic_btn.isChecked()
        finally:
            p.close()
            w.close()

    def test_stop_phrase_without_wake_word_turns_the_mic_off(self,
                                                             tmp_path):
        from rita.gui.presenter import GuiPresenter
        from rita.routing.model import Utterance
        from rita.voice.mic import FakeRecorder
        from rita.voice.stt import FakeSTT

        sup = self._sup(tmp_path)
        stt = FakeSTT(utterances=[Utterance.from_text("stop listening")])
        p = GuiPresenter(sup, voice_backends=lambda: (FakeRecorder(), stt,
                                                      None))
        try:
            assert p.start_voice()
            deadline = time.time() + 5
            while time.time() < deadline and p.voice_active:
                time.sleep(0.02)
            assert not p.voice_active            # "stop listening" = mic off
        finally:
            p.close()


class TestButtonsFeelLikeButtons:
    def test_qss_has_pressed_and_hover_states(self):
        from rita.gui.theme import QSS
        assert "QPushButton:pressed" in QSS
        assert "QPushButton:hover" in QSS
        assert "QPushButton:disabled" in QSS

    def test_install_buttons_are_uniform_and_show_busy(self, tmp_path,
                                                       monkeypatch):
        pytest.importorskip("PySide6")
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        import threading

        from PySide6.QtWidgets import QApplication

        from rita.config import RitaConfig
        from rita.gui.modules_page import ModulesPage
        from rita.gui.presenter import GuiPresenter
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS

        app = QApplication.instance() or QApplication([])
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                             auto_setup=False),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        page = ModulesPage(GuiPresenter(sup))
        # One row, one style: no arbitrary blue box among plain ones.
        assert page.cerberus_btn.objectName() != "primary"
        gate = threading.Event()

        class R:
            ok = True
            detail = "done"

        def slow():
            gate.wait(timeout=5)
            return R()

        page._run_install("X", page.toolchain_btn, slow, "starting…")
        assert page.toolchain_btn.isEnabled() is False
        assert "…" in page.toolchain_btn.text()        # visibly busy
        gate.set()
        deadline = time.time() + 5
        while time.time() < deadline and not page.toolchain_btn.isEnabled():
            app.processEvents()
            time.sleep(0.02)
        assert page.toolchain_btn.isEnabled()
        assert page.toolchain_btn.text() == "Install ARM toolchain"
