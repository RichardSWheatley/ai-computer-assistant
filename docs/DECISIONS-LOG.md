# Decisions log

Compromises, proxies, and deferred decisions — with the reason and what would
remove them. Newest first. (Required by the working rules in `CLAUDE.md`.)

## 2026-07-28 — Phase 1 (Fix 1)

- **Untimed wake proxy.** When the STT backend provides no word timestamps,
  the 500 ms greeting→name rule degrades to greeting-immediately-followed-by-
  name adjacency within one utterance. Removed when all shipped STT paths
  emit word timings (WhisperSTT already does via `word_timestamps=True`).
- **Fixed-window MicRecorder blurs inter-utterance pauses.** "hello" + 1 s
  pause + "Rita" across two recordings never wakes (correct); within one
  recording, word timestamps catch it. A VAD-segmented recorder would sharpen
  this but is out of scope (scope rule: harden, don't widen).
- **Chat fallback is a canned reply for now.** Wiring a real chat model into
  the fallback arrives with the supervisor's module wiring (Fix 6); routing
  correctness doesn't depend on it.

## 2026-07-28 — Phase 0

- **`RitaConfig` writes TOML by hand** (no `tomli-w` dependency). The config
  is a flat table of scalars, so a 15-line serializer keeps the
  zero-required-deps rule. Removed if the config ever needs nesting.
- **Legacy `~/.aica/` migration copies, never moves.** Safer for users with
  both versions installed during the transition; the old dir can be deleted
  manually after verifying. Revisit at the Phase 7 rename.
