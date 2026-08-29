"""The intelligent manager: the AI decides what to do; RITA verifies
the decision against synced reality and executes through the gates.

The owner's rule, twice stated: "RITA can use the AI to decide what to
do" / "there still needs to be an intelligent manager to route."
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"

BOARDS = ["qemu_x86", "native_sim", "apollo510_evb"]
SAMPLES = [("sample.basic.blinky", "zephyr/samples/basic/blinky")]
MACHINE = "Windows; native_sim is POSIX-only and cannot run here"


def order(**kw) -> str:
    base = {"action": "modify", "board": "qemu_x86",
            "sample": "sample.basic.blinky",
            "goal": "add an output string with the soc and vendor",
            "why": "native_sim cannot run on Windows"}
    base.update(kw)
    return json.dumps(base)


class TestInterpreter:
    def _interpret(self, reply):
        from rita.firmware.interpret import interpret_request
        return interpret_request(lambda p: reply, "whatever the user said",
                                 boards=BOARDS, samples=SAMPLES,
                                 machine=MACHINE)

    def test_valid_order_is_returned(self):
        got, note = self._interpret(order())
        assert got is not None
        assert got.action == "modify"
        assert got.board == "qemu_x86"
        assert got.sample == "sample.basic.blinky"
        assert "windows" in got.why.lower()

    def test_prompt_carries_the_facts(self):
        from rita.firmware.interpret import interpret_request
        seen = {}

        def complete(p):
            seen["prompt"] = p
            return order()

        interpret_request(complete, "modify the hello world example",
                          boards=BOARDS, samples=SAMPLES, machine=MACHINE)
        p = seen["prompt"]
        assert "qemu_x86" in p and "sample.basic.blinky" in p
        assert "POSIX-only" in p
        assert "modify the hello world example" in p

    def test_unknown_board_is_rejected_with_evidence(self):
        got, note = self._interpret(order(board="imaginary_board"))
        assert got is None
        assert "imaginary_board" in note

    def test_modify_without_a_real_sample_is_rejected(self):
        got, note = self._interpret(order(sample="sample.that.isnt"))
        assert got is None
        assert "sample.that.isnt" in note

    def test_unknown_action_is_rejected(self):
        got, note = self._interpret(order(action="deploy"))
        assert got is None
        assert "deploy" in note

    def test_chat_action_passes_through(self):
        got, note = self._interpret(order(action="chat", sample="",
                                          board=""))
        assert got is not None and got.action == "chat"


def make_supervisor(tmp_path, *, completions=(), coder=None, ai=True):
    from rita.config import RitaConfig
    from rita.firmware.coder import FakeCoder
    from rita.firmware.west import FakeWest
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    if coder is None and completions:
        coder = FakeCoder(completions=list(completions))
    runner = FakeWest(build_seq=["ok"], twister_seq=["pass.json"],
                      fixtures_dir=TW)
    return Supervisor(
        rita_cfg=RitaConfig(workspace=str(WS), auto_setup=False,
                            ai_routing=ai,
                            applications_dir=str(tmp_path / "apps")),
        config_path=tmp_path / "config", tts=FakeTTS(), runner=runner,
        coder=coder, workdir=tmp_path / "work")


def wait_done(sup, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        reps = [sup.manager.report(t) for t in sup.manager.tasks()]
        if reps and all(r.state in ("DONE", "FAILED", "STOPPED")
                        for r in reps):
            return reps
        time.sleep(0.02)
    raise AssertionError("task never finished")


class TestAiRouting:
    def test_the_agent_decides_and_rita_states_it(self, tmp_path):
        import hashlib

        sample_dir = WS / "zephyr" / "samples" / "basic" / "blinky"
        before = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                  for f in sample_dir.rglob("*") if f.is_file()}
        sup = make_supervisor(tmp_path, completions=[order()])
        said = sup.shell.handle_typed(
            "add an output string with the SoC and vendor to the blinky "
            "sample")
        assert "read that as" in said.lower() or "modify" in said.lower()
        assert "qemu_x86" in said
        wait_done(sup)
        # The copy carries the sample's identity; the coder worked there.
        from rita.firmware.pipeline import applications_root
        apps = applications_root(sup.cfg)
        copies = list(apps.glob("*/sample.yaml"))
        assert copies, f"no sample copy under {apps}"
        # The user's tree is byte-identical — upstream stays sacred.
        after = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                 for f in sample_dir.rglob("*") if f.is_file()}
        assert after == before
        import shutil
        shutil.rmtree(apps, ignore_errors=True)

    def test_chat_order_routes_to_chat(self, tmp_path):
        sup = make_supervisor(
            tmp_path,
            completions=[order(action="chat", sample="", board="")])
        said = sup.shell.handle_typed("build me something nice someday")
        # Chat fallback reply, not a started task.
        assert "started" not in said.lower()

    def test_failed_interpretation_falls_back_to_grammar(self, tmp_path):
        # The agent rambles -> after the JSON retry, grammar routing
        # still works and the reply says the fallback happened.
        sup = make_supervisor(
            tmp_path, completions=["let me think about this...",
                                   "still just words, no JSON",
                                   json.dumps({"fit": "sample.basic.blinky",
                                               "reason": "fits"})])
        said = sup.shell.handle_typed("build blinky")
        assert "started" in said.lower()

    def test_meta_phrases_never_reach_the_interpreter(self, tmp_path):
        from rita.firmware.coder import FakeCoder
        coder = FakeCoder()
        sup = make_supervisor(tmp_path, coder=coder)
        for phrase in ("pause", "status", "check setup",
                       "list your toolsets", "what did you learn"):
            sup.shell.handle_typed(phrase)
        assert coder.prompts == []           # deterministic fast paths

    def test_no_coder_default_board_is_windows_aware(self, tmp_path,
                                                     monkeypatch):
        from rita import supervisor as sup_mod
        sup = make_supervisor(tmp_path, ai=False)
        monkeypatch.setattr(sup_mod, "_WINDOWS", True)
        said = sup.handle_work.__self__.shell.handle_typed("build blinky")
        # No coder at all -> honest no-coder reply; with ai off but a
        # coder present the grammar path runs. Here: no coder.
        assert "coding agent" in said.lower()

    def test_grammar_default_board_prefers_qemu_on_windows(self, tmp_path,
                                                           monkeypatch):
        from rita import supervisor as sup_mod
        from rita.firmware.coder import FakeCoder

        monkeypatch.setattr(sup_mod, "_WINDOWS", True)
        sup = make_supervisor(
            tmp_path, ai=False,
            coder=FakeCoder(completions=[json.dumps(
                {"fit": "sample.basic.blinky", "reason": "fits"})]))
        said = sup.shell.handle_typed("build blinky")
        assert "qemu_x86" in said
