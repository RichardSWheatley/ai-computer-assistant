"""Scaffold is decomposed: one fast JSON plan, then ONE file per
bounded agent call (the owner's rule: smaller tasks that return
quickly, so the timeout can be short — not one 'write the whole app'
call that needs a 30-minute ceiling)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"

PLAN = json.dumps({"files": [
    {"path": "CMakeLists.txt", "purpose": "build definition"},
    {"path": "prj.conf", "purpose": "Kconfig"},
    {"path": "src/main.c", "purpose": "entry point"},
]})


def make_cli():
    from rita.firmware.coder import CoderCli

    return CoderCli(WS, command=(sys.executable,), timeout=300.0)


class Script:
    """Fake subprocess.run: first call answers the plan; write calls
    create the one file the prompt names (unless told not to)."""

    def __init__(self, dest: Path, plan: str = PLAN,
                 skip_writing: set[str] | None = None) -> None:
        self.dest = dest
        self.plan = plan
        self.skip = skip_writing or set()
        self.calls: list[list] = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        prompt = args[1]
        if "--permission-mode" not in args:          # the plan call
            return subprocess.CompletedProcess(args, 0, stdout=self.plan,
                                               stderr="")
        m = re.search(r"ONE file and nothing else: (\S+)", prompt)
        path = m.group(1) if m else ""
        if path and path not in self.skip:
            target = self.dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("// written\n")
        return subprocess.CompletedProcess(args, 0, stdout="done", stderr="")


class TestDecomposedScaffold:
    def test_plan_then_one_bounded_call_per_file(self, tmp_path,
                                                 monkeypatch):
        cli = make_cli()
        dest = tmp_path / "app"
        script = Script(dest)
        monkeypatch.setattr("rita.firmware.coder.subprocess.run", script)
        res = cli.scaffold("blink the LED", "qemu_x86", dest)
        assert res.ok, res.detail
        assert len(script.calls) == 4            # 1 plan + 3 files
        assert "--permission-mode" not in script.calls[0]   # plan: no edits
        for call in script.calls[1:]:
            # Every write prompt names exactly one file.
            assert len(re.findall(r"ONE file and nothing else",
                                  call[1])) == 1
        assert (dest / "src" / "main.c").exists()

    def test_missing_mandatory_files_are_added(self, tmp_path, monkeypatch):
        cli = make_cli()
        dest = tmp_path / "app"
        sparse = json.dumps({"files": [
            {"path": "src/main.c", "purpose": "entry point"}]})
        script = Script(dest, plan=sparse)
        monkeypatch.setattr("rita.firmware.coder.subprocess.run", script)
        res = cli.scaffold("blink the LED", "qemu_x86", dest)
        assert res.ok, res.detail
        assert (dest / "CMakeLists.txt").exists()
        assert (dest / "prj.conf").exists()

    def test_uncreated_file_gets_one_corrective_call_then_honesty(
            self, tmp_path, monkeypatch):
        cli = make_cli()
        dest = tmp_path / "app"
        script = Script(dest, skip_writing={"src/main.c"})
        monkeypatch.setattr("rita.firmware.coder.subprocess.run", script)
        res = cli.scaffold("blink the LED", "qemu_x86", dest)
        assert not res.ok
        assert "src/main.c" in res.detail        # the missing file, named
        corrective = [c for c in script.calls
                      if "was not created" in c[1]]
        assert len(corrective) == 1              # exactly one second chance

    def test_plan_reaching_outside_the_app_dir_is_refused(self, tmp_path,
                                                          monkeypatch):
        cli = make_cli()
        dest = tmp_path / "app"
        evil = json.dumps({"files": [
            {"path": "../evil.c", "purpose": "nope"}]})
        script = Script(dest, plan=evil)
        monkeypatch.setattr("rita.firmware.coder.subprocess.run", script)
        res = cli.scaffold("blink the LED", "qemu_x86", dest)
        assert not res.ok
        assert "outside" in res.detail
        assert not (tmp_path / "evil.c").exists()

    def test_unparseable_plan_fails_with_the_reply_quoted(self, tmp_path,
                                                          monkeypatch):
        cli = make_cli()
        dest = tmp_path / "app"

        def prose(args, **kwargs):
            return subprocess.CompletedProcess(args, 0,
                                               stdout="Sure! Here's my "
                                                      "thinking about it",
                                               stderr="")

        monkeypatch.setattr("rita.firmware.coder.subprocess.run", prose)
        res = cli.scaffold("blink the LED", "qemu_x86", dest)
        assert not res.ok
        assert "thinking about it" in res.detail  # evidence, not mystery


class TestShorterCeiling:
    def test_default_ceiling_is_five_minutes(self):
        from rita.config import RitaConfig

        assert RitaConfig().coder_timeout_seconds == 300
