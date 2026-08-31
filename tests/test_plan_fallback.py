"""A slow agent must not sink the whole task. The owner's live trace:
the authoring step burned both 300s windows RESEARCHING the workspace
(the partial output showed it grepping the tree over a vendor string)
instead of doing its one bounded step. Fixes under test: the prompts
forbid broad research and demand the simplest working choice, and a
failed PLAN falls back to a plan RITA derives herself — the copy's own
sources for a modify, the standard trio for a fresh app. A plan that
reaches outside the app dir stays a hard refusal, never a fallback."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def make_cli():
    from rita.firmware.coder import CoderCli

    return CoderCli(WS, command=(sys.executable,), timeout=300.0)


class PlanHangsThenWrites:
    """Plan calls time out; write calls create the named file."""

    def __init__(self, dest: Path) -> None:
        self.dest = dest
        self.calls: list[list] = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        if "--permission-mode" not in args:      # a plan call: hang
            raise subprocess.TimeoutExpired(cmd=list(args), timeout=300,
                                            output=b"researching...",
                                            stderr=b"")
        m = re.search(r"ONE file and nothing else: (\S+)", args[1])
        if m:
            target = self.dest / m.group(1)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("// edited\n")
        return subprocess.CompletedProcess(args, 0, stdout="done", stderr="")


class TestPlanFallback:
    def test_modify_copy_falls_back_to_its_own_sources(self, tmp_path,
                                                       monkeypatch):
        cli = make_cli()
        notes = []
        cli.on_activity = notes.append
        dest = tmp_path / "app"
        (dest / "src").mkdir(parents=True)
        (dest / "src" / "main.c").write_text("int main(void){return 0;}\n")
        (dest / "CMakeLists.txt").write_text("x\n")
        (dest / "prj.conf").write_text("y\n")
        script = PlanHangsThenWrites(dest)
        monkeypatch.setattr("rita.firmware.coder.subprocess.run", script)
        res = cli.scaffold("add an output string", "qemu_x86", dest)
        assert res.ok, res.detail
        # The plan hung twice; the write targeted the copy's OWN source.
        writes = [c for c in script.calls if "--permission-mode" in c]
        assert len(writes) == 1
        assert "src/main.c" in writes[0][1]
        assert any("standard layout" in n for n in notes), notes

    def test_fresh_scaffold_falls_back_to_the_standard_trio(self, tmp_path,
                                                            monkeypatch):
        cli = make_cli()
        dest = tmp_path / "app"
        script = PlanHangsThenWrites(dest)
        monkeypatch.setattr("rita.firmware.coder.subprocess.run", script)
        res = cli.scaffold("blink the LED", "qemu_x86", dest)
        assert res.ok, res.detail
        for req in ("CMakeLists.txt", "prj.conf", "src/main.c"):
            assert (dest / req).exists(), req

    def test_outside_path_plan_is_still_a_hard_refusal(self, tmp_path,
                                                       monkeypatch):
        cli = make_cli()
        dest = tmp_path / "app"
        evil = json.dumps({"files": [{"path": "../evil.c",
                                      "purpose": "nope"}]})

        def run(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=evil,
                                               stderr="")

        monkeypatch.setattr("rita.firmware.coder.subprocess.run", run)
        res = cli.scaffold("blink the LED", "qemu_x86", dest)
        assert not res.ok
        assert "outside" in res.detail
        assert not (tmp_path / "evil.c").exists()


class TestPromptDiscipline:
    def test_both_prompts_forbid_broad_research(self):
        from rita.firmware.coder import _PLAN_PROMPT, _WRITE_PROMPT

        for prompt in (_PLAN_PROMPT, _WRITE_PROMPT):
            text = " ".join(prompt.lower().split())   # unwrap lines
            assert "do not search the wider workspace" in text \
                or "do not survey the wider workspace" in text
            assert "simplest" in text
