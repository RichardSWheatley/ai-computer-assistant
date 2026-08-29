"""The learning layer: RITA learns the system instead of assuming it.

The coding agent investigates THIS machine (and may search online);
RITA validates every claim deterministically before using or storing
it; validated findings persist as machine facts; the agent can build
toolsets RITA keeps and reruns; each chat can bind its own repo/area.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def make_supervisor(tmp_path, *, workspace=str(WS), completions=(),
                    coder=None):
    from rita.config import RitaConfig
    from rita.firmware.coder import FakeCoder
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    if coder is None and completions:
        coder = FakeCoder(completions=list(completions))
    return Supervisor(
        rita_cfg=RitaConfig(workspace=workspace, auto_setup=False),
        config_path=tmp_path / "config", tts=FakeTTS(),
        coder=coder, workdir=tmp_path / "work")


class TestWorkspaceKinds:
    """Zephyr is a flavor, not an assumption."""

    def test_zephyr_workspace_detected(self):
        from rita.firmware.workspace import workspace_kind
        assert workspace_kind(WS) == "zephyr"

    def test_plain_repo_is_generic(self, tmp_path):
        from rita.firmware.workspace import workspace_kind
        (tmp_path / "src").mkdir()
        assert workspace_kind(tmp_path) == "generic"

    def test_generic_workspace_queues_no_firmware_steps(self, tmp_path):
        # A non-Zephyr repo must not trigger CERBERUS/Unity/toolchain/
        # board-sync — that machinery belongs to Zephyr work only.
        (tmp_path / "repo" / "src").mkdir(parents=True)
        sup = make_supervisor(tmp_path, workspace=str(tmp_path / "repo"))
        names = {n for n, _ in sup._setup_steps()}
        assert names <= {"modules"}

    def test_zephyr_workspace_still_queues_them(self, tmp_path):
        sup = make_supervisor(tmp_path)
        names = {n for n, _ in sup._setup_steps()}
        assert "CERBERUS" in names and "Unity" in names


class TestInvestigate:
    """Trust but verify: the agent's answer is DATA until RITA has
    validated it on this machine herself."""

    def test_validated_claim_becomes_a_finding(self, tmp_path):
        from rita.learning.investigate import investigate
        real = tmp_path / "tool.exe"
        real.write_text("")

        def complete(prompt):
            assert "JSON" in prompt          # strict-JSON contract stated
            assert "online" in prompt.lower()  # may search the web
            return json.dumps({"path": str(real)})

        def validate(claim):
            p = Path(claim.get("path", ""))
            return f"verified {p}" if p.is_file() else None

        finding, note = investigate(complete, "where is the tool?",
                                    schema='{"path": "<absolute path>"}',
                                    validate=validate)
        assert finding is not None
        assert finding.answer["path"] == str(real)
        assert "verified" in note

    def test_unverifiable_claim_is_discarded(self, tmp_path):
        from rita.learning.investigate import investigate

        finding, note = investigate(
            lambda p: json.dumps({"path": str(tmp_path / "nope")}),
            "where?", schema='{"path": "..."}',
            validate=lambda c: None)
        assert finding is None
        assert "verify" in note.lower() or "discard" in note.lower()

    def test_non_json_reply_is_reported_not_trusted(self):
        from rita.learning.investigate import investigate
        finding, note = investigate(
            lambda p: "it's probably in /usr/bin somewhere",
            "where?", schema='{"path": "..."}',
            validate=lambda c: "yes")
        assert finding is None
        assert "json" in note.lower()


class TestMachineFacts:
    def test_fact_roundtrip_and_staleness(self, tmp_path):
        from rita.learning import facts
        tool = tmp_path / "gcc"
        tool.write_text("")
        facts.save_fact("sdk-arm-gcc", {"path": str(tool)},
                        evidence="ran it, gcc 14.3")
        got = facts.fact("sdk-arm-gcc")
        assert got is not None and got["path"] == str(tool)
        tool.unlink()                       # the machine changed
        assert facts.fact("sdk-arm-gcc") is None   # stale, not trusted

    def test_all_facts_lists_only_valid(self, tmp_path):
        from rita.learning import facts
        keep = tmp_path / "west"
        keep.write_text("")
        facts.save_fact("west", {"path": str(keep)}, evidence="exists")
        facts.save_fact("gone", {"path": str(tmp_path / "gone")},
                        evidence="was there once")
        allf = facts.all_facts()
        assert "west" in allf and "gone" not in allf

    def test_describe_names_facts_with_provenance(self, tmp_path):
        from rita.learning import facts
        keep = tmp_path / "qemu"
        keep.write_text("")
        facts.save_fact("qemu-system-arm", {"path": str(keep)},
                        evidence="ran ok")
        text = facts.describe()
        assert "qemu-system-arm" in text


class TestSystemDiscovery:
    """The sync learning pass: undetected pieces become agent
    investigations; only validated answers are stored — and the
    deterministic detectors then USE the stored facts."""

    def _gcc_gap(self, tmp_path, monkeypatch):
        # A machine whose SDK layout RITA's own probes don't understand.
        from rita.firmware import toolchain as tc
        from rita.firmware import workspace as wsmod
        sdk = tmp_path / "sdk"
        sdk.mkdir()
        hidden = sdk / "weird" / "spot" / "deep" / "bin"
        hidden.mkdir(parents=True)
        gcc = hidden / "arm-zephyr-eabi-gcc"
        gcc.write_text("")
        monkeypatch.setattr(wsmod, "read_sdk_info",
                            lambda: {"path": str(sdk), "version": "9.9.9"})
        monkeypatch.setattr(
            tc, "_gcc_version_raw",
            lambda cc: (((14, 3), "14.3.0") if str(cc) == str(gcc)
                        else (None, "not a compiler")))
        # qemu detection pinned: whether THIS machine has qemu must not
        # change what the discovery tests observe.
        monkeypatch.setattr(tc, "detect_qemu", lambda: "/x/qemu-system-arm")
        return sdk, gcc

    def test_agent_claim_is_validated_then_remembered(self, tmp_path,
                                                      monkeypatch):
        from rita.learning import facts
        sdk, gcc = self._gcc_gap(tmp_path, monkeypatch)
        sup = make_supervisor(
            tmp_path, completions=[json.dumps({"path": str(gcc)})])
        out = sup.discover_system()
        assert "sdk-arm-gcc" in out
        fact = facts.fact("sdk-arm-gcc")
        assert fact is not None and fact["path"] == str(gcc)

    def test_bogus_claim_is_discarded_not_stored(self, tmp_path,
                                                 monkeypatch):
        from rita.learning import facts
        self._gcc_gap(tmp_path, monkeypatch)
        sup = make_supervisor(
            tmp_path,
            completions=[json.dumps({"path": str(tmp_path / "lie")})])
        out = sup.discover_system()
        assert facts.fact("sdk-arm-gcc") is None
        assert "sdk-arm-gcc" in out          # reported, with the outcome

    def test_detection_uses_the_learned_fact(self, tmp_path, monkeypatch):
        # After discovery, RITA's own detector resolves via the fact —
        # second run has nothing to ask (zero agent calls).
        from rita.firmware import toolchain as tc
        from rita.firmware.coder import FakeCoder
        sdk, gcc = self._gcc_gap(tmp_path, monkeypatch)
        sup = make_supervisor(
            tmp_path, completions=[json.dumps({"path": str(gcc)})])
        sup.discover_system()
        assert tc._sdk_arm_gcc() == gcc      # the fact IS the detection now
        coder = FakeCoder()
        sup2 = make_supervisor(tmp_path, coder=coder)
        out2 = sup2.discover_system()
        assert coder.prompts == []           # nothing left to investigate
        assert "nothing" in out2.lower()

    def test_no_coder_is_honest(self, tmp_path, monkeypatch):
        self._gcc_gap(tmp_path, monkeypatch)
        sup = make_supervisor(tmp_path)
        assert "coding agent" in sup.discover_system().lower()


class TestToolsets:
    """The agent builds tools RITA keeps: validated by a real run
    before registration, rerunnable from disk forever after."""

    def _toolset_json(self, name="line-count", files=None, command=None,
                      smoke=None):
        return json.dumps({
            "name": name, "purpose": "count lines in a file",
            "files": files or {"main.py": "print('ok 3 lines')\n"},
            "command": command or ["python", "main.py"],
            "smoke": smoke or [],
        })

    def test_create_validate_register_rerun(self, tmp_path):
        from rita.learning import toolsets
        info, detail = toolsets.create_toolset(
            lambda p: self._toolset_json(), "count lines in files")
        assert info is not None, detail
        assert info.name == "line-count"
        names = [t.name for t in toolsets.list_toolsets()]
        assert "line-count" in names         # persisted, listable
        ok, output = toolsets.run_toolset("line-count")
        assert ok and "ok 3 lines" in output

    def test_failing_smoke_is_not_registered(self, tmp_path):
        from rita.learning import toolsets
        info, detail = toolsets.create_toolset(
            lambda p: self._toolset_json(
                name="broken", files={"main.py": "import sys; sys.exit(3)\n"}),
            "whatever")
        assert info is None
        assert "broken" not in [t.name for t in toolsets.list_toolsets()]
        assert "exit" in detail or "3" in detail

    def test_escaping_file_paths_are_refused(self, tmp_path):
        from rita.learning import toolsets
        info, detail = toolsets.create_toolset(
            lambda p: self._toolset_json(
                name="evil", files={"../outside.py": "print(1)\n"}),
            "escape")
        assert info is None
        assert "refus" in detail.lower()
        assert not (Path(toolsets.toolsets_root()).parent / "outside.py").exists()

    def test_absolute_file_paths_are_refused(self, tmp_path):
        from rita.learning import toolsets
        target = tmp_path / "abs.py"
        info, detail = toolsets.create_toolset(
            lambda p: self._toolset_json(
                name="evil2", files={str(target): "print(1)\n"}),
            "escape")
        assert info is None
        assert not target.exists()

    def test_unparseable_agent_output_is_reported(self):
        from rita.learning import toolsets
        info, detail = toolsets.create_toolset(
            lambda p: "sure, I'd write a python script that ...", "x")
        assert info is None
        assert "json" in detail.lower()


class TestChatAreas:
    """Each chat can bind its own repo/area; unbound chats keep the
    global workspace, so today's flow keeps working."""

    def test_default_chat_uses_global_workspace(self, tmp_path):
        sup = make_supervisor(tmp_path)
        assert sup.effective_workspace() == str(WS)

    def test_binding_a_local_path(self, tmp_path):
        repo = tmp_path / "myrepo"
        (repo / "src").mkdir(parents=True)
        sup = make_supervisor(tmp_path)
        said = sup.bind_chat(str(repo))
        assert sup.effective_workspace() == str(repo)
        assert str(repo) in said

    def test_binding_survives_a_new_supervisor(self, tmp_path):
        repo = tmp_path / "myrepo"
        repo.mkdir()
        sup = make_supervisor(tmp_path)
        sup.bind_chat(str(repo))
        sup2 = make_supervisor(tmp_path)
        assert sup2.effective_workspace() == str(repo)

    def test_new_chat_starts_unbound(self, tmp_path):
        repo = tmp_path / "myrepo"
        repo.mkdir()
        sup = make_supervisor(tmp_path)
        sup.bind_chat(str(repo))
        said = sup.new_chat()
        assert sup.effective_workspace() == str(WS)   # back to global
        assert "chat" in said.lower()

    def test_git_url_is_cloned_into_the_chat_area(self, tmp_path,
                                                  monkeypatch):
        from rita.learning import chats
        cloned = {}

        def fake_clone(url, dest):
            cloned["url"] = url
            Path(dest).mkdir(parents=True, exist_ok=True)
            return True, "cloned"

        monkeypatch.setattr(chats, "_git_clone", fake_clone)
        sup = make_supervisor(tmp_path)
        sup.bind_chat("https://example.com/team/fw.git")
        assert cloned["url"] == "https://example.com/team/fw.git"
        from rita.home import chats_dir
        assert str(chats_dir()) in sup.effective_workspace()

    def test_missing_local_path_is_refused_honestly(self, tmp_path):
        sup = make_supervisor(tmp_path)
        said = sup.bind_chat(str(tmp_path / "nope"))
        assert sup.effective_workspace() == str(WS)   # unchanged
        assert "exist" in said.lower() or "find" in said.lower()

    def test_chat_binding_phrase_routes_to_chat(self, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        sup = make_supervisor(tmp_path)
        said = sup.handle_chat(f"use {repo} for this chat")
        assert sup.effective_workspace() == str(repo)
        assert str(repo) in said


class TestRoutingPhrases:
    def _route(self, text):
        from rita.routing.model import Utterance
        from rita.routing.router import route
        from rita.routing.vocabulary import Vocabulary
        return route(Utterance.from_text(text), Vocabulary.load())

    def test_make_a_toolset_is_not_scaffold_work(self):
        # "make" is a scaffold verb; the toolset phrase must win first.
        d = self._route("make a toolset that summarizes build logs")
        assert d.kind == "chat"

    def test_toolset_create_submits_a_task(self, tmp_path):
        sup = make_supervisor(
            tmp_path,
            completions=[json.dumps({
                "name": "log-summary", "purpose": "summarize logs",
                "files": {"main.py": "print('summary')\n"},
                "command": ["python", "main.py"], "smoke": []})])
        said = sup.handle_chat("make a toolset that summarizes build logs")
        assert "toolset" in said.lower()
        import time
        deadline = time.time() + 5
        while time.time() < deadline:
            from rita.learning import toolsets
            if "log-summary" in [t.name for t in toolsets.list_toolsets()]:
                break
            time.sleep(0.02)
        from rita.learning import toolsets
        assert "log-summary" in [t.name for t in toolsets.list_toolsets()]

    def test_list_toolsets_phrase(self, tmp_path):
        from rita.learning import toolsets
        toolsets.create_toolset(
            lambda p: json.dumps({
                "name": "one", "purpose": "does one thing",
                "files": {"main.py": "print('x')\n"},
                "command": ["python", "main.py"], "smoke": []}), "x")
        sup = make_supervisor(tmp_path)
        said = sup.handle_chat("list your toolsets")
        assert "one" in said

    def test_use_toolset_phrase_runs_it(self, tmp_path):
        from rita.learning import toolsets
        toolsets.create_toolset(
            lambda p: json.dumps({
                "name": "greeter", "purpose": "greets",
                "files": {"main.py": "print('hello from toolset')\n"},
                "command": ["python", "main.py"], "smoke": []}), "x")
        sup = make_supervisor(tmp_path)
        said = sup.handle_chat("use the greeter toolset")
        assert "hello from toolset" in said

    def test_what_did_you_learn_reports(self, tmp_path):
        from rita.learning import facts
        keep = tmp_path / "tool"
        keep.write_text("")
        facts.save_fact("west", {"path": str(keep)}, evidence="exists")
        sup = make_supervisor(tmp_path)
        said = sup.handle_chat("what did you learn")
        assert "west" in said


class TestSyncTriggersDiscovery:
    def test_presenter_sync_submits_the_learning_pass(self, tmp_path,
                                                      monkeypatch):
        from rita.gui.presenter import GuiPresenter
        sup = make_supervisor(tmp_path, completions=["{}"])
        monkeypatch.setattr(sup, "_discovery_gaps", lambda: [("x",) * 4])
        submitted = []
        monkeypatch.setattr(
            sup.manager, "submit",
            lambda name, fn: submitted.append(name) or "task-x")
        p = GuiPresenter(sup)
        p.sync(str(WS))
        assert any("learn" in n.lower() for n in submitted)
