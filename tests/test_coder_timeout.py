"""A hung coding agent must not kill the task with a raw TimeoutExpired
(the owner's paste: 'Task task-2 failed: TimeoutExpired ... timed out
after 600.0 seconds' — no evidence, no retry, and a ceiling too short
for real coding steps). The rules: the ceiling is config, a timeout is
retried once, and a double timeout reports the partial output."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def make_cli(timeout=600.0):
    from rita.firmware.coder import CoderCli

    # A real executable: resolve_argv verifies argv[0] exists on PATH.
    return CoderCli(WS, command=(sys.executable,), timeout=timeout)


def expired(partial_out=b"halfway through the plan", partial_err=b""):
    return subprocess.TimeoutExpired(cmd=["agent"], timeout=600,
                                     output=partial_out, stderr=partial_err)


class TestTimeoutHandling:
    def test_double_timeout_reports_evidence_not_a_traceback(self,
                                                             monkeypatch):
        cli = make_cli(timeout=600.0)
        calls = []

        def fake_run(*a, **k):
            calls.append(a)
            raise expired()

        monkeypatch.setattr("rita.firmware.coder.subprocess.run", fake_run)
        with pytest.raises(RuntimeError) as e:
            cli.complete("do the thing")
        msg = str(e.value)
        assert len(calls) == 2                    # retried exactly once
        assert "600" in msg                       # the ceiling, named
        assert "halfway through the plan" in msg  # partial output quoted
        assert "Settings" in msg                  # the fix, named

    def test_timeout_then_success_recovers(self, monkeypatch):
        cli = make_cli()
        attempts = []

        def fake_run(*a, **k):
            attempts.append(a)
            if len(attempts) == 1:
                raise expired()
            return subprocess.CompletedProcess(
                args=a, returncode=0, stdout="recovered fine", stderr="")

        monkeypatch.setattr("rita.firmware.coder.subprocess.run", fake_run)
        assert "recovered fine" in cli.complete("do the thing")
        assert len(attempts) == 2

    def test_cutoff_is_narrated(self, monkeypatch):
        cli = make_cli(timeout=300.0)
        notes = []
        cli.on_activity = notes.append

        def fake_run(*a, **k):
            raise expired()

        monkeypatch.setattr("rita.firmware.coder.subprocess.run", fake_run)
        with pytest.raises(RuntimeError):
            cli.complete("do the thing")
        assert any("300" in n and "cut off" in n for n in notes), notes


class TestConfiguredCeiling:
    def test_supervisor_passes_the_configured_ceiling(self, tmp_path):
        from rita.config import RitaConfig
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS

        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                             coder_command="agent",
                                             coder_timeout_seconds=1234,
                                             auto_setup=False,
                                             ai_routing=False),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        assert sup._make_coder().timeout == 1234

    def test_settings_spinbox_round_trips(self, tmp_path, monkeypatch):
        pytest.importorskip("PySide6")
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from rita.config import RitaConfig, load_rita_config
        from rita.gui.main_window import RitaWindow
        from rita.gui.presenter import GuiPresenter
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS

        app = QApplication.instance() or QApplication([])
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                             auto_setup=False,
                                             ai_routing=False),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        p = GuiPresenter(sup)
        w = RitaWindow(p)
        try:
            sp = w.settings_page
            sp.coder_timeout.setValue(2400)
            sp._save()
            assert sup.cfg.coder_timeout_seconds == 2400
            back = load_rita_config(tmp_path / "config")
            assert back.coder_timeout_seconds == 2400
        finally:
            p.close()
            w.close()
