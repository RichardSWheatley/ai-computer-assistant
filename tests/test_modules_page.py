"""The Modules page must never lose an install result.

One shared one-line label swallowed the ARM toolchain error under the
CERBERUS heading; a raising installer vanished entirely. Results are now
an append-only log naming the tool, and exceptions land there too.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def wait_for(app, cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture()
def page(tmp_path, monkeypatch):
    monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
    from PySide6.QtWidgets import QApplication

    from rita.config import RitaConfig
    from rita.gui.modules_page import ModulesPage
    from rita.gui.presenter import GuiPresenter
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    app = QApplication.instance() or QApplication([])
    sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS)),
                     config_path=tmp_path / "config", tts=FakeTTS(),
                     workdir=tmp_path / "work")
    presenter = GuiPresenter(sup)
    screen = []
    presenter.on_screen = screen.append
    w = ModulesPage(presenter)
    yield app, w, screen
    presenter.close()
    w.deleteLater()


class TestInstallLog:
    def test_failure_detail_is_appended_and_named(self, page, monkeypatch):
        app, w, screen = page
        from rita.firmware.cerberus_setup import InstallResult
        import rita.gui.modules_page as mp
        monkeypatch.setattr(
            "rita.firmware.toolchain.install_arm_gcc",
            lambda *a, **k: InstallResult(
                ok=False, path="x", detail="download failed: HTTP 404"))
        w._install_toolchain()
        assert wait_for(app, lambda: "HTTP 404" in w.log.toPlainText())
        text = w.log.toPlainText()
        assert "ARM toolchain" in text            # named, not anonymous
        # And it reaches the chat screen pane, so it is never lost.
        assert any("HTTP 404" in s for s in screen)

    def test_messages_append_never_overwrite(self, page, monkeypatch):
        app, w, screen = page
        from rita.firmware.cerberus_setup import InstallResult
        monkeypatch.setattr(
            "rita.firmware.unity.install_unity",
            lambda *a, **k: InstallResult(ok=True, path="u", detail="Unity ok"))
        monkeypatch.setattr(
            "rita.firmware.toolchain.install_arm_gcc",
            lambda *a, **k: InstallResult(ok=False, path="t",
                                          detail="toolchain boom"))
        w._install_unity()
        assert wait_for(app, lambda: "Unity ok" in w.log.toPlainText())
        w._install_toolchain()
        assert wait_for(app, lambda: "toolchain boom" in w.log.toPlainText())
        text = w.log.toPlainText()
        assert "Unity ok" in text                  # still there

    def test_raising_installer_lands_in_the_log(self, page, monkeypatch):
        app, w, screen = page

        def boom(*a, **k):
            raise RuntimeError("cert store exploded")

        monkeypatch.setattr("rita.firmware.toolchain.install_arm_gcc", boom)
        w._install_toolchain()
        assert wait_for(app, lambda: "cert store exploded"
                        in w.log.toPlainText())
        assert "FAILED" in w.log.toPlainText()
        # Button re-enabled for a retry.
        assert wait_for(app, lambda: w.toolchain_btn.isEnabled())
