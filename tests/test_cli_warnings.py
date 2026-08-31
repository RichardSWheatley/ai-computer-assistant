"""The agent CLI's own configuration warnings must surface in 'check
setup', not hide until they pollute a failure dump. The owner's live
trace: their agent printed 'Permission allow rule … has a wildcard …'
on stderr of EVERY call, and the first time anyone saw it was inside a
timeout's partial-output evidence."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"

WARNING = ("Permission allow rule (..\\.claude\\settings.json): "
           "Bash(grep -nB2 *) has a wildcard before the rest of the "
           "command")


def fake_agent(stdout: str, stderr: str):
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=stdout,
                                           stderr=stderr)
    return run


class TestStderrIsKept:
    def test_run_records_the_last_stderr(self, monkeypatch):
        from rita.firmware.coder import CoderCli

        cli = CoderCli(WS, command=(sys.executable,))
        monkeypatch.setattr("rita.firmware.coder.subprocess.run",
                            fake_agent("ok", WARNING))
        cli.complete("hello")
        assert "wildcard" in cli.last_stderr


class TestLiveCheckSurfacesWarnings:
    def make_cfg(self):
        from rita.config import RitaConfig

        return RitaConfig(workspace=str(WS), coder_command=sys.executable)

    def test_warnings_ride_along_on_a_green_check(self, monkeypatch):
        from rita import diagnostics

        monkeypatch.setattr(
            "rita.firmware.coder.subprocess.run",
            fake_agent("INTACT LANTERN", WARNING))
        check = diagnostics._coder_live(self.make_cfg())
        assert check.ok                      # transport is still fine
        assert "warning" in check.detail.lower()
        assert "wildcard" in check.detail    # the evidence, quoted

    def test_clean_stderr_stays_quiet(self, monkeypatch):
        from rita import diagnostics

        monkeypatch.setattr(
            "rita.firmware.coder.subprocess.run",
            fake_agent("INTACT LANTERN", ""))
        check = diagnostics._coder_live(self.make_cfg())
        assert check.ok
        assert "warning" not in check.detail.lower()
