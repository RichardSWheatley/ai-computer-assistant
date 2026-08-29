"""Path pickers: every box that takes a path gets a browse button —
nobody should have to hand-type C:\\ paths (the owner's request, made
for the chat-bind field and audited across the app)."""

from __future__ import annotations

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


def pick_dir(monkeypatch, path):
    from rita.gui import pickers
    monkeypatch.setattr(pickers.QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: path))


def pick_file(monkeypatch, path):
    from rita.gui import pickers
    monkeypatch.setattr(pickers.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (path, "")))


class TestChatBindPicker:
    def test_folder_picker_fills_the_bind_field(self, tmp_path, app,
                                                monkeypatch):
        w, p = make_window(tmp_path, app)
        try:
            tab = w.chat_tabs.widget(0)
            assert hasattr(tab, "bind_pick")     # the button exists
            pick_dir(monkeypatch, "C:/repos/sensor-fw")
            tab.bind_pick.click()
            assert tab.bind_edit.text() == "C:/repos/sensor-fw"
        finally:
            p.close()
            w.close()

    def test_cancelled_picker_leaves_the_field_alone(self, tmp_path, app,
                                                     monkeypatch):
        w, p = make_window(tmp_path, app)
        try:
            tab = w.chat_tabs.widget(0)
            tab.bind_edit.setText("https://example.com/x.git")
            pick_dir(monkeypatch, "")            # user pressed Cancel
            tab.bind_pick.click()
            assert tab.bind_edit.text() == "https://example.com/x.git"
        finally:
            p.close()
            w.close()


class TestSettingsPickers:
    def test_coder_picker_quotes_spaced_paths(self, tmp_path, app,
                                              monkeypatch):
        w, p = make_window(tmp_path, app)
        try:
            sp = w.settings_page
            assert hasattr(sp, "coder_pick")
            pick_file(monkeypatch,
                      r"C:/Users/richa/App Data/npm/claude.CMD")
            sp.coder_pick.click()
            # A spaced path arrives quoted so split_command keeps it whole.
            assert sp.coder_edit.text() == \
                '"C:/Users/richa/App Data/npm/claude.CMD"'
        finally:
            p.close()
            w.close()

    def test_compiler_and_cerberus_pickers_exist(self, tmp_path, app,
                                                 monkeypatch):
        w, p = make_window(tmp_path, app)
        try:
            sp = w.settings_page
            pick_file(monkeypatch, "/opt/gcc/bin/arm-none-eabi-gcc")
            sp.host_cc_pick.click()
            assert sp.host_cc_edit.text() == "/opt/gcc/bin/arm-none-eabi-gcc"
            sp.cerberus_pick.click()
            assert "/opt/gcc/bin/arm-none-eabi-gcc" in sp.cerberus_edit.text()
        finally:
            p.close()
            w.close()


class TestSettingsWorkspacePickers:
    def test_default_workspace_gets_a_dir_picker(self, tmp_path, app,
                                                 monkeypatch):
        w, p = make_window(tmp_path, app)
        try:
            sp = w.settings_page
            assert hasattr(sp, "workspace_pick")
            pick_dir(monkeypatch, "C:/zephyrproject")
            sp.workspace_pick.click()
            assert sp.workspace_edit.text() == "C:/zephyrproject"
        finally:
            p.close()
            w.close()

    def test_hardware_map_gets_a_file_picker(self, tmp_path, app,
                                             monkeypatch):
        w, p = make_window(tmp_path, app)
        try:
            sp = w.settings_page
            assert hasattr(sp, "map_pick")
            pick_file(monkeypatch, "C:/maps/map.yaml")
            sp.map_pick.click()
            assert sp.map_edit.text() == "C:/maps/map.yaml"
        finally:
            p.close()
            w.close()
