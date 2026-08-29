"""Real CERBERUS acquisition + the adapter pinned to its contract.

github.com/RichardSWheatley/cerberus: `python -m cerberus.cli scan <target>`
from the clone; exit 0 = approve, 1 = request changes, 2 = block. Tests use
a local git fixture repo so the suite stays offline; the user's PC clones
the real URL.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"

# A stand-in cerberus repo: cerberus/cli.py scans the target dir and fails
# with a JSON finding while a marker file exists — exit 1 (request changes).
CLI_BODY = '''\
import json, sys
from pathlib import Path
target = Path(sys.argv[-1])
if (target / "bad_marker").exists():
    print(json.dumps({"findings": [{"file": "src/main.c", "line": 7,
                                    "severity": "high",
                                    "message": "unchecked return value"}]}))
    sys.exit(1)
sys.exit(0)
'''


@pytest.fixture()
def fixture_repo(tmp_path) -> Path:
    """A real local git repo shaped like CERBERUS (cerberus/cli.py)."""
    repo = tmp_path / "cerberus-src"
    (repo / "cerberus").mkdir(parents=True)
    (repo / "cerberus" / "cli.py").write_text(CLI_BODY)
    (repo / "cerberus" / "__init__.py").write_text("")
    (repo / "README.md").write_text("CERBERUS fixture\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q", "-b", "main"],
                ["git", "add", "-A"],
                ["git", "-c", "user.name=t", "-c", "user.email=t@t",
                 "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=repo, check=True, env={**env,
                       "PATH": __import__("os").environ["PATH"]})
    return repo


@pytest.fixture()
def rita_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "rita"
    monkeypatch.setenv("RITA_HOME", str(home))
    return home


class TestAcquisition:
    def test_install_clones_into_rita_home(self, fixture_repo, rita_home):
        from rita.firmware.cerberus_setup import detect_cerberus, install_cerberus
        res = install_cerberus(url=str(fixture_repo))
        assert res.ok
        assert detect_cerberus() == rita_home / "cerberus"
        assert (rita_home / "cerberus" / "cerberus" / "cli.py").exists()

    def test_install_is_idempotent_pulls_updates(self, fixture_repo, rita_home):
        from rita.firmware.cerberus_setup import install_cerberus
        assert install_cerberus(url=str(fixture_repo)).ok
        res2 = install_cerberus(url=str(fixture_repo))
        assert res2.ok
        assert "updat" in res2.detail.lower() or "pull" in res2.detail.lower()

    def test_missing_git_is_an_honest_failure(self, fixture_repo, rita_home):
        from rita.firmware.cerberus_setup import install_cerberus
        res = install_cerberus(url=str(fixture_repo), git="/no/such/git")
        assert res.ok is False
        assert "git" in res.detail.lower()

    def test_detect_absent_is_none(self, rita_home):
        from rita.firmware.cerberus_setup import detect_cerberus
        assert detect_cerberus() is None


class TestDefaultChecker:
    def test_scan_invocation_shape(self, tmp_path):
        from rita.firmware.cerberus_setup import default_checker
        clone = tmp_path / "clone"
        clone.mkdir()
        checker = default_checker(clone)
        assert checker.argv == [sys.executable, "-m", "cerberus.cli", "scan"]
        assert checker.cwd == str(clone)

    def test_deep_mode_uses_analyze_with_unity(self, tmp_path):
        from rita.firmware.cerberus_setup import default_checker
        clone = tmp_path / "clone"
        (clone / "unity").mkdir(parents=True)
        checker = default_checker(clone, deep=True)
        # Deep is ADDITIVE: the deterministic scan always runs first,
        # the LLM analyze runs after a clean scan — never either/or.
        assert "scan" in checker.scan.argv
        assert "analyze" in checker.analyze.argv
        assert "--unity-dir" in checker.analyze.argv

    def test_acquired_gate_end_to_end(self, fixture_repo, rita_home, tmp_path):
        # Clone -> default checker -> REAL subprocess verdicts both ways.
        from rita.firmware.cerberus_setup import (default_checker,
                                                  detect_cerberus,
                                                  install_cerberus)
        install_cerberus(url=str(fixture_repo))
        checker = default_checker(detect_cerberus())
        target = tmp_path / "code"
        (target / "src").mkdir(parents=True)
        (target / "bad_marker").write_text("")
        bad = checker.check(target)
        assert bad.ok is False
        assert "unchecked return value" in bad.findings[0].log_excerpt
        assert "request changes" in bad.findings[0].reason.lower()
        (target / "bad_marker").unlink()          # "the patch"
        assert checker.check(target).ok is True


class TestExitCodeVerdicts:
    def _cli(self, tmp_path, code: int) -> "CerberusCli":
        from rita.firmware.static_check import CerberusCli
        script = tmp_path / "c.py"
        script.write_text(f"import sys; print('finding text'); sys.exit({code})\n")
        return CerberusCli([sys.executable, str(script)])

    def test_exit_1_is_request_changes(self, tmp_path):
        res = self._cli(tmp_path, 1).check(tmp_path)
        assert res.ok is False
        assert "request changes" in res.findings[0].reason.lower()

    def test_exit_2_is_block(self, tmp_path):
        res = self._cli(tmp_path, 2).check(tmp_path)
        assert res.ok is False
        assert "block" in res.findings[0].reason.lower()


class TestSupervisorAutoDetect:
    def make_sup(self, tmp_path, **cfg_kw):
        from rita.config import RitaConfig
        from rita.supervisor import Supervisor
        from rita.voice.tts import FakeTTS
        return Supervisor(rita_cfg=RitaConfig(workspace=str(WS), **cfg_kw),
                          config_path=tmp_path / "config", tts=FakeTTS(),
                          workdir=tmp_path / "work")

    def test_detected_clone_wires_the_gate_with_no_config(
            self, fixture_repo, rita_home, tmp_path):
        from rita.firmware.cerberus_setup import install_cerberus
        from rita.firmware.static_check import CerberusCli
        install_cerberus(url=str(fixture_repo))
        checker = self.make_sup(tmp_path)._make_static_checker()
        assert isinstance(checker, CerberusCli)
        assert "scan" in checker.argv

    def test_explicit_command_still_wins(self, fixture_repo, rita_home, tmp_path):
        from rita.firmware.cerberus_setup import install_cerberus
        install_cerberus(url=str(fixture_repo))
        checker = self.make_sup(
            tmp_path, cerberus_command="mytool --check")._make_static_checker()
        assert checker.command == "mytool --check"

    def test_nothing_detected_is_none(self, rita_home, tmp_path):
        assert self.make_sup(tmp_path)._make_static_checker() is None


class TestCli:
    def test_rita_cerberus_install_command(self, fixture_repo, rita_home):
        from rita.__main__ import main
        rc = main(["cerberus", "install", "--url", str(fixture_repo)])
        assert rc == 0
        from rita.firmware.cerberus_setup import detect_cerberus
        assert detect_cerberus() is not None
