"""Fix 6: supervisor + versioned module processes.

The toy module is a REAL child process speaking the RPC protocol — these
tests prove the handshake, timeouts, event demux, version drain, instance
caps, exclusivity, and crash isolation against actual subprocesses.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
TOY = FIXTURES / "toy_module.py"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"

SUP_VERSION = "0.7.0"


def install_toy(root: Path, *, name="toy", version="1.0.0", max_instances=2,
                exclusivity=(), min_supervisor="0.1.0", entrypoint=None):
    d = root / name / version
    d.mkdir(parents=True, exist_ok=True)
    ep = entrypoint or [sys.executable, str(TOY), version]
    text = (f'name = "{name}"\nversion = "{version}"\n'
            f"entrypoint = {json.dumps(ep)}\n"
            f'capabilities = ["demo"]\n'
            f"max_instances = {max_instances}\n"
            f'min_supervisor = "{min_supervisor}"\n')
    if exclusivity:
        text += f"\n[exclusivity]\nkeys = {json.dumps(list(exclusivity))}\n"
    (d / "manifest.toml").write_text(text)
    (root / name / "current").write_text(version)


@pytest.fixture()
def registry(tmp_path):
    from rita.modules.registry import ModuleRegistry
    reg = ModuleRegistry(root=tmp_path / "modules",
                         supervisor_version=SUP_VERSION)
    yield reg
    reg.shutdown_all()


class TestManifest:
    def test_parse(self, tmp_path):
        from rita.modules.manifest import load_manifest
        install_toy(tmp_path, exclusivity=["serial_port"])
        m = load_manifest(tmp_path / "toy" / "1.0.0" / "manifest.toml")
        assert m.name == "toy"
        assert m.version == "1.0.0"
        assert m.entrypoint[0] == sys.executable
        assert m.max_instances == 2
        assert m.exclusivity_keys == ("serial_port",)

    def test_missing_fields_rejected(self, tmp_path):
        from rita.modules.manifest import ManifestError, load_manifest
        p = tmp_path / "manifest.toml"
        p.write_text('name = "x"\n')
        with pytest.raises(ManifestError):
            load_manifest(p)

    def test_min_supervisor_newer_than_us_is_a_launch_error(self, registry, tmp_path):
        from rita.modules.registry import ModuleCompatError
        install_toy(registry.root, min_supervisor="99.0.0")
        with pytest.raises(ModuleCompatError):
            registry.launch("toy")


class TestHandleAndProtocol:
    def test_handshake_call_events(self, registry):
        install_toy(registry.root)
        h = registry.launch("toy")
        assert h.call("start", {"value": 42}) == {"started": True}
        assert h.call("status")["value"] == 42
        # pause_at_checkpoint round-trips through a real child process,
        # and its event streams independently of the response.
        assert h.call("pause_at_checkpoint", {"stage": "BUILD"}) == {"paused_at": "BUILD"}
        deadline = time.time() + 2
        seen = []
        while time.time() < deadline and not any(e[0] == "checkpoint" for e in seen):
            seen += h.drain_events()
            time.sleep(0.01)
        assert ("progress", {"pct": 50}) in seen
        assert ("checkpoint", {"stage": "BUILD"}) in seen

    def test_per_call_timeout_is_honored(self, registry):
        from rita.modules.handle import ModuleCallTimeout
        install_toy(registry.root)
        h = registry.launch("toy")
        with pytest.raises(ModuleCallTimeout):
            h.call("slow", {"seconds": 5}, timeout=0.2)

    def test_handshake_failure_is_a_launch_error(self, registry):
        from rita.modules.handle import ModuleError
        install_toy(registry.root, name="garbage", entrypoint=[
            sys.executable, "-c",
            "import time; print('this is not json', flush=True); time.sleep(10)"])
        with pytest.raises(ModuleError):
            registry.launch("garbage", handshake_timeout=1.0)

    def test_crash_isolation_supervisor_survives(self, registry):
        from rita.modules.handle import ModuleError
        install_toy(registry.root)
        h = registry.launch("toy")
        with pytest.raises(ModuleError):
            h.call("crash", timeout=5)
        assert h.alive is False
        assert "boom" in h.stderr_tail()
        # The registry keeps working: the dead instance no longer counts.
        h2 = registry.launch("toy")
        assert h2.call("status")["version"] == "1.0.0"


class TestRegistry:
    def test_update_flip_drains_old_version(self, registry):
        install_toy(registry.root, version="1.0.0")
        h1 = registry.launch("toy")
        assert h1.call("status")["version"] == "1.0.0"

        # Drop a new version dir + flip current while v1 is still running.
        install_toy(registry.root, version="2.0.0")
        assert registry.current("toy") == "2.0.0"
        # The running instance drains on the old version...
        assert h1.call("status")["version"] == "1.0.0"
        # ...and the next spawn uses the new one.
        h2 = registry.launch("toy")
        assert h2.call("status")["version"] == "2.0.0"

    def test_max_instances_enforced(self, registry):
        from rita.modules.registry import ModuleBusy
        install_toy(registry.root, max_instances=1)
        registry.launch("toy")
        with pytest.raises(ModuleBusy):
            registry.launch("toy")

    def test_exclusive_claims(self, registry):
        from rita.modules.registry import ModuleBusy
        install_toy(registry.root, max_instances=4,
                    exclusivity=["serial_port"])
        registry.launch("toy", claims={"serial_port": "/dev/ttyACM0"})
        registry.launch("toy", claims={"serial_port": "/dev/ttyACM1"})  # ok
        with pytest.raises(ModuleBusy):
            registry.launch("toy", claims={"serial_port": "/dev/ttyACM0"})
        with pytest.raises(ModuleBusy):        # exclusivity key must be claimed
            registry.launch("toy")

    def test_discover_and_list(self, registry):
        install_toy(registry.root, version="1.0.0")
        install_toy(registry.root, version="2.0.0")
        found = registry.discover()
        assert found["toy"] == ["1.0.0", "2.0.0"]


class TestDevInstallAndStubs:
    def test_dev_install_writes_all_module_manifests(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.modules.install import dev_install
        from rita.modules.registry import ModuleRegistry
        installed = dev_install()
        names = {m.name for m in installed}
        assert {"voice-in", "voice-out", "zephyr-runner", "claude-worker",
                "scaffold", "cerberus", "joulescope"} <= names
        reg = ModuleRegistry(supervisor_version=SUP_VERSION)
        assert reg.current("joulescope")
        jl = next(m for m in installed if m.name == "joulescope")
        assert jl.max_instances == 1                    # one probe, ever

    def test_stub_modules_are_honest(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.modules.install import dev_install
        from rita.modules.registry import ModuleRegistry
        dev_install()
        reg = ModuleRegistry(supervisor_version=SUP_VERSION)
        try:
            h = reg.launch("cerberus")
            res = h.call("start", timeout=10)
            assert res.get("ok") is False               # never fake capability
            assert "not configured" in res.get("error", "")
            h2 = reg.launch("joulescope")
            res2 = h2.call("start", timeout=10)
            assert res2.get("ok") is False
            assert "not present" in res2.get("error", "")
        finally:
            reg.shutdown_all()


class TestSupervisor:
    def make_supervisor(self, tmp_path):
        from rita.config import RitaConfig
        from rita.firmware.claude import FakeClaude
        from rita.firmware.west import FakeWest
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS

        cfg = RitaConfig(workspace=str(WS))
        fit = json.dumps({"fit": "sample.basic.blinky", "reason": "fits"})
        sup = Supervisor(
            rita_cfg=cfg, config_path=tmp_path / "config",
            tts=FakeTTS(),
            runner=FakeWest(build_seq=["ok"], twister_seq=["pass.json"],
                            fixtures_dir=TW),
            claude=FakeClaude(completions=[fit]),
            workdir=tmp_path / "work")
        return sup

    def test_wake_and_work_runs_the_pipeline(self, tmp_path):
        sup = self.make_supervisor(tmp_path)
        said = sup.shell.handle("hello rita build blinky")
        assert "start" in said.lower() or "on it" in said.lower()
        tid = sup.manager.latest_active() or "task-1"
        assert sup.manager.wait_state(tid, "DONE", timeout=5)
        assert sup.manager.report(tid).result.outcome == "green"

    def test_work_without_workspace_asks_for_sync(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.config import RitaConfig
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        sup = Supervisor(rita_cfg=RitaConfig(workspace=None),
                         config_path=tmp_path / "config", tts=FakeTTS(),
                         workdir=tmp_path / "work")
        said = sup.shell.handle("hello rita build blinky")
        assert "sync" in said.lower()

    def test_control_words_reach_manager_and_speaker(self, tmp_path):
        sup = self.make_supervisor(tmp_path)
        sup.shell.handle("hello rita")
        said = sup.shell.handle("pause")
        assert "paus" in said.lower()
