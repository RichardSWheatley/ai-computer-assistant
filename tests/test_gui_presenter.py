"""GUI shell (presenter layer): headless proof of every GUI behavior.

The Qt view binds to GuiPresenter; everything the window does is tested
here without a display.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"


def blinky_fit(_p: str = "") -> str:
    return json.dumps({"fit": "sample.basic.blinky", "reason": "fits"})


def make_presenter(tmp_path, *, workspace=str(WS), build_seq=("ok",),
                   twister_seq=("pass.json",), steppable=False):
    from rita.config import RitaConfig
    from rita.firmware.coder import FakeCoder
    from rita.firmware.west import FakeWest
    from rita.gui.presenter import GuiPresenter
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    fake = FakeWest(build_seq=list(build_seq), twister_seq=list(twister_seq),
                    fixtures_dir=TW)
    runner = fake
    gate = None
    if steppable:
        from tests.test_pause_stop import SteppableWest
        gate = SteppableWest(fake)
        runner = gate
    # auto_setup off: presenter/window tests exercise routing and
    # rendering — the launch hook must not start real installs.
    sup = Supervisor(rita_cfg=RitaConfig(workspace=workspace,
                                         auto_setup=False),
                     config_path=tmp_path / "config", tts=FakeTTS(),
                     runner=runner, coder=FakeCoder(completions=[blinky_fit()]),
                     workdir=tmp_path / "work")
    p = GuiPresenter(sup)
    events = {"user": [], "reply": [], "screen": [], "tasks": []}
    p.on_user = events["user"].append
    p.on_reply = events["reply"].append
    p.on_screen = events["screen"].append
    p.on_task = events["tasks"].append
    return p, sup, fake, gate, events


def wait_for(pred, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


class TestTypedInput:
    def test_quoted_command_routes_like_unquoted(self, tmp_path):
        p, sup, fake, _, ev = make_presenter(tmp_path)
        p.submit_text('"Rita, build blinky"')
        assert wait_for(lambda: ev["reply"])
        assert "started" in ev["reply"][0].lower()
        tid = sup.manager.latest_active() or "task-1"
        sup.manager.wait_state(tid, "DONE", timeout=5)

    @pytest.mark.parametrize("quotes", ["“Rita, build blinky”", "'build blinky'"])
    def test_smart_and_single_quotes_stripped(self, tmp_path, quotes):
        p, sup, fake, _, ev = make_presenter(tmp_path)
        p.submit_text(quotes)
        assert wait_for(lambda: ev["reply"])
        assert "started" in ev["reply"][0].lower()

    def test_typed_input_needs_no_wake_word(self, tmp_path):
        p, sup, fake, _, ev = make_presenter(tmp_path)
        p.submit_text("build blinky")          # no "hello rita"
        assert wait_for(lambda: ev["reply"])
        assert "started" in ev["reply"][0].lower()

    def test_questions_stay_chat(self, tmp_path):
        p, sup, fake, _, ev = make_presenter(tmp_path)
        p.submit_text("tell me about the apollo510")
        assert wait_for(lambda: ev["reply"])
        assert "ambiq" in ev["reply"][0].lower()
        assert fake.twister_calls == []        # no pipeline ran

    def test_user_echo_is_emitted(self, tmp_path):
        p, sup, fake, _, ev = make_presenter(tmp_path)
        p.submit_text('"build blinky"')
        assert ev["user"] == ["build blinky"]  # echoed unquoted, immediately


class TestChannels:
    def test_speech_and_screen_arrive_separately(self, tmp_path):
        p, sup, fake, _, ev = make_presenter(tmp_path)
        sup.shell.chat = lambda text: "All good.\n```c\nint x;\n```"
        p.submit_text("how are you doing today friend")
        assert wait_for(lambda: ev["reply"] and ev["screen"])
        assert "`" not in ev["reply"][0]           # code never spoken
        assert "int x;" in ev["screen"][0]         # full artifact on screen


class TestTaskLifecycle:
    def test_completed_task_announces_outcome(self, tmp_path):
        p, sup, fake, _, ev = make_presenter(tmp_path)
        p.submit_text("build blinky")
        assert wait_for(lambda: any("green" in r.lower() for r in ev["reply"]),
                        timeout=8)
        snaps = [t for t in ev["tasks"] if t.state == "DONE"]
        assert snaps and snaps[-1].outcome == "green"

    def test_pause_resume_via_presenter_buttons(self, tmp_path):
        p, sup, fake, gate, ev = make_presenter(tmp_path, steppable=True)
        p.submit_text("build blinky")
        assert gate.in_build.wait(5)
        p.pause()                                   # the PAUSE button
        tid = sup.manager.latest_active()
        assert sup.manager.state(tid) == "PAUSING"
        gate.release_build.set()
        assert sup.manager.wait_state(tid, "PAUSED", timeout=5)
        assert len(fake.build_calls) == 1
        p.resume()                                  # the RESUME button
        assert sup.manager.wait_state(tid, "DONE", timeout=5)
        assert len(fake.build_calls) == 1           # no rebuild

    def test_stop_reports_partial(self, tmp_path):
        p, sup, fake, gate, ev = make_presenter(tmp_path, steppable=True)
        p.submit_text("build blinky")
        assert gate.in_build.wait(5)
        p.stop()                                    # the STOP button
        gate.release_build.set()
        tid = sup.manager.latest_active() or "task-1"
        assert sup.manager.wait_state(tid, "STOPPED", timeout=5)
        assert wait_for(lambda: any(t.state == "STOPPED" for t in ev["tasks"]))


class TestWorkspaceSync:
    def test_sync_from_presenter_writes_home_files_and_config(self, tmp_path,
                                                              monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import load_rita_config
        p, sup, fake, _, ev = make_presenter(tmp_path, workspace=None)
        result = p.sync(str(WS))
        assert result.boards >= 2
        home = tmp_path / "rita"
        assert (home / "boards.json").exists()
        assert (home / "verification-index.json").exists()
        assert (home / "mcp.json").exists()
        assert load_rita_config(tmp_path / "config").workspace == str(WS)
        assert p.status().workspace == str(WS)

    def test_status_reports_actual_facts(self, tmp_path):
        p, sup, fake, _, ev = make_presenter(tmp_path)
        st = p.status()
        assert st.workspace == str(WS)
        assert st.zephyr_version == "4.1.0"


class TestMcpWiring:
    def test_sync_writes_mcp_config_pointing_at_workspace(self, tmp_path,
                                                          monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.firmware.sync import sync_workspace
        sync_workspace(WS)
        cfg = json.loads((tmp_path / "rita" / "mcp.json").read_text())
        server = cfg["mcpServers"]["rita-workspace"]
        assert "mcp-serve" in server["args"]
        assert str(WS) in server["args"]

    def test_supervisor_hands_mcp_config_to_coder_worker(self, tmp_path,
                                                          monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import RitaConfig
        from rita.firmware.sync import sync_workspace
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        sync_workspace(WS)
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                             coder_command="agent -p"),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        worker = sup._make_coder()
        assert worker.mcp_config == str(tmp_path / "rita" / "mcp.json")

    def test_no_mcp_config_when_never_synced(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import RitaConfig
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                             coder_command="agent -p"),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        assert sup._make_coder().mcp_config is None


class TestQtLayer:
    def test_window_builds_and_routes_offscreen(self, tmp_path, monkeypatch):
        pytest.importorskip("PySide6")
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from PySide6.QtWidgets import QApplication

        from rita.gui.main_window import RitaWindow
        from rita.gui.theme import QSS

        app = QApplication.instance() or QApplication([])
        app.setStyleSheet(QSS)
        p, sup, fake, _, ev = make_presenter(tmp_path)
        window = RitaWindow(p)
        try:
            window.prompt.setText('"build blinky"')
            window._send()
            # The window rebinds presenter callbacks to Qt signals; pump the
            # event loop until the routed reply lands in the transcript.
            deadline = time.time() + 5
            while time.time() < deadline:
                app.processEvents()
                if "Started" in window.transcript.toPlainText():
                    break
                time.sleep(0.02)
            text = window.transcript.toPlainText()
            assert "You" in text and "build blinky" in text  # echoed entry
            assert "Started" in text                         # routed reply
            assert window.status_bar.currentMessage()        # facts in the bar
        finally:
            window.close()
