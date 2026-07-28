# Spec: Project-work routing (Fix 1)

## Problem

Intent used to be guessed by an LLM (`classify_intent`-style): a model decided
chat-vs-work, so utterances like "write me an application for the apollo510
that blinks an LED" could misroute. Routing must be **matching, not semantic
judgment**.

## Design

The router is a **pure function**: utterance in, dispatch decision out. No
LLM, no I/O, table-driven tests. Chat is the **fallback** when nothing
matches — inverted from before.

### Stage zero: wake grammar (`aica.routing.wake.WakeGate`)

- `("hello" | "hi" | "hey") + <name>` with the name starting within
  **≤ 0.5 s** of the greeting ending → wake; the words after the name are the
  **residual** utterance, routed immediately (one-utterance wake+command).
- Bare `<name>` also wakes (empty residual → the shell answers a short
  acknowledgement).
- A greeting followed by a pause and **no name** in the same utterance is a
  plain greeting, **not** a wake event.
- `<name>` is config data (`~/.rita/config`, `assistant_name`, default
  "Rita"), changeable at runtime by voice ("your name is now X" → persisted
  via `save_rita_config`) — it survives restart.
- Timing uses per-word timestamps when the STT provides them
  (`Utterance.words`). When absent, greeting-immediately-followed-by-name
  adjacency within the same utterance is the proxy (see DECISIONS-LOG).

### Router (`aica.routing.router.route`)

`route(utterance, vocabulary, assistant_name) -> Dispatch`, evaluated in
order:

1. **Control words** (`pause`, `resume`, `continue`, `stop`, `cancel`) as the
   whole (normalized) utterance → `kind="control"`.
2. **Rename** ("your name is now X" / "call yourself X" / "change your name
   to X") → `kind="rename"`, `argument=X`.
3. **Interrogative shapes** ("tell me about…", "what is…", "how does…",
   "explain…", "describe…", …) → `kind="chat"` — *even when a board, sample,
   or peripheral is named*. "Tell me about the apollo510" is chat.
4. **Work verbs** over RITA's own domain vocabulary:
   `build`, `flash`, `measure`, `run_samples`, `report`,
   `scaffold` (write/create/make an application). A verb match →
   `kind="work"` with entities attached (`matched_by="verb+entity"` or
   `"verb"` when no entity is named).
5. **Entities without a verb**: anything naming a **board, sample, or
   artifact** in an imperative-shaped utterance is work
   (`matched_by="entity_only"`, `verb=None` — the pipeline resolves the
   default action). Board names come from `boards.json` (+ derived aliases:
   "apollo510" matches `apollo510_evb`); sample and peripheral terms from the
   vocabulary.
6. **Fallback**: nothing matched → `kind="chat"` (`matched_by="fallback"`).

### Dispatch model (`aica.routing.model`)

```
Word(text, start, end)                      # STT word timing (seconds)
Utterance(text, words, t_start, t_end)
Entities(board, sample, peripheral, artifact)
Dispatch(kind: wake_only|work|chat|control|rename,
         verb: build|flash|measure|run_samples|report|scaffold|None,
         entities, matched_by: verb|verb+entity|entity_only|control|fallback,
         argument, residual)
WakeDecision(woke, residual)
```

### Vocabulary (`aica.routing.vocabulary.Vocabulary`)

Loaded from `~/.rita/boards.json` and the verification index when present;
before the first workspace sync, a packaged seed
(`aica/firmware/data/boards.seed.json`) provides board vocabulary so routing
works out of the box. Aliases are derived (strip `_evb`/vendor suffixes,
spaced variants). Samples/peripherals have a small builtin seed
(blinky, hello_world, button; led, gpio, uart, i2c, spi, pwm, adc).

### Shell (`aica.voice.loop.RouterShell`)

Holds the `WakeGate` + persisted config; feeds utterances through wake → route
→ the registered handlers (`work`, `chat`, `control`). Work handlers are
placeholders until Fix 3 lands. Rename dispatches persist the new name and
re-arm the gate immediately.

## Acceptance criteria (each is a test)

- "Write me an application for the apollo510 that blinks an LED" →
  `(work, scaffold, board=apollo510_evb)` — cannot misroute.
- Each firmware-loop verb routes: build / flash / measure / run samples /
  report.
- Board-name detection: an utterance naming a board dispatches as work.
- Ambiguous utterance (no verb, no entity) falls back to chat.
- "Tell me about the apollo510" stays chat.
- "hello Rita build blinky" wakes **and** routes in one utterance.
- "hello" + 1 s pause (no name within 0.5 s) does **not** wake.
- Voice rename persists across restart (fresh config load sees the new name).
