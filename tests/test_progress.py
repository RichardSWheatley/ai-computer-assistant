"""Progress visibility: the owner pressed Pause just to prove a task
was alive. "Are you still working?" answers with live status; stages
stream into the screen pane as they pass; agent invocations are
narrated — silence never means anything again."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def make_supervisor(tmp_path):
    from rita.config import RitaConfig
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS
    return Supervisor(
        rita_cfg=RitaConfig(workspace=str(WS), auto_setup=False),
        config_path=tmp_path / "config", tts=FakeTTS(),
        workdir=tmp_path / "work")


class TestStatusQuestions:
    def test_are_you_still_working_reports_the_running_task(self, tmp_path):
        sup = make_supervisor(tmp_path)
        gate = threading.Event()
        sup.manager.submit("build hello world", lambda ctl: gate.wait(5))
        try:
            said = sup.handle_chat("are you still working on it")
            assert "build hello world" in said
            assert "running" in said.lower() or "still" in said.lower()
        finally:
            gate.set()

    def test_status_shows_completed_stages(self, tmp_path):
        sup = make_supervisor(tmp_path)
        g1, g2 = threading.Event(), threading.Event()

        def work(ctl):
            ctl.checkpoint("RESOLVE")
            g1.set()
            g2.wait(5)

        sup.manager.submit("build blinky", work)
        try:
            assert g1.wait(5)
            said = sup.handle_chat("status")
            assert "RESOLVE" in said
        finally:
            g2.set()

    def test_nothing_running_is_honest(self, tmp_path):
        sup = make_supervisor(tmp_path)
        said = sup.handle_chat("are you still working")
        assert "nothing" in said.lower()

    def test_status_phrase_is_not_work(self):
        from rita.routing.model import Utterance
        from rita.routing.router import route
        from rita.routing.vocabulary import Vocabulary
        d = route(Utterance.from_text("are you still working on it"),
                  Vocabulary.load())
        assert d.kind == "chat"


class TestStageStreaming:
    def test_stages_stream_into_the_owning_chat(self, tmp_path):
        from rita.gui.presenter import GuiPresenter
        sup = make_supervisor(tmp_path)
        p = GuiPresenter(sup, poll_interval=0.02)
        events = []
        p.on_chat_event = lambda c, k, t: events.append((c, k, t))
        g1, g2 = threading.Event(), threading.Event()

        def work(ctl):
            ctl.checkpoint("RESOLVE")
            g1.wait(5)
            ctl.checkpoint("BUILD")
            g2.wait(5)

        try:
            p.set_active_chat("chat-1")
            before = set(sup.manager.tasks())
            sup.manager.submit("build hello world", work)
            tid = next(iter(set(sup.manager.tasks()) - before))
            p._task_chats[tid] = "chat-1"
            deadline = time.time() + 5
            while time.time() < deadline and not any(
                    "RESOLVE" in t for _c, k, t in events if k == "screen"):
                time.sleep(0.02)
            assert any("RESOLVE" in t for c, k, t in events
                       if k == "screen" and c == "chat-1")
            g1.set()
            deadline = time.time() + 5
            while time.time() < deadline and not any(
                    "BUILD" in t for _c, k, t in events if k == "screen"):
                time.sleep(0.02)
            assert any("BUILD" in t for _c, k, t in events if k == "screen")
        finally:
            g1.set()
            g2.set()
            p.close()


class TestAgentNarration:
    def _wire(self, monkeypatch, which):
        from rita.firmware import coder as coder_mod
        from rita.firmware import static_check

        monkeypatch.setattr(static_check.shutil, "which", which)
        seen = {}

        def fake_run(argv, **kw):
            seen["argv"] = list(argv)
            seen.update(kw)

            class P:
                returncode = 0
                stdout = "the reply"
                stderr = ""
            return P()

        monkeypatch.setattr(coder_mod.subprocess, "run", fake_run)
        return seen

    def test_coder_invocations_are_narrated(self, tmp_path, monkeypatch):
        from rita.firmware.coder import CoderCli

        self._wire(monkeypatch, lambda n: f"/x/{n}")
        cli = CoderCli(tmp_path, command=("agent", "-p"))
        notes = []
        cli.on_activity = notes.append
        out = cli.complete("hello")
        assert out == "the reply"
        assert any("coding agent" in n.lower() for n in notes)
        assert any("replied" in n.lower() for n in notes)

    def test_cmd_shim_sends_the_prompt_via_stdin(self, tmp_path,
                                                 monkeypatch):
        # The owner's agent said "your message ends at the colon": npm
        # .CMD shims run through cmd.exe, which truncates multi-line
        # arguments — the prompt must travel via stdin instead.
        from rita.firmware.coder import CoderCli

        seen = self._wire(monkeypatch,
                          lambda n: r"C:\npm\agent.CMD")
        cli = CoderCli(tmp_path, command=("agent", "-p"))
        cli.complete("intent on board qemu_x86:\nbuild hello world")
        assert seen["input"] == "intent on board qemu_x86:\nbuild hello world"
        assert all("hello world" not in a for a in seen["argv"])
        assert (seen.get("encoding") or "").lower().replace("-", "") == "utf8"

    def test_plain_binary_keeps_the_prompt_in_argv(self, tmp_path,
                                                   monkeypatch):
        from rita.firmware.coder import CoderCli

        seen = self._wire(monkeypatch, lambda n: "/usr/bin/agent")
        cli = CoderCli(tmp_path, command=("agent", "-p"))
        cli.complete("one\ntwo")
        assert "one\ntwo" in seen["argv"]
        assert seen.get("input") is None
