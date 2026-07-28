"""Wake grammar (Fix 1, stage zero): greeting + name timing, bare name,
one-utterance wake+command."""

from __future__ import annotations

from rita.routing.model import Utterance, Word
from rita.routing.wake import WakeGate


def timed(*words: tuple[str, float, float]) -> Utterance:
    ws = tuple(Word(text=t, start=s, end=e) for t, s, e in words)
    return Utterance(text=" ".join(w.text for w in ws), words=ws,
                     t_start=ws[0].start if ws else 0.0,
                     t_end=ws[-1].end if ws else 0.0)


class TestWakeTiming:
    def test_greeting_then_name_within_half_second_wakes(self):
        gate = WakeGate("Rita")
        d = gate.feed(timed(("hello", 0.0, 0.3), ("rita", 0.5, 0.8)))
        assert d.woke is True

    def test_greeting_then_long_pause_then_name_does_not_wake(self):
        gate = WakeGate("Rita")
        d = gate.feed(timed(("hello", 0.0, 0.3), ("rita", 1.5, 1.8)))
        assert d.woke is False

    def test_greeting_alone_does_not_wake(self):
        gate = WakeGate("Rita")
        assert gate.feed(timed(("hello", 0.0, 0.3))).woke is False

    def test_greeting_with_other_words_no_name_does_not_wake(self):
        gate = WakeGate("Rita")
        assert gate.feed(Utterance.from_text("hello there everyone")).woke is False


class TestWakeForms:
    def test_bare_name_wakes(self):
        d = WakeGate("Rita").feed(Utterance.from_text("Rita"))
        assert d.woke is True
        assert d.residual is None or d.residual.text == ""

    def test_wake_and_command_in_one_utterance(self):
        d = WakeGate("Rita").feed(Utterance.from_text("hello Rita build blinky"))
        assert d.woke is True
        assert d.residual is not None
        assert d.residual.text == "build blinky"

    def test_untimed_adjacency_proxy(self):
        # No word timestamps: greeting immediately followed by name is a wake.
        assert WakeGate("Rita").feed(Utterance.from_text("hi rita")).woke is True

    def test_name_is_case_insensitive(self):
        assert WakeGate("Rita").feed(Utterance.from_text("HELLO RITA")).woke is True

    def test_configured_name_is_respected(self):
        gate = WakeGate("Vera")
        assert gate.feed(Utterance.from_text("hello vera")).woke is True
        assert gate.feed(Utterance.from_text("hello rita")).woke is False

    def test_timed_residual_carries_words_after_name(self):
        d = WakeGate("Rita").feed(timed(("hello", 0.0, 0.3), ("rita", 0.4, 0.7),
                                        ("flash", 0.9, 1.2), ("blinky", 1.3, 1.7)))
        assert d.woke is True
        assert d.residual.text == "flash blinky"
        assert len(d.residual.words) == 2
