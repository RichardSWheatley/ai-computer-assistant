"""The deterministic router (Fix 1): utterance in, dispatch decision out.

`route` is a pure function — no LLM, no I/O, no clock. Chat is the FALLBACK
when nothing matches; anything naming a board, sample, or artifact is work.
Evaluation order (first hit wins): control -> rename -> interrogative ->
work verb -> bare entity -> chat.
"""

from __future__ import annotations

from . import grammar
from .model import Dispatch, Entities, Utterance
from .vocabulary import Vocabulary


def _entities(norm: str, vocab: Vocabulary) -> Entities:
    artifact = next((t for t in norm.split() if t in grammar.ARTIFACT_TOKENS), None)
    return Entities(
        board=vocab.find_board(norm),
        sample=vocab.find_sample(norm),
        peripheral=vocab.find_peripheral(norm),
        artifact=artifact,
    )


def route(utt: Utterance, vocab: Vocabulary, assistant_name: str = "Rita") -> Dispatch:
    norm = utt.norm
    tokens = utt.tokens
    if not tokens:
        return Dispatch(kind="chat", matched_by="fallback", residual="")

    if grammar.is_control(tokens):
        control = next(t for t in tokens if t in grammar.CONTROL_TOKENS)
        return Dispatch(kind="control", matched_by="control", argument=control,
                        residual=norm)

    new_name = grammar.rename_target(norm)
    if new_name:
        return Dispatch(kind="rename", argument=new_name, matched_by="control",
                        residual=norm)

    # Handoff phrases BEFORE verb matching: "create a project to ..." must
    # not be swallowed by the scaffold verb "create".
    goal = grammar.project_goal(norm)
    if goal:
        return Dispatch(kind="project", argument=goal, matched_by="control",
                        residual=norm)

    # Toolset / learning / chat-binding phrases likewise beat the verb
    # table ("make a toolset ..." is not scaffold work) — chat handles them.
    if (grammar.toolset_request(norm) or grammar.is_learning_question(norm)
            or grammar.chat_bind_target(norm) or grammar.CHAT_NEW.match(norm)):
        return Dispatch(kind="chat", matched_by="control", residual=norm)

    if grammar.is_interrogative(norm):
        return Dispatch(kind="chat", matched_by="fallback", residual=norm)

    entities = _entities(norm, vocab)

    verb = next((grammar.VERB_TOKENS[t] for t in tokens if t in grammar.VERB_TOKENS),
                None)
    if verb is not None:
        has_entity = any((entities.board, entities.sample, entities.peripheral,
                          entities.artifact))
        # "run" is only the run-samples verb when a sample (or the word
        # "sample(s)") is in play; a bare "run whatever" stays generic work
        # only if some entity grounds it.
        if verb == "run_samples" and not (entities.sample or "sample" in norm
                                          or "samples" in norm):
            verb = None
        # "build me an example/app for X" with no existing sample named is a
        # request to CREATE something new — scaffold, not build.
        if verb == "build" and entities.artifact and not entities.sample:
            verb = "scaffold"
        if verb is not None:
            return Dispatch(kind="work", verb=verb, entities=entities,
                            matched_by="verb+entity" if has_entity else "verb",
                            residual=norm)

    # No verb: naming a board, sample, or artifact is still work.
    if entities.board or entities.sample or entities.artifact:
        return Dispatch(kind="work", verb=None, entities=entities,
                        matched_by="entity_only", residual=norm)

    return Dispatch(kind="chat", matched_by="fallback", residual=norm)
