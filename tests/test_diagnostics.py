"""Diagnostics: RITA checks her own setup, from inside the app."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


class TestChecks:
    def test_every_check_has_a_concrete_detail(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import RitaConfig
        from rita.diagnostics import run_checks
        checks = run_checks(RitaConfig(workspace=str(WS)))
        assert checks
        names = {c.name for c in checks}
        assert {"workspace", "coding agent", "workspace MCP", "voice",
                "west", "Zephyr SDK", "CERBERUS", "Unity"} <= names
        for c in checks:
            assert c.detail.strip(), c.name

    def test_unconfigured_pieces_are_not_ok_and_name_the_fix(self, tmp_path,
                                                             monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import RitaConfig
        from rita.diagnostics import run_checks
        by = {c.name: c for c in run_checks(RitaConfig())}
        assert by["workspace"].ok is False
        assert "workspace" in by["workspace"].detail.lower()
        assert by["coding agent"].ok is False
        assert "settings" in by["coding agent"].detail.lower()

    def test_deep_check_runs_the_agent_and_reports_its_output(self, tmp_path,
                                                              monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import RitaConfig
        from rita import diagnostics
        from rita.firmware import static_check
        monkeypatch.setattr(static_check.shutil, "which", lambda n: f"/x/{n}")

        def fake_run(args, **kw):
            class P:
                returncode, stdout, stderr = 1, "Invalid API key", ""
            return P()

        monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)
        by = {c.name: c for c in run_deep(diagnostics,
                                          RitaConfig(workspace=str(WS),
                                                     coder_command="agent -p"))}
        smoke = by["coding agent (live)"]
        assert smoke.ok is False
        assert "Invalid API key" in smoke.detail       # what it really said
        assert "1" in smoke.detail                      # the exit code


def run_deep(diagnostics, cfg):
    return diagnostics.run_checks(cfg, deep=True)


class TestReportRouting:
    @pytest.mark.parametrize("text", ["check setup", "run diagnostics",
                                      "check your setup"])
    def test_setup_phrases_reach_the_report(self, tmp_path, text, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import RitaConfig
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS)),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        said = sup.shell.handle_typed(text)
        assert "workspace" in said.lower()
        assert "coding agent" in said.lower()
        assert sup.manager.tasks() == []          # a report, never a task


class TestCoderFailureIsQuoted:
    def test_error_carries_argv_exit_code_and_both_streams(self, tmp_path,
                                                           monkeypatch):
        from rita.firmware import coder, static_check
        monkeypatch.setattr(static_check.shutil, "which", lambda n: f"/x/{n}")

        def fake_run(args, **kw):
            class P:
                returncode, stdout, stderr = 1, "MCP server failed", "boom"
            return P()

        monkeypatch.setattr(coder.subprocess, "run", fake_run)
        cli = coder.CoderCli(tmp_path, ("agent", "-p"))
        with pytest.raises(RuntimeError) as exc:
            cli.complete("x")
        msg = str(exc.value)
        assert "agent" in msg and "1" in msg
        assert "MCP server failed" in msg          # stdout, not just stderr
        assert "boom" in msg


class TestMcpNeverBlocksCoding:
    def test_failed_mcp_invocation_retries_without_it(self, tmp_path,
                                                      monkeypatch):
        from rita.firmware import coder, static_check
        monkeypatch.setattr(static_check.shutil, "which", lambda n: f"/x/{n}")
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            used_mcp = "--mcp-config" in args

            class P:
                returncode = 1 if used_mcp else 0
                stdout = "" if used_mcp else "GOOD"
                stderr = "mcp server exited" if used_mcp else ""
            return P()

        monkeypatch.setattr(coder.subprocess, "run", fake_run)
        mcp = tmp_path / "mcp.json"
        mcp.write_text("{}")
        cli = coder.CoderCli(tmp_path, ("agent", "-p"), mcp_config=mcp)
        assert cli.complete("x") == "GOOD"          # work still gets done
        assert len(calls) == 2
        assert "--mcp-config" in calls[0] and "--mcp-config" not in calls[1]
        assert cli.mcp_fallback is True             # and it is recorded

    def test_clean_invocation_never_retries(self, tmp_path, monkeypatch):
        from rita.firmware import coder, static_check
        monkeypatch.setattr(static_check.shutil, "which", lambda n: f"/x/{n}")
        calls = []

        def fake_run(args, **kw):
            calls.append(args)

            class P:
                returncode, stdout, stderr = 0, "FINE", ""
            return P()

        monkeypatch.setattr(coder.subprocess, "run", fake_run)
        mcp = tmp_path / "mcp.json"
        mcp.write_text("{}")
        cli = coder.CoderCli(tmp_path, ("agent", "-p"), mcp_config=mcp)
        assert cli.complete("x") == "FINE"
        assert len(calls) == 1
        assert cli.mcp_fallback is False


class TestMcpSdkCompat:
    """mcp 2.x renamed FastMCP to MCPServer. Importing the old name under
    2.x killed the server, which killed the agent that launches it."""

    def test_server_class_resolves_on_the_installed_sdk(self):
        pytest.importorskip("mcp")
        from rita.mcpserver.server import _server_class, mcp_available
        cls = _server_class()
        assert cls.__name__ in ("MCPServer", "FastMCP")
        assert mcp_available() is True

    def test_server_builds_with_every_tool_registered(self):
        pytest.importorskip("mcp")
        import asyncio

        from rita.mcpserver.server import build_server
        srv = build_server(WS)
        names = {t.name for t in asyncio.run(srv.list_tools())}
        assert {"workspace_info", "find_verification", "board_info",
                "zephyr_howto", "sample_lookup"} <= names

    def test_available_is_false_when_neither_class_exists(self, monkeypatch):
        from rita.mcpserver import server

        def boom():
            raise ImportError("no server class")

        monkeypatch.setattr(server, "_server_class", boom)
        assert server.mcp_available() is False


class TestPackagedDependencies:
    def test_spec_collects_dynamically_imported_packages(self):
        spec = (Path(__file__).resolve().parents[1]
                / "packaging" / "rita.spec").read_text()
        # `mcp` is imported inside a function, so PyInstaller can't see it:
        # without explicit collection `rita.exe mcp-serve` dies in a frozen
        # install and the coding agent's MCP startup fails.
        assert "mcp" in spec and "collect_all" in spec
        for pkg in ("sounddevice", "faster_whisper"):
            assert pkg in spec, pkg
