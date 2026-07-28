"""Fix 2: verification resolution (index -> fit judge -> write-the-test),
boards.json generation, and the workspace MCP tool implementations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


# --- Static index (pure data, no LLM) --------------------------------------

@pytest.fixture(scope="module")
def index():
    from aica.firmware.index import VerificationIndex
    return VerificationIndex.build(WS)


@pytest.fixture(scope="module")
def tools():
    from aica.mcpserver.tools import WorkspaceTools
    return WorkspaceTools(WS)


class TestVerificationIndex:
    def test_build_finds_samples_and_tests(self, index):
        ids = {e.id for e in index.entries}
        assert "sample.basic.blinky" in ids
        assert "sample.drivers.adc" in ids
        assert "kernel.semaphore" in ids
        kinds = {e.id: e.kind for e in index.entries}
        assert kinds["sample.basic.blinky"] == "sample"
        assert kinds["kernel.semaphore"] == "test"

    def test_entry_fields(self, index):
        blinky = next(e for e in index.entries if e.id == "sample.basic.blinky")
        assert blinky.path.endswith("samples/basic/blinky")
        assert "gpio" in [t.lower() for t in blinky.tags]
        assert blinky.harness == "led"
        assert blinky.platform_allow == ()          # allowed everywhere
        assert blinky.readme_path is not None
        adc = next(e for e in index.entries if e.id == "sample.drivers.adc")
        assert adc.platform_allow == ("nrf52840dk/nrf52840",)
        button = next(e for e in index.entries if e.id == "sample.basic.button")
        assert button.filter == 'dt_alias_exists("sw0")'   # recorded, not evaluated

    def test_known_sample_hit_blinky(self, index):
        # Acceptance: blinky -> samples/basic/blinky.
        hits = index.find("apollo510_evb", ["blinky", "led"])
        assert hits and hits[0].id == "sample.basic.blinky"

    def test_board_incompatible_sample_excluded(self, index):
        # Acceptance: adc allows only nrf52840dk -> excluded for apollo510.
        hits = index.find("apollo510_evb", ["adc"])
        assert all(e.id != "sample.drivers.adc" for e in hits)
        hits_nrf = index.find("nrf52840dk", ["adc"])
        assert any(e.id == "sample.drivers.adc" for e in hits_nrf)

    def test_no_terms_match_gives_empty(self, index):
        assert index.find("apollo510_evb", ["quantum", "teleport"]) == []

    def test_save_load_round_trip(self, index, tmp_path):
        from aica.firmware.index import VerificationIndex
        p = tmp_path / "index.json"
        index.save(p)
        loaded = VerificationIndex.load(p)
        assert {e.id for e in loaded.entries} == {e.id for e in index.entries}
        assert loaded.find("apollo510_evb", ["led"])[0].id == "sample.basic.blinky"


# --- boards.json generation + sync ------------------------------------------

class TestBoards:
    def test_build_boards_json(self):
        from aica.firmware.boards import build_boards_json
        data = build_boards_json(WS, hw_map=FIXTURES / "map.yaml")
        b = data["boards"]["apollo510_evb"]
        assert b["twister_platform"] == "apollo510_evb/apollo510"
        assert b["vendor"] == "ambiq"
        assert "apollo510" in b["aliases"]
        assert "led" in b["supported"]
        assert b["connected"]["serial"] == "/dev/ttyACM0"
        assert b["connected"]["runner"] == "jlink"
        assert "native_sim" in data["boards"]
        assert "connected" not in data["boards"]["native_sim"]

    def test_sync_writes_home_files_and_feeds_vocabulary(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from aica.firmware.sync import sync_workspace
        from aica.routing.vocabulary import Vocabulary

        result = sync_workspace(WS, hw_map=FIXTURES / "map.yaml")
        assert (tmp_path / "rita" / "boards.json").exists()
        assert (tmp_path / "rita" / "verification-index.json").exists()
        assert result.boards >= 2 and result.entries >= 4

        vocab = Vocabulary.load()   # now reads the synced boards.json
        assert vocab.find_board("flash blinky to the apollo510") == "apollo510_evb"


# --- Fit judge (Claude judges fit ONLY, one bounded call) -------------------

class TestFitJudge:
    def make_candidates(self):
        from aica.firmware.index import VerificationIndex
        idx = VerificationIndex.build(WS)
        return idx.find("apollo510_evb", ["led", "blinky"])

    def test_yes_selects_candidate(self):
        from aica.firmware.fit import judge_fit
        cands = self.make_candidates()
        calls = []

        def fake_complete(prompt: str) -> str:
            calls.append(prompt)
            return json.dumps({"fit": "sample.basic.blinky", "reason": "blinks led0"})

        decision = judge_fit("blink the led", cands, fake_complete)
        assert decision.entry is not None and decision.entry.id == "sample.basic.blinky"
        assert decision.reason == "blinks led0"
        assert len(calls) == 1                      # one bounded call
        assert "sample.basic.blinky" in calls[0]    # candidates are in the prompt

    def test_no_fit_returns_none(self):
        from aica.firmware.fit import judge_fit
        decision = judge_fit("measure power", self.make_candidates(),
                             lambda p: json.dumps({"fit": "none", "reason": "nope"}))
        assert decision.entry is None

    def test_cannot_invent_a_candidate(self):
        from aica.firmware.fit import judge_fit
        decision = judge_fit("blink", self.make_candidates(),
                             lambda p: json.dumps({"fit": "sample.i.made.up",
                                                   "reason": "hallucinated"}))
        assert decision.entry is None


# --- Test writer (no match -> Claude writes a proper ztest) ------------------

GOOD_TEST_FILES = {
    "testcase.yaml": ("tests:\n  app.blink.custom:\n    tags: led gpio\n"
                      "    harness: ztest\n"),
    "src/main.c": "#include <zephyr/ztest.h>\nZTEST_SUITE(blink, NULL, NULL, NULL, NULL, NULL);\n",
    "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\n",
    "prj.conf": "CONFIG_ZTEST=y\n",
}


class TestTestWriter:
    def test_writes_validated_ztest(self, tmp_path):
        from aica.firmware.testwriter import write_ztest
        written = write_ztest("blink the led", "apollo510_evb", tmp_path / "t",
                              lambda p: json.dumps(GOOD_TEST_FILES))
        assert (tmp_path / "t" / "testcase.yaml").exists()
        assert (tmp_path / "t" / "src" / "main.c").exists()
        assert written.test_id == "app.blink.custom"

    def test_rejects_missing_testcase_yaml(self, tmp_path):
        from aica.firmware.testwriter import write_ztest
        bad = {k: v for k, v in GOOD_TEST_FILES.items() if k != "testcase.yaml"}
        with pytest.raises(ValueError):
            write_ztest("blink", "apollo510_evb", tmp_path / "t",
                        lambda p: json.dumps(bad))

    def test_rejects_unparseable_testcase_yaml(self, tmp_path):
        from aica.firmware.testwriter import write_ztest
        bad = dict(GOOD_TEST_FILES, **{"testcase.yaml": "no tests key here"})
        with pytest.raises(ValueError):
            write_ztest("blink", "apollo510_evb", tmp_path / "t",
                        lambda p: json.dumps(bad))


# --- Resolution: find-or-write ----------------------------------------------

class TestResolveVerification:
    def test_known_sample_resolves_from_index(self, tmp_path):
        from aica.firmware.index import VerificationIndex
        from aica.firmware.resolve import resolve_verification
        idx = VerificationIndex.build(WS)
        res = resolve_verification(
            goal="blink the led", board="apollo510_evb", terms=["led", "blinky"],
            index=idx, complete=lambda p: json.dumps(
                {"fit": "sample.basic.blinky", "reason": "fits"}),
            write_dir=tmp_path)
        assert res.method == "existing"
        assert res.entry.path.endswith("samples/basic/blinky")

    def test_no_match_forces_test_authorship(self, tmp_path):
        # Acceptance: nothing in the index verifies this -> a test is written.
        from aica.firmware.index import VerificationIndex
        from aica.firmware.resolve import resolve_verification
        idx = VerificationIndex.build(WS)
        res = resolve_verification(
            goal="verify the watchdog fires", board="apollo510_evb",
            terms=["watchdog"], index=idx,
            complete=lambda p: json.dumps(GOOD_TEST_FILES),
            write_dir=tmp_path)
        assert res.method == "written"
        assert (tmp_path / "testcase.yaml").exists()


# --- MCP tool implementations (pure, workspace-rooted, guarded) --------------

class TestMcpTools:
    def test_find_verification(self, tools):
        hits = tools.find_verification("apollo510_evb", "blinky led")
        assert hits[0]["id"] == "sample.basic.blinky"

    def test_board_info_and_list(self, tools):
        info = tools.board_info("apollo510_evb")
        assert info["twister_platform"] == "apollo510_evb/apollo510"
        boards = tools.list_boards(supports="adc")
        assert "native_sim" in [b["name"] for b in boards]
        assert "apollo510_evb" not in [b["name"] for b in boards]

    def test_sample_lookup_includes_readme(self, tools):
        s = tools.sample_lookup("blinky")
        assert s is not None
        assert "led0" in s["readme"]
        assert "sample.basic.blinky" in s["yaml"]

    def test_read_workspace_file(self, tools):
        text = tools.read_workspace_file("zephyr/samples/basic/blinky/README.rst")
        assert "Blinky" in text

    def test_read_rejects_traversal(self, tools):
        with pytest.raises(ValueError):
            tools.read_workspace_file("../../../etc/passwd")
        with pytest.raises(ValueError):
            tools.read_workspace_file("/etc/passwd")

    def test_grep_workspace(self, tools):
        hits = tools.grep_workspace("led0", glob="*.rst")
        assert any("blinky/README.rst" in h["path"] for h in hits)
        assert all("led0" in h["line"] for h in hits)
