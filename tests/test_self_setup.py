"""Self-setup: RITA bootstraps herself; the agent gets MD context at
runtime; unknown how-do-i questions are asked once and remembered."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"


def wait_done(sup, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        tids = sup.manager.tasks()
        if tids and sup.manager.report(tids[-1]).state in ("DONE", "FAILED"):
            return sup.manager.report(tids[-1])
        time.sleep(0.02)
    raise AssertionError("task never finished")


def make_supervisor(tmp_path, monkeypatch, **cfg_kw):
    monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
    from rita.config import RitaConfig
    from rita.firmware.coder import FakeCoder
    from rita.firmware.west import FakeWest
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    coder = FakeCoder(completions=cfg_kw.pop("completions", []))
    sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS), **cfg_kw),
                     config_path=tmp_path / "config", tts=FakeTTS(),
                     runner=FakeWest(build_seq=["ok"] * 4,
                                     twister_seq=["pass.json"] * 4,
                                     fixtures_dir=TW),
                     coder=coder, workdir=tmp_path / "work")
    return sup, coder


class TestAutoSetup:
    def _patch_installs(self, monkeypatch, missing):
        """Simulate which pieces are missing; record what gets installed."""
        from rita.firmware.cerberus_setup import InstallResult
        import rita.supervisor as sup_mod
        installed = []

        def fake(name):
            def run(*a, **k):
                installed.append(name)
                return InstallResult(ok=True, path=name, detail=f"{name} ok")
            return run

        monkeypatch.setattr("rita.firmware.cerberus_setup.detect_cerberus",
                            lambda *a, **k: None if "cerberus" in missing
                            else Path("/x/cerberus"))
        monkeypatch.setattr("rita.firmware.cerberus_setup.install_cerberus",
                            fake("cerberus"))
        monkeypatch.setattr("rita.firmware.unity.detect_unity",
                            lambda *a, **k: None if "unity" in missing
                            else Path("/x/unity"))
        monkeypatch.setattr("rita.firmware.unity.install_unity", fake("unity"))
        monkeypatch.setattr("rita.firmware.toolchain.detect_arm_gcc",
                            lambda: None if "toolchain" in missing
                            else object())
        monkeypatch.setattr("rita.firmware.toolchain.zephyr_gcc_version",
                            lambda: (14, 3))
        monkeypatch.setattr("rita.firmware.toolchain.install_arm_gcc",
                            fake("toolchain"))
        return installed

    def test_installs_only_whats_missing(self, tmp_path, monkeypatch):
        sup, coder = make_supervisor(tmp_path, monkeypatch,
                                     coder_command="agent -p")
        installed = self._patch_installs(monkeypatch,
                                         missing={"unity", "toolchain"})
        said = sup.auto_setup()
        assert "unity" in said.lower() or "setting" in said.lower()
        rep = wait_done(sup)
        assert rep.state == "DONE"
        assert "cerberus" not in installed          # present -> untouched
        assert "unity" in installed and "toolchain" in installed
        summary = sup.task_summary(sup.manager.tasks()[-1])
        assert "unity ok" in summary.lower()

    def test_nothing_missing_says_so_without_a_task(self, tmp_path,
                                                    monkeypatch):
        sup, coder = make_supervisor(tmp_path, monkeypatch,
                                     coder_command="agent -p")
        from rita.firmware.sync import sync_workspace
        from rita.modules.install import dev_install
        dev_install()
        sync_workspace(WS)
        self._patch_installs(monkeypatch, missing=set())
        said = sup.auto_setup()
        assert "ready" in said.lower() or "nothing" in said.lower()
        assert sup.manager.tasks() == []

    def test_human_only_items_are_named(self, tmp_path, monkeypatch):
        sup, coder = make_supervisor(tmp_path, monkeypatch)   # no coder cfg
        sup._coder = None
        self._patch_installs(monkeypatch, missing=set())
        said = sup.auto_setup()
        assert "coding agent" in said.lower()
        assert "settings" in said.lower()

    @pytest.mark.parametrize("text", ["set yourself up", "finish setup",
                                      "get ready", "fix your setup"])
    def test_phrases_route_to_setup(self, tmp_path, monkeypatch, text):
        sup, coder = make_supervisor(tmp_path, monkeypatch,
                                     coder_command="agent -p")
        installed = self._patch_installs(monkeypatch, missing={"unity"})
        said = sup.shell.handle_typed(text)
        assert "unity" in said.lower() or "setting" in said.lower()
        wait_done(sup)
        assert installed == ["unity"]

    def test_presenter_launch_hook_honors_toggle(self, tmp_path, monkeypatch):
        from rita.gui.presenter import GuiPresenter
        sup, coder = make_supervisor(tmp_path, monkeypatch,
                                     coder_command="agent -p")
        installed = self._patch_installs(monkeypatch, missing={"unity"})
        p = GuiPresenter(sup)
        try:
            p.maybe_auto_setup()
            wait_done(sup)
            assert installed == ["unity"]
        finally:
            p.close()
        sup2, _ = make_supervisor(tmp_path, monkeypatch,
                                  coder_command="agent -p", auto_setup=False)
        installed2 = self._patch_installs(monkeypatch, missing={"unity"})
        p2 = GuiPresenter(sup2)
        try:
            p2.maybe_auto_setup()
            time.sleep(0.2)
            assert sup2.manager.tasks() == []      # toggle respected
        finally:
            p2.close()


class TestAgentContextMd:
    def test_scaffold_dir_gets_agents_md(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import RitaConfig
        from rita.firmware.coder import FakeCoder
        from rita.firmware.index import VerificationIndex
        from rita.firmware.pipeline import IteratePipeline
        from rita.firmware.west import FakeWest

        test_files = json.dumps({
            "testcase.yaml": "tests:\n  app.x:\n    tags: x\n    harness: ztest\n",
            "src/main.c": "#include <zephyr/ztest.h>\n",
            "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\n",
            "prj.conf": "CONFIG_ZTEST=y\n"})
        pipe = IteratePipeline(
            runner=FakeWest(build_seq=["ok"] * 4, twister_seq=["pass.json"] * 4,
                            fixtures_dir=TW),
            coder=FakeCoder(completions=[test_files]),
            index=VerificationIndex.build(WS),
            cfg=RitaConfig(workspace=str(WS),
                           applications_dir=str(tmp_path / "apps")),
            workdir=tmp_path / "work")
        report = pipe.run(goal="an example for mspi psram",
                          board="apollo510_evb", terms=["mspi", "psram"],
                          scaffold=True)
        assert report.outcome == "green"
        md_files = list((tmp_path / "apps").rglob("AGENTS.md"))
        assert md_files, "no AGENTS.md written into the scaffolded app"
        text = md_files[0].read_text()
        assert "apollo510_evb" in text
        assert "restrict" in text.lower() and "validate" in text.lower()
        assert "mspi" in text.lower()               # goal/terms present

    def test_authored_dir_gets_agents_md_too(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import RitaConfig
        from rita.firmware.coder import FakeCoder
        from rita.firmware.index import VerificationIndex
        from rita.firmware.pipeline import IteratePipeline
        from rita.firmware.west import FakeWest

        test_files = json.dumps({
            "testcase.yaml": "tests:\n  app.x:\n    tags: x\n    harness: ztest\n",
            "src/main.c": "#include <zephyr/ztest.h>\n",
            "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\n",
            "prj.conf": "CONFIG_ZTEST=y\n"})
        pipe = IteratePipeline(
            runner=FakeWest(build_seq=["ok"] * 4, twister_seq=["pass.json"] * 4,
                            fixtures_dir=TW),
            coder=FakeCoder(completions=[test_files]),
            index=VerificationIndex.build(WS),
            cfg=RitaConfig(workspace=str(WS)),
            workdir=tmp_path / "work")
        report = pipe.run(goal="verify mspi psram", board="apollo510_evb",
                          terms=["mspi", "psram"])
        assert report.outcome == "green"
        assert (tmp_path / "work" / "authored" / "AGENTS.md").exists()


class TestLearnedKnowledge:
    def test_miss_asks_the_agent_once_and_remembers(self, tmp_path,
                                                    monkeypatch):
        sup, coder = make_supervisor(
            tmp_path, monkeypatch, coder_command="agent -p",
            completions=["Enable CONFIG_PM and use pm_device_runtime_get()."])
        said = sup.shell.handle_typed("how do i wrangle the flux capacitor")
        assert "asking" in said.lower() or "agent" in said.lower()
        wait_done(sup)
        learned = list((tmp_path / "rita" / "knowledge" / "learned").glob("*.md"))
        assert learned, "answer was not persisted"
        text = learned[0].read_text()
        assert "CONFIG_PM" in text
        assert "agent-authored" in text
        # Second ask: answered from the file, ZERO further agent calls.
        calls_before = len(coder.prompts)
        said2 = sup.shell.handle_typed("how do i wrangle the flux capacitor")
        assert "CONFIG_PM" in said2 or "pm_device" in said2
        assert len(coder.prompts) == calls_before

    def test_no_coder_still_answers_honestly(self, tmp_path, monkeypatch):
        sup, coder = make_supervisor(tmp_path, monkeypatch)
        sup._coder = None
        said = sup.shell.handle_typed("how do i wrangle the flux capacitor")
        assert "coding agent" in said.lower() or "don't" in said.lower()
        assert sup.manager.tasks() == []
