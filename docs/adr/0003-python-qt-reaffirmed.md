# ADR 0003 — Python + Qt reaffirmed for RITA; Rust revisit triggers named

**Status:** accepted · **Date:** 2026-08-29 · **Supersedes:** nothing —
reaffirms ADR 0001 for the RITA era, narrows ADR 0002.

## Context

The owner asked (post-v0.28.0) whether RITA should have been built on
Rust + Slint/Tauri to run faster on current hardware, keeping a remote
coding agent until a higher-TOPS machine arrives.

What RITA actually is today: ~12k lines of Python conducting native
workhorses. Qt (C++, via PySide6) renders the GUI. Speech-to-text is
faster-whisper on **CTranslate2 (C++)**. The firmware work is
`arm-none-eabi-gcc`, QEMU, `west`/twister — native subprocesses. The
coding agent is a remote LLM service. Python holds the routing tables,
the gate orchestration, the learning layer, and the seams.

Where the felt time goes:

| Cost | Bound by | Changed by a Rust rewrite? |
|---|---|---|
| Whisper transcription | silicon (TOPS) + C++ runtime | **No** |
| Coding-agent calls | network + service | **No** |
| Builds/tests | gcc/QEMU/twister | **No** |
| Downloads | network | **No** |
| App startup | frozen-Python bootstrap | Yes (~2 s → ~instant) |
| Memory footprint | Qt + Python runtime | Yes (hundreds → tens of MB) |
| Installer size | bundled runtime | Yes (105 MB → ~10 MB) |
| Packaging bug class | PyInstaller | Yes — eliminated |

## Decision

**Python + Qt stays.** The wins a rewrite offers are comfort wins
(startup, footprint, binary size, the frozen-Python failure class);
the costs are rewriting ~12k lines and 519 tests mid-evolution, in
the ecosystem where the AI seams (MCP SDK, whisper bindings, agent
CLIs) are thinnest. The performance the owner will feel most is
model-bound and network-bound — untouched by language. A higher-TOPS
machine accelerates Whisper (and any future local models) regardless
of what language the app is written in.

## Revisit triggers (any one reopens this ADR)

1. **The feature set stabilizes** — the `docs/SECTIONS.md` deep passes
   are complete and the product stops changing weekly.
2. **A measured, reproducible slowness traceable to Python itself** —
   profiled, not vibes: not models, not network, not native tools.
3. **The packaging failure class recurs** despite the frozen-bundle
   smoke gate.

If reopened, the path is **incremental**: a native shell (Rust +
Slint/Tauri) over the existing deterministic core and seams — per ADR
0002's "each part in the language that wins" — never a big-bang
rewrite.
