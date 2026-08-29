"""Chat tabs: multiple chats open at once, each with its own workspace.

The owner: "Workspace and chat are still linear. We need chat tabs so
I can open more than one at a time. Each chat tab should have its own
Workspace tab as well." The presenter tags every event with the chat
that owns it; task announcements land in the chat that started the
task; the window renders one tab per chat.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def make_presenter(tmp_path, *, completions=()):
    from rita.config import RitaConfig
    from rita.firmware.coder import FakeCoder
    from rita.gui.presenter import GuiPresenter
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    coder = FakeCoder(completions=list(completions)) if completions else None
    sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                         auto_setup=False),
                     config_path=tmp_path / "config", tts=FakeTTS(),
                     coder=coder, workdir=tmp_path / "work")
    p = GuiPresenter(sup)
    events: list[tuple[str, str, str]] = []
    p.on_chat_event = lambda chat, kind, text: events.append(
        (chat, kind, text))
    return p, sup, events


def wait_for(pred, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.02)
    return pred()


class TestChatScopedSupervisor:
    def test_active_chat_switches_the_workspace(self, tmp_path):
        from rita.learning import chats
        p, sup, _ = make_presenter(tmp_path)
        repo_a = tmp_path / "repo-a"
        repo_a.mkdir()
        sup.active_chat = "chat-1"
        sup.bind_chat(str(repo_a))
        assert sup.effective_workspace() == str(repo_a)
        cid = chats.new_chat()
        sup.active_chat = cid            # the new chat is unbound
        assert sup.effective_workspace() == str(WS)
        sup.active_chat = "chat-1"
        assert sup.effective_workspace() == str(repo_a)

    def test_list_chats(self, tmp_path):
        from rita.learning import chats
        chats.new_chat()
        chats.new_chat()
        assert chats.list_chats()[:2] == ["chat-1", "chat-2"]


class TestEventRouting:
    def test_events_carry_their_chat(self, tmp_path):
        p, sup, events = make_presenter(tmp_path)
        p.set_active_chat("chat-1")
        p.submit_text("list your toolsets")
        assert wait_for(lambda: any(k == "reply" for _, k, _t in events))
        assert all(c == "chat-1" for c, _k, _t in events)
        events.clear()
        p.set_active_chat("chat-2")
        p.submit_text("list your toolsets")
        assert wait_for(lambda: any(k == "reply" for _, k, _t in events))
        assert all(c == "chat-2" for c, _k, _t in events)

    def test_task_announcement_lands_in_the_owning_chat(self, tmp_path):
        toolset = json.dumps({
            "name": "tab-tool", "purpose": "proves routing",
            "files": {"main.py": "print('made in chat-1')\n"},
            "command": ["python", "main.py"], "smoke": []})
        p, sup, events = make_presenter(tmp_path, completions=[toolset])
        p.set_active_chat("chat-1")
        p.submit_text("make a toolset that proves routing")
        p.set_active_chat("chat-2")     # the user moved on to another tab
        assert wait_for(lambda: any(
            k == "reply" and "tab-tool" in t for _c, k, t in events),
            timeout=10)
        done = [c for c, k, t in events if k == "reply" and "tab-tool" in t]
        assert done and all(c == "chat-1" for c in done)

    def test_new_chat_returns_id_and_switches(self, tmp_path):
        p, sup, events = make_presenter(tmp_path)
        cid = p.new_chat()
        assert cid.startswith("chat-")
        assert sup.active_chat == cid


class TestTabbedWindow:
    def test_tabs_isolate_transcripts(self, tmp_path, monkeypatch):
        pytest.importorskip("PySide6")
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from rita.gui.main_window import RitaWindow

        app = QApplication.instance() or QApplication([])
        p, sup, _ = make_presenter(tmp_path)
        w = RitaWindow(p)
        try:
            assert w.chat_tabs.count() >= 1
            first = w.chat_tabs.widget(0)
            w._add_chat_tab_clicked()
            assert w.chat_tabs.count() == 2
            second = w.chat_tabs.widget(1)
            w.chat_tabs.setCurrentIndex(1)
            second.prompt.setText("list your toolsets")
            second._send()
            deadline = time.time() + 5
            while time.time() < deadline:
                app.processEvents()
                if "toolset" in second.transcript.toPlainText().lower():
                    break
                time.sleep(0.02)
            assert "toolset" in second.transcript.toPlainText().lower()
            assert first.transcript.toPlainText().strip() == ""
        finally:
            w.close()

    def test_each_tab_shows_its_own_workspace(self, tmp_path, monkeypatch):
        pytest.importorskip("PySide6")
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from rita.gui.main_window import RitaWindow

        app = QApplication.instance() or QApplication([])
        p, sup, _ = make_presenter(tmp_path)
        repo = tmp_path / "other-repo"
        repo.mkdir()
        w = RitaWindow(p)
        try:
            w._add_chat_tab_clicked()
            second = w.chat_tabs.widget(1)
            w.chat_tabs.setCurrentIndex(1)
            second.bind_edit.setText(str(repo))
            second._bind()
            deadline = time.time() + 5
            while time.time() < deadline:
                app.processEvents()
                if str(repo) in second.workspace_label.text():
                    break
                time.sleep(0.02)
            assert str(repo) in second.workspace_label.text()
            first = w.chat_tabs.widget(0)
            assert str(repo) not in first.workspace_label.text()
        finally:
            w.close()
