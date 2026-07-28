# Decisions log

Compromises, proxies, and deferred decisions — with the reason and what would
remove them. Newest first. (Required by the working rules in `CLAUDE.md`.)

## 2026-07-28 — Workspace facts (post-rename)

- **The packaged boards seed is bootstrap vocabulary only.** It exists so
  the router can match board names before the first `rita sync`; every
  fact RITA *states* (board metadata, Zephyr version) comes from the
  synced workspace data, and the synced `boards.json` supersedes the seed
  for routing too. A missing fact (no `zephyr/VERSION`) is reported as
  missing, never guessed.

## 2026-07-28 — Phase 7 (rename)

- **Keyring service name stays `aica`** — renaming it would orphan every
  secret users already stored. Revisit only with a migration that copies
  entries forward.
- **Legacy `AICA_*` env names are honored (and the sandbox sets both
  marker spellings) for one release** so external workers keep working;
  drop in 0.9.
- **Historical CHANGELOG/DECISIONS entries keep their original `aica.*`
  module paths** — they describe the code as it was at that version.

## 2026-07-28 — Phase 6 (Fix 6)

- **The supervisor uses in-process seams (WestCli/ClaudeWorkerCli) for
  pipeline work by default**; module processes are launched via the
  registry when installed. Full module-backed pipeline wiring (a
  ZephyrRunner proxy over RPC) is a hardening step for the packaged
  install — the protocol, registry, drain, caps, and crash isolation are
  all in and tested against real child processes.
- **One in-flight request per handle** (events stream independently).
  The smallest concurrency model that supports checkpoints and progress;
  request pipelining can come later without a wire change.
- **`docs/ACCESS.md` (laptop access beyond the workspace) is deferred**
  until a capability actually needs it — the enumerated-permission rule is
  stated in the spec so nothing lands implicitly.

## 2026-07-28 — Phase 5 (Fix 5)

- **The speech strip is deliberately over-aggressive** (drops any token
  with a code-file extension, any mostly-symbol line). A false positive
  costs a slightly clipped sentence; a false negative reads code aloud —
  the spec calls that a test failure, so the bias is one-directional by
  design.

## 2026-07-28 — Phase 4 (Fix 4)

- **A chunk aborted mid-speech replays in full on RESUME** (position is the
  chunk index, not a character offset). Chunks are single sentences, so the
  repetition is at most one sentence — simpler and more robust than
  intra-utterance offsets, which pyttsx3 cannot honor anyway.
- **The <300 ms PAUSE guarantee is architectural** (chunk boundaries +
  immediate engine stop), proven deterministically with a blocking fake.
  Real pyttsx3 stop latency on the target OS gets measured at first bench;
  if it misbehaves, the fallback is shorter chunks.

## 2026-07-28 — Phase 3 (Fix 3)

- **A sim-test patch re-enters at BUILD** (the directive's "goto 2") even
  though twister rebuilds internally: a patch can break the compile, and a
  `west build` catches that in seconds without burning a twister cycle.
- **`WestCli` ignores twister's exit code on purpose** — `twister.json` is
  parsed as the gate result either way, per the never-scrape-stdout rule.
- **Real `west`/`claude -p` paths are `pragma: no cover`** here: this
  container has no Zephyr toolchain or claude CLI. The seams (`FakeWest`,
  `FakeClaude`) exercise the identical parsing/loop logic; the subprocess
  implementations run on the target machine. First bench milestone
  (docs/BENCH-PLAN.md, still to be scheduled) validates them for real.

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
