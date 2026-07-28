"""Deterministic, grammar-first intent routing (Fix 1).

Not to be confused with `rita.llm.model_router`, which selects WHICH MODEL plans a
step for the legacy agent. This package decides WHAT HAPPENS with an
utterance — by matching, never by model judgment.
"""

from .model import Dispatch, Entities, Utterance, WakeDecision, Word
from .router import route
from .vocabulary import Vocabulary
from .wake import WakeGate

__all__ = ["Dispatch", "Entities", "Utterance", "WakeDecision", "Word",
           "route", "Vocabulary", "WakeGate"]
