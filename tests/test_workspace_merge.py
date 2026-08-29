"""Each chat tab owns its workspace, so the standalone Workspace page
is gone (the owner's question: "If each tab has its own workspace, why
do we still have a workspace tab?"). Sync lives in the tab strip; the
default workspace and the twister hardware map are Settings."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


@pytest.fixture()
def app(monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def make_window(tmp_path, app):
    from rita.config import RitaConfig
    from rita.gui.main_window import RitaWindow
    from rita.gui.presenter import GuiPresenter
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                         auto_setup=False,
                                         ai_routing=False),
                     config_path=tmp_path / "config", tts=FakeTTS(),
                     workdir=tmp_path / "work")
    p = GuiPresenter(sup)
    return RitaWindow(p), p


class TestWorkspacePageIsGone:
    def test_no_workspace_page_and_no_workspace_nav_entry(self, tmp_path,
                                                          app):
        w, p = make_window(tmp_path, app)
        try:
            assert not hasattr(w, "workspace_page")
            labels = [b.text() for b in w._nav_buttons]
            assert "Workspace" not in labels
            assert labels == ["Chat", "Projects", "Modules", "Settings"]
        finally:
            p.close()
            w.close()

    def test_settings_holds_default_workspace_and_map(self, tmp_path, app):
        w, p = make_window(tmp_path, app)
        try:
            sp = w.settings_page
            assert sp.workspace_edit.text() == str(WS)
            sp.map_edit.setText("C:/maps/map.yaml")
            sp._save()
            assert p.sup.cfg.hardware_map == "C:/maps/map.yaml"
        finally:
            p.close()
            w.close()


class TestChatTabSync:
    def test_sync_button_syncs_this_chats_workspace(self, tmp_path, app):
        w, p = make_window(tmp_path, app)
        try:
            replies: list[str] = []
            w.sig_chat_event.connect(
                lambda cid, kind, text:
                kind == "reply" and replies.append(text))
            tab = w.chat_tabs.widget(0)
            assert hasattr(tab, "sync_btn")
            tab.sync_btn.click()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                app.processEvents()
                if any("board" in r for r in replies):
                    break
                time.sleep(0.02)
            assert any("board" in r for r in replies), replies
        finally:
            p.close()
            w.close()

    def test_sync_on_generic_bound_folder_is_honest(self, tmp_path, app):
        w, p = make_window(tmp_path, app)
        try:
            from rita.learning import chats

            plain = tmp_path / "plain-repo"
            plain.mkdir()
            tab = w.chat_tabs.widget(0)
            chats.bind(str(plain), tab.chat_id)
            replies: list[str] = []
            p.on_chat_event = (lambda cid, kind, text:
                               kind == "reply" and replies.append(text))
            p.sync_chat(tab.chat_id)
            assert any("isn't a Zephyr workspace" in r for r in replies), \
                replies
        finally:
            p.close()
            w.close()

    def test_sync_with_no_workspace_names_the_fix(self, tmp_path, app):
        from rita.config import RitaConfig
        from rita.gui.presenter import GuiPresenter
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS

        sup = Supervisor(rita_cfg=RitaConfig(workspace=None,
                                             auto_setup=False,
                                             ai_routing=False),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        p = GuiPresenter(sup)
        try:
            replies: list[str] = []
            p.on_chat_event = (lambda cid, kind, text:
                               kind == "reply" and replies.append(text))
            p.sync_chat()
            assert any("Settings" in r for r in replies), replies
        finally:
            p.close()
