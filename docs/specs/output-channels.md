# Spec: Two output channels (Fix 5)

## Problem

Reading code aloud is a **test failure**, not a style issue. Every brain
response must split into:

- **speech** — at most 2 conversational sentences: what happened, what's
  next;
- **screen** — everything (code, diffs, logs, file paths), untouched.

## Design (`rita.ui.channels.split_response`)

The brain (chat model / claude-worker prompts) is *asked* to emit both
channels, but the **shell's deterministic strip is the guarantee** — it is
applied unconditionally to whatever the brain returns:

1. Fenced code blocks (```…```) are removed from the speech path.
2. Diff/patch lines (`diff --git`, `index …`, `@@ …`, leading `+`/`-`),
   log-like lines, and lines that are mostly symbols are removed.
3. Inline code spans, URLs, and path-like tokens (absolute, `~/`, drive
   letters, or anything with a code file extension) are removed.
4. What remains is capped at `max_sentences` (default 2).
5. If nothing conversational survives, speech falls back to
   "The details are on your screen."

`screen` is always the original response, byte-for-byte.

`VoiceLoop` speaks only `split_response(reply).speech` and hands
`reply.screen` to an optional `on_screen` sink — so even a handler that
ignores the two-channel instruction cannot leak code into TTS. Streaming:
`PausableSpeaker.say` is non-blocking and sentence-chunked, so the first
sentence plays while the rest of the response is still being produced.

## Acceptance criteria (each is a test)

- A response containing a fenced block produces speech with **zero code
  tokens** (no backticks, braces, or code lines); the screen channel shows
  the full artifact.
- Inline paths, URLs, and diff hunks never reach speech.
- Speech never exceeds 2 sentences, however long the response.
- A code-only response speaks the fallback sentence.
- Speech output begins before the full response finishes being handled
  (`say()` does not block on playback).
