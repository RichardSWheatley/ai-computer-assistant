"""One-click Status + honest task ages. The owner's complaint: "it has
been working on something that I could have already finished and it
isn't done" — status must say HOW LONG a task has been at it and how
long since it last made progress, and asking must not require typing."""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def make_supervisor(tmp_path):
    from rita.config import RitaConfig
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    return Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                          auto_setup=False,
                                          ai_routing=False),
                      config_path=tmp_path / "config", tts=FakeTTS(),
                      workdir=tmp_path / "work")


class TestAgeFormat:
    def test_ages_read_like_a_human_wrote_them(self):
        from rita.supervisor import _age

        assert _age(0) == "0s"
        assert _age(45) == "45s"
        assert _age(300) == "5m 00s"
        assert _age(3900) == "1h 05m"


class TestLiveStatusAges:
    def test_status_says_how_long_and_when_last_progress(self, tmp_path):
        sup = make_supervisor(tmp_path)
        release = threading.Event()
        stage_done = threading.Event()

        def work(ctl):
            ctl.checkpoint("BUILD")
            stage_done.set()
            release.wait(timeout=30)
            return "ok"

        sup.manager.submit("walk the dog", work)
        assert stage_done.wait(timeout=10)
        text = sup._live_status()
        release.set()
        assert "walk the dog" in text
        assert re.search(r"running for \d+s", text), text
        assert re.search(r"last progress \d+s ago", text), text

    def test_report_carries_timestamps(self, tmp_path):
        sup = make_supervisor(tmp_path)
        release = threading.Event()

        def work(ctl):
            release.wait(timeout=30)
            return "ok"

        tid = sup.manager.submit("hold", work)
        deadline = time.monotonic() + 10
        while (sup.manager.report(tid).started_at == 0.0
               and time.monotonic() < deadline):
            time.sleep(0.01)
        rep = sup.manager.report(tid)
        release.set()
        assert rep.started_at > 0.0


class TestStatusButton:
    @pytest.fixture()
    def app(self, monkeypatch):
        pytest.importorskip("PySide6")
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])

    def test_button_asks_status_through_the_one_code_path(self, tmp_path,
                                                          app):
        from rita.gui.main_window import RitaWindow
        from rita.gui.presenter import GuiPresenter

        sup = make_supervisor(tmp_path)
        p = GuiPresenter(sup)
        w = RitaWindow(p)
        try:
            replies: list[str] = []
            w.sig_chat_event.connect(
                lambda cid, kind, text:
                kind == "reply" and replies.append(text))
            tab = w.chat_tabs.widget(0)
            assert hasattr(tab, "status_btn")
            tab.status_btn.click()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                app.processEvents()
                if any("Nothing is running" in r for r in replies):
                    break
                time.sleep(0.02)
            assert any("Nothing is running" in r for r in replies), replies
        finally:
            p.close()
            w.close()
