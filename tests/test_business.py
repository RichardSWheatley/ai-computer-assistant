"""Business tests: real PPTX generation, and Outlook/Teams over a fake Graph
session (no network). Graph send/post must be the outward_facing tier."""

import sys
from pathlib import Path

import pytest

from rita.business.graph import GraphClient

# Load the opt-in drop-in plugins directly (they're enabled=false in manifests).
_PLUGINS = Path(__file__).resolve().parents[1] / "plugins"
sys.path.insert(0, str(_PLUGINS / "outlook"))
sys.path.insert(0, str(_PLUGINS / "teams"))
sys.path.insert(0, str(_PLUGINS / "powerpoint"))


# --- PowerPoint (real file) ------------------------------------------------

def test_build_deck_writes_real_pptx(tmp_path):
    pptx = pytest.importorskip("pptx")  # noqa: F841
    from rita.business.pptx_builder import build_deck

    spec = {
        "title": "Q3 Review",
        "subtitle": "Board deck",
        "slides": [
            {"type": "section", "title": "Results"},
            {"title": "Highlights", "bullets": ["Revenue up", "Churn down"],
             "notes": "speak to growth"},
            {"title": "Revenue", "chart": {
                "kind": "bar", "categories": ["Q1", "Q2", "Q3"],
                "series": [{"name": "Rev", "values": [10, 14, 19]}]}},
            {"title": "ARR", "big_number": "$4.2M", "caption": "+38% YoY"},
        ],
    }
    out = tmp_path / "deck.pptx"
    path = build_deck(spec, str(out))
    assert Path(path).exists() and out.stat().st_size > 0

    # It's a valid presentation with a slide per spec entry + title slide.
    prs = pptx.Presentation(str(out))
    assert len(prs.slides) == 5


def test_build_deck_requires_title(tmp_path):
    pytest.importorskip("pptx")
    from rita.business.pptx_builder import build_deck
    with pytest.raises(ValueError):
        build_deck({"slides": []}, str(tmp_path / "x.pptx"))


def test_powerpoint_plugin_dispatch(tmp_path):
    pytest.importorskip("pptx")
    import plugin as pp  # plugins/powerpoint/plugin.py
    out = tmp_path / "d.pptx"
    res = pp.create().invoke("create_deck", {
        "spec": {"title": "Hello", "slides": [{"title": "One", "bullets": ["a"]}]},
        "out": str(out),
    })
    assert res.ok and out.exists()


# --- Graph + Outlook/Teams over a fake session -----------------------------

class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = "x"

    def json(self):
        return self._payload


class _FakeSession:
    """Records calls and returns canned JSON per path."""

    def __init__(self):
        self.calls = []

    def get(self, url, headers=None):
        self.calls.append(("GET", url))
        return _Resp({"value": [
            {"subject": "Welcome", "from": {"emailAddress": {"address": "a@co"}},
             "isRead": False},
            {"subject": "Invoice", "from": {"emailAddress": {"address": "b@co"}},
             "isRead": True},
        ]})

    def post(self, url, headers=None, json=None):
        self.calls.append(("POST", url, json))
        return _Resp({"id": "msg-1"})


def test_outlook_summarize_and_draft():
    # import the outlook plugin module explicitly
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "outlook_plugin", str(_PLUGINS / "outlook" / "plugin.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    g = GraphClient(token="t", session=_FakeSession())
    plugin = mod.OutlookPlugin(client=g)

    summary = plugin.invoke("summarize_inbox", {"count": 5})
    assert summary.ok and "2 messages" in summary.output and "unread" in summary.output

    draft = plugin.invoke("draft_email",
                          {"to": ["x@co"], "subject": "Hi", "body": "Hello"})
    assert draft.ok and "draft created" in draft.output

    # send is the outward_facing tier
    tiers = {s.name: s.permission_tier for s in plugin.describe()}
    assert tiers["send_email"] == "outward_facing"
    assert tiers["summarize_inbox"] == "read_only"


def test_teams_post_is_outward_facing():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "teams_plugin", str(_PLUGINS / "teams" / "plugin.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    g = GraphClient(token="t", session=_FakeSession())
    plugin = mod.TeamsPlugin(client=g)
    res = plugin.invoke("post_message",
                        {"team_id": "T", "channel_id": "C", "text": "hi"})
    assert res.ok and "posted message" in res.output
    assert plugin.describe()[0].permission_tier == "outward_facing"


def test_graph_send_mail_hits_sendmail_endpoint():
    sess = _FakeSession()
    g = GraphClient(token="t", session=sess)
    g.send_mail(["x@co"], "Subj", "Body")
    assert any(c[0] == "POST" and c[1].endswith("/me/sendMail") for c in sess.calls)
