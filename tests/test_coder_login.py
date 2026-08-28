"""The coding-agent login belongs to RITA: one click opens the window.

Nothing runs via command line — the user never types the login command;
RITA launches the agent's own interactive flow in a visible console.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


class TestLaunchLogin:
    def _capture(self, monkeypatch):
        from rita.firmware import coder, static_check
        monkeypatch.setattr(static_check.shutil, "which",
                            lambda n: f"/x/{n}")
        seen = {}

        def fake_popen(argv, **kw):
            seen["argv"] = argv
            seen["kw"] = kw
            class P:
                pid = 1234
            return P()

        monkeypatch.setattr(coder.subprocess, "Popen", fake_popen)
        return seen

    def test_bare_agent_when_no_login_command(self, monkeypatch):
        from rita.config import RitaConfig
        from rita.firmware.coder import launch_login
        seen = self._capture(monkeypatch)
        msg = launch_login(RitaConfig(coder_command="agent -p"))
        assert seen["argv"][-1].endswith("agent")     # bare, no -p
        assert "-p" not in seen["argv"]
        assert "login" in msg.lower() and "window" in msg.lower()

    def test_explicit_login_command_wins(self, monkeypatch):
        from rita.config import RitaConfig
        from rita.firmware.coder import launch_login
        seen = self._capture(monkeypatch)
        launch_login(RitaConfig(coder_command="agent -p",
                                coder_login_command="agent auth-login"))
        assert seen["argv"][-2:] == ["/x/agent", "auth-login"] or \
            seen["argv"][-1] == "auth-login"

    def test_windows_opens_its_own_console(self, monkeypatch):
        from rita.config import RitaConfig
        from rita.firmware import coder
        from rita.firmware.coder import launch_login
        seen = self._capture(monkeypatch)
        monkeypatch.setattr(coder, "_is_windows", lambda: True)
        monkeypatch.setattr(coder.subprocess, "CREATE_NEW_CONSOLE", 0x10,
                            raising=False)
        launch_login(RitaConfig(coder_command="agent -p"))
        assert seen["kw"].get("creationflags") == 0x10

    def test_unconfigured_coder_is_honest_and_launches_nothing(self,
                                                               monkeypatch):
        from rita.config import RitaConfig
        from rita.firmware.coder import launch_login
        seen = self._capture(monkeypatch)
        msg = launch_login(RitaConfig())
        assert "settings" in msg.lower()
        assert "argv" not in seen                      # nothing launched

    def test_missing_executable_is_named(self, monkeypatch):
        from rita.config import RitaConfig
        from rita.firmware import coder, static_check
        from rita.firmware.coder import launch_login
        monkeypatch.setattr(static_check.shutil, "which", lambda n: None)
        msg = launch_login(RitaConfig(coder_command="ghost -p"))
        assert "ghost" in msg


class TestPresenterButton:
    def test_login_coder_emits_the_message(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import RitaConfig
        from rita.firmware import coder, static_check
        from rita.gui.presenter import GuiPresenter
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        monkeypatch.setattr(static_check.shutil, "which", lambda n: f"/x/{n}")
        monkeypatch.setattr(coder.subprocess, "Popen",
                            lambda *a, **k: type("P", (), {"pid": 1})())
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                             coder_command="agent -p"),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        p = GuiPresenter(sup)
        replies = []
        p.on_reply = replies.append
        try:
            p.login_coder()
            assert any("login" in r.lower() for r in replies)
        finally:
            p.close()


class TestAuthHintsPointAtTheButton:
    def test_task_failure_names_the_settings_button(self, tmp_path,
                                                    monkeypatch):
        from rita.firmware import coder, static_check
        monkeypatch.setattr(static_check.shutil, "which", lambda n: f"/x/{n}")

        def fake_run(args, **kw):
            class P:
                returncode, stdout, stderr = 1, "OAuth session expired", ""
            return P()

        monkeypatch.setattr(coder.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError) as exc:
            coder.CoderCli(tmp_path, ("agent", "-p")).complete("x")
        msg = str(exc.value).lower()
        assert "log in coding agent" in msg and "settings" in msg
        assert "terminal" not in msg                   # never again
