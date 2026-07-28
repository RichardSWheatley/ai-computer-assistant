"""Proves the Python<->worker boundary works end to end by spawning the
reference worker as a real subprocess and driving it over the protocol."""

from rita.app import build_assistant
from rita.config import load_config
from rita.workers import protocol as P
from rita.workers.client import WorkerClient


def test_worker_ping_and_actions():
    with WorkerClient() as wc:
        info = wc.call(P.M_PING)
        assert info["version"] == P.PROTOCOL_VERSION

        cap = wc.call(P.M_CAPTURE)
        assert "summary" in cap and isinstance(cap["elements"], list)

        clicked = wc.call(P.M_CLICK, {"x": 5, "y": 9, "button": "left"})
        assert "(5,9)" in clicked["detail"]

        typed = wc.call(P.M_TYPE, {"text": "hello"})
        assert "5 chars" in typed["detail"]


def test_protocol_roundtrip_encoding():
    req = P.Request(id=7, method=P.M_HOTKEY, params={"keys": ["ctrl", "c"]})
    parsed = P.parse_request(req.encode())
    assert parsed.id == 7 and parsed.method == P.M_HOTKEY
    resp = P.Response.decode(P.ok(7, {"detail": "x"}).encode())
    assert resp.ok and resp.result["detail"] == "x"


def test_assistant_runs_over_native_worker():
    cfg = load_config()
    cfg.use_native_worker = True   # flip to the polyglot path
    asst = build_assistant(cfg)
    result = asst.run("type_text hi")
    assert result.finished is True
    # Actions were served by the worker process, not the in-process controller.
    assert any("[ref]" in (s.detail or "") for s in result.steps)
