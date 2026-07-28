# Decisions log

Compromises, proxies, and deferred decisions — with the reason and what would
remove them. Newest first. (Required by the working rules in `CLAUDE.md`.)

## 2026-07-28 — Phase 2 (Fix 2)

- **twister `filter:` expressions are recorded, not evaluated.** Evaluating
  them needs a devicetree/Kconfig context only twister has — and twister is
  the gate anyway. The index may therefore over-offer candidates; the fit
  judge and twister itself weed those out.
- **`yamlmini` subset parser** covers block mappings/lists/scalars only.
  Real workspaces with exotic YAML (anchors, flow style) need
  `pip install .[firmware]` (pyyaml is tried first when present). Chosen to
  keep the zero-required-deps rule.
- **Index ranking is bag-of-words term overlap** (tags/id/name/description/
  depends_on). Good enough because Claude judges fit on the top matches
  anyway; smarter ranking is a hardening option, not a widening need.

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
