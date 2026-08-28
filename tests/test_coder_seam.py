"""The coding-agent seam: vendor-neutral, command-as-config."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def make_supervisor(tmp_path, **cfg_kw):
    from rita.config import RitaConfig
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    return Supervisor(rita_cfg=RitaConfig(workspace=str(WS), **cfg_kw),
                      config_path=tmp_path / "config", tts=FakeTTS(),
                      workdir=tmp_path / "work")


class TestCommandAsConfig:
    def test_unconfigured_coder_answers_work_honestly(self, tmp_path,
                                                      monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        sup = make_supervisor(tmp_path)          # no coder_command, no inject
        said = sup.shell.handle_typed("build blinky")
        assert "coding agent" in said.lower()
        assert "settings" in said.lower()
        assert sup.manager.tasks() == []          # no task started

    def test_unconfigured_coder_answers_handoff_honestly(self, tmp_path,
                                                         monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        sup = make_supervisor(tmp_path)
        said = sup.shell.handle_typed("start a project: bring up the board "
                                      "and document it")
        assert "coding agent" in said.lower()
        assert sup.manager.tasks() == []

    def test_configured_command_reaches_the_cli_argv(self, tmp_path):
        from rita.firmware.coder import CoderCli
        sup = make_supervisor(tmp_path, coder_command="python /tools/agent.py")
        coder = sup._make_coder()
        assert isinstance(coder, CoderCli)
        assert coder.command == ("python", "/tools/agent.py")

    def test_injected_worker_bypasses_config(self, tmp_path):
        from rita.firmware.coder import FakeCoder
        from rita.config import RitaConfig
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        fake = FakeCoder()
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS)),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         coder=fake, workdir=tmp_path / "work")
        assert sup._make_coder() is fake


class TestFailedTasksReportTheError:
    def test_task_summary_carries_the_exception(self, tmp_path):
        sup = make_supervisor(tmp_path)
        tid = sup.manager.submit("boom", lambda ctl: 1 / 0)
        assert sup.manager.wait_state(tid, "FAILED", timeout=5)
        said = sup.task_summary(tid)
        assert "failed" in said.lower()
        assert "ZeroDivisionError" in said       # the reason, not just "failed"


class TestStatusHonesty:
    def test_status_false_when_unconfigured(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.gui.presenter import GuiPresenter
        p = GuiPresenter(make_supervisor(tmp_path))
        try:
            assert p.status().coder_cli is False
        finally:
            p.close()

    def test_status_true_for_resolvable_command(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        import sys
        from rita.gui.presenter import GuiPresenter
        p = GuiPresenter(make_supervisor(
            tmp_path, coder_command=f'"{sys.executable}" -p'))
        try:
            assert p.status().coder_cli is True
        finally:
            p.close()
