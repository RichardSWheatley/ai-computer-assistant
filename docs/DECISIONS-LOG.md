# Decisions log

Compromises, proxies, and deferred decisions — with the reason and what would
remove them. Newest first. (Required by the working rules in `CLAUDE.md`.)

## 2026-07-28 — Phase 0

- **`RitaConfig` writes TOML by hand** (no `tomli-w` dependency). The config
  is a flat table of scalars, so a 15-line serializer keeps the
  zero-required-deps rule. Removed if the config ever needs nesting.
- **Legacy `~/.aica/` migration copies, never moves.** Safer for users with
  both versions installed during the transition; the old dir can be deleted
  manually after verifying. Revisit at the Phase 7 rename.
