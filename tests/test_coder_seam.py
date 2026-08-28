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


class TestWindowsLauncherShims:
    """npm/pip CLIs on Windows are .cmd shims; CreateProcess won't resolve
    a bare name the way a shell does. Every external command resolves its
    executable through shutil.which at invocation — and a missing one
    fails naming the executable, never with a bare WinError 2."""

    def test_resolve_argv_resolves_argv0_keeps_args(self, monkeypatch):
        from rita.firmware import static_check
        monkeypatch.setattr(static_check.shutil, "which",
                            lambda n: f"/resolved/{n}.cmd")
        assert static_check.resolve_argv(["agent", "-p"]) == \
            ["/resolved/agent.cmd", "-p"]

    def test_resolve_argv_missing_names_the_executable(self, monkeypatch):
        from rita.firmware import static_check
        monkeypatch.setattr(static_check.shutil, "which", lambda n: None)
        with pytest.raises(FileNotFoundError, match="agent"):
            static_check.resolve_argv(["agent", "-p"])

    def test_coder_cli_invokes_the_resolved_executable(self, tmp_path,
                                                       monkeypatch):
        from rita.firmware import coder, static_check
        monkeypatch.setattr(static_check.shutil, "which",
                            lambda n: f"/resolved/{n}.cmd")
        seen = {}

        def fake_run(args, **kw):
            seen["args"] = args
            class P:  # minimal CompletedProcess stand-in
                returncode, stdout, stderr = 0, "ok", ""
            return P()

        monkeypatch.setattr(coder.subprocess, "run", fake_run)
        cli = coder.CoderCli(tmp_path, ("agent", "-p"))
        cli.complete("hello")
        assert seen["args"][0] == "/resolved/agent.cmd"

    def test_west_cli_invokes_the_resolved_executable(self, tmp_path,
                                                      monkeypatch):
        from rita.firmware import static_check, west
        monkeypatch.setattr(static_check.shutil, "which",
                            lambda n: f"/resolved/{n}.exe")
        seen = {}

        def fake_run(args, **kw):
            seen["args"] = args
            class P:
                returncode, stdout, stderr = 0, "", ""
            return P()

        monkeypatch.setattr(west.subprocess, "run", fake_run)
        west.WestCli(tmp_path)._run(["build"])
        assert seen["args"][0] == "/resolved/west.exe"


class TestCoderOutputHonesty:
    """An agent that exits nonzero or prints nothing must fail NAMING the
    agent and its stderr — never hand '' downstream to crash a JSON parse."""

    def test_empty_output_raises_with_stderr(self, tmp_path, monkeypatch):
        from rita.firmware import coder, static_check
        monkeypatch.setattr(static_check.shutil, "which", lambda n: f"/x/{n}")

        def fake_run(args, **kw):
            class P:
                returncode, stdout, stderr = 1, "", "login required"
            return P()

        monkeypatch.setattr(coder.subprocess, "run", fake_run)
        cli = coder.CoderCli(tmp_path, ("agent", "-p"))
        with pytest.raises(RuntimeError) as exc:
            cli.complete("judge fit")
        assert "coding agent" in str(exc.value)
        assert "login required" in str(exc.value)

    def test_good_output_passes_through(self, tmp_path, monkeypatch):
        from rita.firmware import coder, static_check
        monkeypatch.setattr(static_check.shutil, "which", lambda n: f"/x/{n}")

        def fake_run(args, **kw):
            class P:
                returncode, stdout, stderr = 0, '{"fit": "none"}', ""
            return P()

        monkeypatch.setattr(coder.subprocess, "run", fake_run)
        assert coder.CoderCli(tmp_path, ("agent", "-p")).complete("x") == \
            '{"fit": "none"}'


class TestFrozenMcpConfig:
    def test_frozen_install_points_mcp_at_the_cli_exe(self, tmp_path,
                                                      monkeypatch):
        # In a packaged install sys.executable is the GUI exe, which can't
        # run `-m rita`; mcp.json must point at the bundled console CLI.
        import json as _json
        import sys

        from rita.firmware.sync import _write_mcp_config
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        bundle = tmp_path / "app"
        bundle.mkdir()
        (bundle / "rita.exe").write_text("")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(bundle / "RitaApp.exe"))
        _write_mcp_config(tmp_path / "ws")
        cfg = _json.loads((tmp_path / "rita" / "mcp.json").read_text())
        server = cfg["mcpServers"]["rita-workspace"]
        assert server["command"] == str(bundle / "rita.exe")
        assert server["args"][0] == "mcp-serve"


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
