"""Worker sandboxing: env scrubbing, spawn kwargs, and a sandboxed round-trip."""

from aica.security.sandbox import SandboxPolicy, sandboxed_env, spawn_kwargs
from aica.workers import protocol as P
from aica.workers.client import WorkerClient


def test_sandboxed_env_drops_secrets_keeps_safe():
    base = {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "ANTHROPIC_API_KEY": "sk-ant-secret",
        "AICA_GRAPH_CLIENT_ID": "abc",
        "MY_API_TOKEN": "t",
        "AWS_SECRET_ACCESS_KEY": "x",
        "RANDOM_VAR": "nope",  # not allow-listed
    }
    env = sandboxed_env(SandboxPolicy(), base=base)
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/home/u"
    assert "ANTHROPIC_API_KEY" not in env
    assert "AICA_GRAPH_CLIENT_ID" not in env
    assert "MY_API_TOKEN" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "RANDOM_VAR" not in env          # not on the allow-list
    assert env["AICA_SANDBOX"] == "1" and env["AICA_NO_NETWORK"] == "1"


def test_spawn_kwargs_sets_env_and_cwd(tmp_path):
    pol = SandboxPolicy(workdir=str(tmp_path / "sbx"))
    kw = spawn_kwargs(pol)
    assert kw["cwd"].endswith("sbx")
    assert "AICA_SANDBOX" in kw["env"]


def test_worker_runs_under_sandbox():
    # The reference worker needs no secrets, so it must still work sandboxed.
    with WorkerClient(sandbox=SandboxPolicy()) as wc:
        info = wc.call(P.M_PING)
        assert info["version"] == P.PROTOCOL_VERSION
        assert wc.call(P.M_TYPE, {"text": "hi"})["detail"]
