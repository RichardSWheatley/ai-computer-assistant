"""Grammar-first router (Fix 1): pure function, table-driven.

Every acceptance criterion from docs/specs/project-work-routing.md is a row
or test here.
"""

from __future__ import annotations

import pytest

from rita.config import load_rita_config
from rita.routing.model import Utterance
from rita.routing.router import route
from rita.routing.vocabulary import Vocabulary


@pytest.fixture(scope="module")
def vocab() -> Vocabulary:
    return Vocabulary.seed()


def r(text: str, vocab: Vocabulary):
    return route(Utterance.from_text(text), vocab)


# --- The directive's flagship case ----------------------------------------

def test_write_an_application_for_apollo510_dispatches_to_scaffold(vocab):
    d = r("Write me an application for the apollo510 that blinks an LED", vocab)
    assert d.kind == "work"
    assert d.verb == "scaffold"
    assert d.entities.board == "apollo510_evb"
    assert d.entities.peripheral == "led"


# --- Every firmware-loop verb routes --------------------------------------

@pytest.mark.parametrize("text,verb", [
    ("build blinky", "build"),
    ("compile the blinky sample", "build"),
    ("flash blinky to the apollo510", "flash"),
    ("measure the power on the apollo510", "measure"),
    ("run the samples", "run_samples"),
    ("run blinky", "run_samples"),
    ("report on the last run", "report"),
    ("create an application for the apollo510", "scaffold"),
])
def test_each_verb_routes_to_work(vocab, text, verb):
    d = r(text, vocab)
    assert d.kind == "work"
    assert d.verb == verb


# --- Entity detection ------------------------------------------------------

def test_board_name_detection(vocab):
    d = r("flash blinky to the apollo510", vocab)
    assert d.entities.board == "apollo510_evb"
    assert d.entities.sample == "blinky"


def test_board_alias_with_space(vocab):
    d = r("build blinky for the apollo 510", vocab)
    assert d.entities.board == "apollo510_evb"


def test_naming_a_board_without_a_verb_is_work(vocab):
    d = r("blinky on the apollo510", vocab)
    assert d.kind == "work"
    assert d.matched_by == "entity_only"


# --- Chat: interrogatives and the fallback ---------------------------------

def test_tell_me_about_a_board_stays_chat(vocab):
    d = r("tell me about the apollo510", vocab)
    assert d.kind == "chat"


@pytest.mark.parametrize("text", [
    "what is a zephyr sample",
    "how does the scheduler work",
    "explain devicetree overlays",
])
def test_interrogatives_are_chat(vocab, text):
    assert r(text, vocab).kind == "chat"


def test_ambiguous_utterance_falls_back_to_chat(vocab):
    d = r("nice weather we are having today", vocab)
    assert d.kind == "chat"
    assert d.matched_by == "fallback"


# --- Control and rename -----------------------------------------------------

@pytest.mark.parametrize("text", ["pause", "resume", "stop", "cancel", "stop please"])
def test_control_words(vocab, text):
    assert r(text, vocab).kind == "control"


@pytest.mark.parametrize("text,name", [
    ("your name is now vera", "vera"),
    ("call yourself iris", "iris"),
    ("change your name to juno", "juno"),
])
def test_rename_patterns(vocab, text, name):
    d = r(text, vocab)
    assert d.kind == "rename"
    assert d.argument == name


# --- Purity ---------------------------------------------------------------

def test_route_is_deterministic(vocab):
    u = Utterance.from_text("build blinky for the apollo510")
    assert route(u, vocab) == route(u, vocab)


# --- Shell: wake + route in one utterance, rename persistence ---------------

class TestRouterShell:
    def make_shell(self, tmp_path, **kw):
        from rita.voice.loop import RouterShell
        return RouterShell(config_path=tmp_path / "config", **kw)

    def test_hello_rita_build_blinky_wakes_and_routes(self, tmp_path):
        seen = []
        shell = self.make_shell(tmp_path, work=lambda d: seen.append(d) or "on it")
        said = shell.handle(Utterance.from_text("hello rita build blinky"))
        assert said == "on it"
        assert seen[0].verb == "build"
        assert seen[0].entities.sample == "blinky"

    def test_not_awake_ignores_non_wake_utterances(self, tmp_path):
        shell = self.make_shell(tmp_path)
        assert shell.handle(Utterance.from_text("build blinky")) == ""

    def test_voice_rename_persists_across_restart(self, tmp_path):
        shell = self.make_shell(tmp_path)
        shell.handle(Utterance.from_text("hello rita"))          # wake
        shell.handle(Utterance.from_text("your name is now vera"))
        # "Restart": a brand-new shell reading the same config file.
        assert load_rita_config(tmp_path / "config").assistant_name == "Vera"
        fresh = self.make_shell(tmp_path)
        assert fresh.handle(Utterance.from_text("hello vera")) != ""
        # A separate asleep shell no longer answers to the old name.
        still_asleep = self.make_shell(tmp_path)
        assert still_asleep.handle(Utterance.from_text("hello rita")) == ""
