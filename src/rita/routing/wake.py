"""Wake grammar (Fix 1, stage zero): pure timing/adjacency rules.

("hello" | "hi" | "hey") followed by the assistant's name within ~500 ms
wakes; a bare name wakes; a greeting with a pause and no name is just a
greeting. With word timestamps the 0.5 s rule is exact; without them,
greeting-immediately-followed-by-name adjacency is the documented proxy.
"""

from __future__ import annotations

from .grammar import GREETING_TOKENS
from .model import Utterance, WakeDecision, Word, normalize

MAX_GREETING_NAME_GAP_S = 0.5


class WakeGate:
    def __init__(self, name: str = "Rita") -> None:
        self.name = name
        self._name_norm = normalize(name)

    def feed(self, utt: Utterance) -> WakeDecision:
        tokens = utt.tokens
        if not tokens:
            return WakeDecision(woke=False)

        # Bare name (nothing but the name) always wakes.
        if list(tokens) == [self._name_norm]:
            return WakeDecision(woke=True, residual=None)

        if utt.words:
            return self._feed_timed(utt)
        return self._feed_untimed(tokens)

    # -- with word timestamps: the 0.5 s rule is exact -----------------------

    def _feed_timed(self, utt: Utterance) -> WakeDecision:
        words = utt.words
        for i, w in enumerate(words[:-1]):
            if normalize(w.text) not in GREETING_TOKENS:
                continue
            nxt = words[i + 1]
            if (normalize(nxt.text) == self._name_norm
                    and (nxt.start - w.end) <= MAX_GREETING_NAME_GAP_S):
                return WakeDecision(woke=True, residual=_residual_timed(words[i + 2:]))
        # Name as the first word also wakes ("Rita, build blinky").
        if normalize(words[0].text) == self._name_norm:
            return WakeDecision(woke=True, residual=_residual_timed(words[1:]))
        return WakeDecision(woke=False)

    # -- without timestamps: adjacency is the proxy --------------------------

    def _feed_untimed(self, tokens: tuple[str, ...]) -> WakeDecision:
        for i, t in enumerate(tokens[:-1]):
            if t in GREETING_TOKENS and tokens[i + 1] == self._name_norm:
                rest = " ".join(tokens[i + 2:])
                return WakeDecision(woke=True,
                                    residual=Utterance.from_text(rest) if rest else None)
        if tokens[0] == self._name_norm:
            rest = " ".join(tokens[1:])
            return WakeDecision(woke=True,
                                residual=Utterance.from_text(rest) if rest else None)
        return WakeDecision(woke=False)


def _residual_timed(words: tuple[Word, ...]) -> Utterance | None:
    if not words:
        return None
    return Utterance(text=" ".join(w.text for w in words), words=tuple(words),
                     t_start=words[0].start, t_end=words[-1].end)
