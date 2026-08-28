"""Zephyr facts come from the ACTUAL workspace install — never baked in.

The version is read from the checkout's zephyr/VERSION file at sync; board
answers in chat come from the synced boards.json; the MCP server serves the
same facts to the coder-worker.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


class TestWorkspaceInfo:
    def test_version_read_from_the_checkout(self):
        from rita.firmware.workspace import read_workspace_info
        info = read_workspace_info(WS)
        assert info["zephyr_version"] == "4.1.0"     # from zephyr/VERSION
        assert info["zephyr_base"].endswith("zephyr")

    def test_extraversion_is_appended(self, tmp_path):
        from rita.firmware.workspace import read_workspace_info
        z = tmp_path / "zephyr"
        z.mkdir()
        (z / "VERSION").write_text("VERSION_MAJOR = 4\nVERSION_MINOR = 2\n"
                                   "PATCHLEVEL = 0\nVERSION_TWEAK = 0\n"
                                   "EXTRAVERSION = rc1\n")
        assert read_workspace_info(tmp_path)["zephyr_version"] == "4.2.0-rc1"

    def test_missing_version_file_is_reported_not_invented(self, tmp_path):
        from rita.firmware.workspace import read_workspace_info
        (tmp_path / "zephyr").mkdir()
        assert read_workspace_info(tmp_path)["zephyr_version"] is None

    def test_boards_json_carries_workspace_facts(self):
        from rita.firmware.boards import build_boards_json
        data = build_boards_json(WS)
        assert data["zephyr_version"] == "4.1.0"
        assert data["generated_at"]                  # sync timestamp recorded

    def test_sync_persists_the_version(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.firmware.sync import sync_workspace
        sync_workspace(WS)
        saved = json.loads((tmp_path / "rita" / "boards.json").read_text())
        assert saved["zephyr_version"] == "4.1.0"


class TestMcpWorkspaceInfo:
    def test_tool_serves_actual_facts(self):
        from rita.mcpserver.tools import WorkspaceTools
        info = WorkspaceTools(WS).workspace_info()
        assert info["zephyr_version"] == "4.1.0"
        assert info["boards"] >= 2
        assert info["indexed_suites"] >= 4


class TestChatAnswersFromWorkspace:
    def make_supervisor(self, tmp_path):
        from rita.config import RitaConfig
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        return Supervisor(rita_cfg=RitaConfig(workspace=str(WS)),
                          config_path=tmp_path / "config", tts=FakeTTS(),
                          workdir=tmp_path / "work")

    def test_tell_me_about_a_board_answers_from_synced_data(self, tmp_path):
        sup = self.make_supervisor(tmp_path)
        sup.shell.handle("hello rita")
        said = sup.shell.handle("tell me about the apollo510")
        assert "ambiq" in said.lower()               # from the actual board.yml
        assert "arm" in said.lower()                 # from the platform yaml
        assert "gpio" in said.lower()                # actual supported list

    def test_zephyr_version_question_answers_from_the_install(self, tmp_path):
        sup = self.make_supervisor(tmp_path)
        sup.shell.handle("hello rita")
        said = sup.shell.handle("what zephyr version are we on")
        assert "4.1.0" in said

    def test_unknown_topic_still_falls_back(self, tmp_path):
        sup = self.make_supervisor(tmp_path)
        sup.shell.handle("hello rita")
        said = sup.shell.handle("tell me about quantum entanglement")
        assert said                                   # a reply, not silence
        assert "4.1.0" not in said
