"""Zephyr knowledge pack: shipped conventions, deterministically retrieved.

Facts about the user's install still come only from the workspace; this
pack carries HOW-Zephyr-works knowledge, each topic citing its source.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"


# --- Pack integrity ----------------------------------------------------------

class TestPack:
    def test_index_and_files_agree(self):
        from rita.firmware import knowledge
        topics = knowledge.list_topics()
        assert {"building-apps", "app-locations", "west-commands", "twister",
                "ztest", "devicetree-overlays", "mspi", "psram",
                "flash-and-debug", "sdk"} <= set(t["topic"] for t in topics)
        for t in topics:
            text = knowledge.get_topic(t["topic"])
            assert text.strip(), t["topic"]
            # Every topic cites its source (Zephyr docs, SEI CERT, Unity...).
            assert "http" in text, f"{t['topic']} must cite its source"
            assert t["keywords"], t["topic"]

    def test_match_topics_is_deterministic_keyword_overlap(self):
        from rita.firmware import knowledge
        names = [t for t in knowledge.match_topics(["mspi", "psram", "hex"])]
        assert names[0] in ("mspi", "psram")
        assert set(names[:2]) == {"mspi", "psram"}
        assert knowledge.match_topics(["quantum", "teleport"]) == []

    def test_notes_for_is_bounded_and_contains_content(self):
        from rita.firmware import knowledge
        notes = knowledge.notes_for(["mspi", "psram"], max_chars=4000)
        assert len(notes) <= 4000
        assert "mspi" in notes.lower()
        big = knowledge.notes_for(["mspi", "psram", "twister", "ztest"],
                                  max_chars=1500)
        assert len(big) <= 1500


# --- MCP exposure ------------------------------------------------------------

class TestMcpKnowledge:
    def test_zephyr_howto_and_list(self):
        from rita.mcpserver.tools import WorkspaceTools
        tools = WorkspaceTools(WS)
        assert any(t["topic"] == "twister" for t in tools.list_topics())
        text = tools.zephyr_howto("twister")
        assert "twister" in text.lower()
        assert tools.zephyr_howto("no-such-topic") is None


# --- Routing: the flagship utterance ----------------------------------------

class TestFlagshipRouting:
    def test_build_me_an_example_for_mspi_psram_scaffolds(self):
        from rita.routing.model import Utterance
        from rita.routing.router import route
        from rita.routing.vocabulary import Vocabulary
        d = route(Utterance.from_text(
            "Rita, please build me an example for MSPI that communicates "
            "with a PSRAM on MSPI0 in hex mode"), Vocabulary.seed())
        assert d.kind == "work"
        assert d.verb == "scaffold"          # new app, not a build of existing
        assert d.entities.peripheral in ("mspi", "psram")

    def test_build_of_an_existing_sample_stays_build(self):
        from rita.routing.model import Utterance
        from rita.routing.router import route
        from rita.routing.vocabulary import Vocabulary
        d = route(Utterance.from_text("build the blinky sample"),
                  Vocabulary.seed())
        assert d.verb == "build"             # names an existing sample


# --- Scaffold placement + prompt enrichment ----------------------------------

def blinky_fit(_p: str = "") -> str:
    return json.dumps({"fit": "sample.basic.blinky", "reason": "fits"})


# No indexed suite verifies mspi/psram, so the resolver correctly asks for
# test authorship — the fake returns a valid ztest bundle.
MSPI_TEST_FILES = json.dumps({
    "testcase.yaml": "tests:\n  app.mspi.psram:\n    tags: mspi psram\n    harness: ztest\n",
    "src/main.c": "#include <zephyr/ztest.h>\n",
    "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\n",
    "prj.conf": "CONFIG_ZTEST=y\n",
})


class TestScaffoldPlacement:
    def make_pipeline(self, tmp_path, apps_dir=None, completions=None):
        from rita.config import RitaConfig
        from rita.firmware.claude import FakeClaude
        from rita.firmware.index import VerificationIndex
        from rita.firmware.pipeline import IteratePipeline
        from rita.firmware.west import FakeWest
        cfg = RitaConfig(workspace=str(WS),
                         applications_dir=str(apps_dir) if apps_dir else None)
        runner = FakeWest(build_seq=["ok"], twister_seq=["pass.json"],
                          fixtures_dir=TW)
        claude = FakeClaude(completions=list(completions or [MSPI_TEST_FILES]))
        pipe = IteratePipeline(runner=runner, claude=claude,
                               index=VerificationIndex.build(WS), cfg=cfg,
                               workdir=tmp_path / "work")
        return pipe, runner, claude

    def test_scaffold_lands_in_applications_dir(self, tmp_path):
        pipe, runner, claude = self.make_pipeline(tmp_path,
                                                  apps_dir=tmp_path / "apps")
        report = pipe.run(goal="an example for mspi psram in hex mode",
                          board="apollo510_evb", terms=["mspi", "psram"],
                          scaffold=True)
        assert report.outcome == "green"
        app_dir = Path(claude.scaffolds_dirs[0])
        assert app_dir.is_relative_to(tmp_path / "apps")
        assert (app_dir / "CMakeLists.txt").exists()

    def test_default_applications_root_is_workspace_applications(self):
        from rita.config import RitaConfig
        from rita.firmware.pipeline import applications_root
        cfg = RitaConfig(workspace="/w")
        assert applications_root(cfg) == Path("/w") / "applications"
        cfg2 = RitaConfig(workspace="/w", applications_dir="/elsewhere")
        assert applications_root(cfg2) == Path("/elsewhere")

    def test_scaffold_prompt_carries_knowledge_notes(self, tmp_path):
        pipe, runner, claude = self.make_pipeline(tmp_path,
                                                  apps_dir=tmp_path / "apps")
        pipe.run(goal="an example for mspi psram in hex mode",
                 board="apollo510_evb", terms=["mspi", "psram"], scaffold=True)
        goal_seen = claude.scaffolds[0]
        assert "Zephyr notes" in goal_seen
        assert "mspi" in goal_seen.lower()


# --- SDK detection -----------------------------------------------------------

class TestSdkDetection:
    def test_env_var_wins_and_sdk_version_file_read(self, tmp_path, monkeypatch):
        from rita.firmware.workspace import read_sdk_info
        sdk = tmp_path / "zephyr-sdk-0.17.0"
        sdk.mkdir()
        (sdk / "sdk_version").write_text("0.17.0\n")
        monkeypatch.setenv("ZEPHYR_SDK_INSTALL_DIR", str(sdk))
        info = read_sdk_info()
        assert info == {"path": str(sdk), "version": "0.17.0"}

    def test_version_falls_back_to_dir_name(self, tmp_path, monkeypatch):
        from rita.firmware.workspace import read_sdk_info
        sdk = tmp_path / "zephyr-sdk-0.16.8"
        sdk.mkdir()
        monkeypatch.setenv("ZEPHYR_SDK_INSTALL_DIR", str(sdk))
        assert read_sdk_info()["version"] == "0.16.8"

    def test_home_scan_when_no_env(self, tmp_path, monkeypatch):
        from rita.firmware.workspace import read_sdk_info
        monkeypatch.delenv("ZEPHYR_SDK_INSTALL_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        sdk = tmp_path / "zephyr-sdk-0.17.2"
        sdk.mkdir()
        assert read_sdk_info()["version"] == "0.17.2"

    def test_absent_sdk_is_none_not_guessed(self, tmp_path, monkeypatch):
        from rita.firmware.workspace import read_sdk_info
        monkeypatch.delenv("ZEPHYR_SDK_INSTALL_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        assert read_sdk_info() is None

    def test_workspace_info_includes_sdk(self, tmp_path, monkeypatch):
        from rita.firmware.workspace import read_workspace_info
        sdk = tmp_path / "zephyr-sdk-0.17.0"
        sdk.mkdir()
        (sdk / "sdk_version").write_text("0.17.0")
        monkeypatch.setenv("ZEPHYR_SDK_INSTALL_DIR", str(sdk))
        info = read_workspace_info(WS)
        assert info["sdk"]["version"] == "0.17.0"


# --- Chat: how-do-I questions answer from the pack ---------------------------

class TestChatHowTo:
    def test_howto_question_answers_with_topic_summary(self, tmp_path):
        from rita.config import RitaConfig
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS)),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        said = sup.shell.handle_typed("how do I add a devicetree overlay")
        assert "overlay" in said.lower()
        assert "docs.zephyrproject.org" not in said   # summary, not the dump
