# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.

## [0.3.0] - 2026-07-28

### Added
- **Fix 2 — verification resolution** (`aica.firmware`): static index of
  `samples/**/sample.yaml` + `tests/**/testcase.yaml` (platform_allow,
  filter, harness, depends_on, tags) built at `sync`, saved to
  `~/.rita/verification-index.json`. Pure data, no LLM. Board-compat
  filtering + term ranking in `find()`.
- `boards.json` generation from `boards/**/board.yml` + twister platform
  yamls, merged with the twister hardware map; derived spoken aliases feed
  the Fix 1 router after the first sync.
- Fit judge (`judge_fit`): Claude judges fit ONLY — one bounded call over
  the index's top matches; cannot introduce non-candidates.
- Test writer (`write_ztest`): no match -> Claude authors a ztest with a
  validated `testcase.yaml` so twister gates it like everything else.
- `resolve_verification`: the find-or-write pipeline entry.
- **Workspace MCP server** (`aica.mcpserver`, `mcp-serve` CLI): stdio server
  exposing find_verification / board_info / list_boards / sample_lookup /
  read_workspace_file / grep_workspace — read-only, workspace-rooted,
  traversal-guarded. `mcp` SDK is an optional extra.
- Vendored YAML-subset parser (`yamlmini`) with pyyaml fallback
  (`.[firmware]` extra) to keep zero required deps.
- `sync` CLI command; fixture Zephyr workspace for hermetic tests.
- Spec: `docs/specs/verification-resolution.md`.

## [0.2.0] - 2026-07-28

### Added
- **Fix 1 — grammar-first routing** (`aica.routing`): a pure, table-driven
  router over domain vocabulary (work verbs, board names from boards.json,
  samples, peripherals). Anything naming a board/sample/artifact is work;
  interrogatives and unmatched utterances fall back to chat — inverted from
  the old LLM-guesses-intent design.
- Wake grammar as stage zero (`WakeGate`): greeting + name within 0.5 s
  (word timestamps), bare name, one-utterance wake+command; greeting with a
  pause and no name is not a wake event.
- `RouterShell` in the voice loop: wake -> route -> handlers; the assistant's
  spoken name is config data, renameable by voice, persisted across restart.
- Packaged board-vocabulary seed (`firmware/data/boards.seed.json`) so
  routing works before the first workspace sync.
- STT word-timestamp support: `Utterance` value type,
  `WhisperSTT.transcribe_utterance`, scriptable `FakeSTT`.
- Spec: `docs/specs/project-work-routing.md`.

## [0.1.1] - 2026-07-28

### Added
- RITA process scaffolding per the directive: `BRIEF.md`, `CLAUDE.md`,
  `docs/DECISIONS-LOG.md`, `docs/specs/`.
- `aica.home`: the `~/.rita/` data root (`RITA_HOME` override), path
  constants, and one-shot `~/.aica/` migration (incl. `boards.json`).
- `RitaConfig` persisted at `~/.rita/config` (TOML): assistant spoken name
  (default "Rita"), Zephyr workspace path, hardware map, iterate-loop
  budgets, device-tier gate.

### Changed
- Audio, screenshot, and sandbox paths moved from cwd-relative `.aica/…` to
  the `~/.rita/` home.

## [0.1.0]

- AICA MVP skeleton: agent loop, plugins, voice I/O, worker protocol, docs.
