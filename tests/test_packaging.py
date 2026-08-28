"""The modular installer: module-run entrypoints + packaging consistency."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
PACKAGING = REPO / "packaging"


class TestModuleRun:
    def test_module_run_speaks_the_protocol(self):
        # A real child process: rita module-run cerberus must handshake and
        # answer with the stub's honest status.
        from rita.modules import rpc
        proc = subprocess.Popen(
            [sys.executable, "-m", "rita", "module-run", "cerberus"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        try:
            proc.stdin.write(rpc.encode_request(1, "hello", {}))
            proc.stdin.flush()
            hello = rpc.decode(proc.stdout.readline())
            assert hello["ok"] and hello["result"]["name"] == "cerberus"
            proc.stdin.write(rpc.encode_request(2, "start", {}))
            proc.stdin.flush()
            res = rpc.decode(proc.stdout.readline())
            assert res["result"]["ok"] is False          # honest stub
            proc.stdin.write(rpc.encode_request(3, "shutdown", {}))
            proc.stdin.flush()
            proc.wait(timeout=5)
        finally:
            proc.kill()

    def test_unknown_module_errors_cleanly(self):
        out = subprocess.run(
            [sys.executable, "-m", "rita", "module-run", "nope"],
            capture_output=True, text=True)
        assert out.returncode != 0
        assert "unknown module" in (out.stdout + out.stderr).lower()


class TestSelectiveInstall:
    def test_only_installs_selected_modules(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.modules.install import dev_install
        installed = dev_install(only=["cerberus", "scaffold"])
        assert {m.name for m in installed} == {"cerberus", "scaffold"}
        root = tmp_path / "rita" / "modules"
        assert (root / "cerberus" / "current").exists()
        assert not (root / "zephyr-runner").exists()

    def test_entrypoints_use_module_run(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.modules.install import dev_install
        m = dev_install(only=["cerberus"])[0]
        assert m.entrypoint[0] == sys.executable
        assert m.entrypoint[-2:] == ("module-run", "cerberus")

    def test_module_run_manifest_launches_via_registry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.modules.install import dev_install
        from rita.modules.registry import ModuleRegistry
        dev_install(only=["cerberus"])
        reg = ModuleRegistry(supervisor_version="9.9.9")
        try:
            h = reg.launch("cerberus", handshake_timeout=15)
            assert h.call("status", timeout=10)["ok"] is False   # honest stub
        finally:
            reg.shutdown_all()


class TestPackagingFiles:
    def test_pyinstaller_spec_references_existing_paths(self):
        spec = (PACKAGING / "rita.spec").read_text()
        assert "RitaApp" in spec and "rita.gui" in spec
        for rel in re.findall(r"SRC / ['\"]([^'\"]+)['\"]", spec):
            assert (REPO / "src" / rel).exists(), rel

    def test_iss_components_cover_all_shipped_modules(self):
        from rita.modules.install import SHIPPED
        iss = (PACKAGING / "installer.iss").read_text()
        for name in SHIPPED:
            assert name in iss, f"{name} missing from installer components"
        assert "RitaApp.exe" in iss
        assert "modules install" in iss                 # post-install step

    def test_iss_skips_downloads_already_on_the_machine(self):
        # Re-running the installer must not re-fetch CERBERUS/Unity the
        # user already has in ~/.rita — the installer checks first.
        iss = (PACKAGING / "installer.iss").read_text()
        assert "CerberusPresent" in iss
        assert "UnityPresent" in iss
        assert "Check: not CerberusPresent" in iss
        assert "Check: not UnityPresent" in iss
        # It probes the same file the app's own detection uses.
        assert r"cerberus\cerberus\cli.py" in iss
        assert r"unity.c" in iss

    def test_ci_workflow_is_valid_yaml_targeting_windows(self):
        from rita.firmware import yamlmini
        wf_path = REPO / ".github" / "workflows" / "installer.yml"
        text = wf_path.read_text()
        assert "windows-latest" in text
        assert "upload-artifact" in text
        assert "pyinstaller" in text.lower()

    def test_build_script_exists(self):
        ps1 = (PACKAGING / "build.ps1").read_text()
        assert "pyinstaller" in ps1.lower() and "iscc" in ps1.lower()
