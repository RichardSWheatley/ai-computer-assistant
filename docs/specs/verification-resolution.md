# Spec: Verification resolution (Fix 2) — find-or-write

## Problem

When work needs verifying, the system must find the sample/test that proves
the intent — or write one — without an LLM guessing over the filesystem.

## Design

Resolution order (`rita.firmware.resolve.resolve_verification`):

1. **Index, don't ask.** At workspace sync (`rita sync`), build a static
   index of `zephyr/samples/**/sample.yaml` and `zephyr/tests/**/testcase.yaml`:
   `platform_allow`, `integration_platforms`, `filter`, `harness`,
   `depends_on`, `tags`, plus name/description/README path. Filter by board
   compatibility, rank by requested peripheral/subsystem term overlap.
   **Pure data. No LLM.** The index lives at
   `~/.rita/verification-index.json`, next to `boards.json`.
2. **the coding agent judges fit only.** The top matches go to the coding agent as a single
   bounded call over each candidate's README + yaml: "does this verify
   *this* intent?" — answer is a choice + reason
   (`rita.firmware.fit.judge_fit`). the coding agent picks among indexed candidates;
   it cannot introduce new ones.
3. **No match → the coding agent writes the test**
   (`rita.firmware.testwriter.write_ztest`): a proper ztest with a
   `testcase.yaml`, validated before acceptance, so it runs under twister
   like everything else.

`filter:` expressions are recorded, not evaluated — twister is the gate that
evaluates them (see DECISIONS-LOG).

## boards.json (`rita sync`, `rita.firmware.boards`)

Generated into `~/.rita/boards.json` by scanning
`zephyr/boards/**/board.yml` + twister platform yamls (`identifier`,
`arch`, `supported:` peripherals), merged with the user's twister hardware
map (`map.yaml`) for connected-port data:

```json
{"generated_at": "...", "workspace": "/path",
 "zephyr_version": "4.1.0",   // from the checkout's zephyr/VERSION — read, never assumed
 "boards": {
  "apollo510_evb": {"name": "apollo510_evb",
    "aliases": ["apollo510", "apollo 510"],
    "vendor": "ambiq", "arch": "arm",
    "twister_platform": "apollo510_evb/apollo510",
    "supported": ["gpio", "uart", "i2c", "led"],
    "connected": {"serial": "/dev/ttyACM0", "runner": "jlink"}}}}
```

Aliases are derived (strip `_evb`/`_dk` suffixes, spaced variants) — they
feed the router's vocabulary (Fix 1), replacing the packaged seed after the
first sync.

## Workspace MCP server (`rita.mcpserver`, `rita mcp-serve`)

RITA hosts a stdio MCP server over the given Zephyr checkout so the
coder-worker queries the workspace's code and intent through tools instead
of groping the filesystem. Tools (all read-only, workspace-rooted,
path-traversal guarded):

| Tool | Purpose |
|---|---|
| `find_verification(board, query, limit)` | ranked index entries for an intent |
| `board_info(name)` / `list_boards(supports)` | board vocabulary + capabilities |
| `sample_lookup(name)` | a sample's path, yaml, and README text |
| `read_workspace_file(path, max_bytes)` | bounded file read inside the workspace |
| `grep_workspace(pattern, glob, max_results)` | bounded regex search |

The `mcp` SDK is an optional extra (`pip install .[mcp]`); the tool
implementations are pure functions tested without it. YAML parsing uses
pyyaml when installed (`.[firmware]`) with a vendored subset parser fallback
so the suite stays zero-required-deps.

## Acceptance criteria (each is a test)

- Known-sample hit: blinky intent on a compatible board resolves to
  `samples/basic/blinky` from the index.
- Board-incompatible sample is excluded (`platform_allow` respected).
- No index match forces test authorship, and the written test's
  `testcase.yaml` must parse and declare a test, or it is rejected.
- Fit judging is a single bounded call and can only select among the
  provided candidates.
- Sync writes `boards.json` + `verification-index.json` into `~/.rita/`,
  and the router's vocabulary picks up synced board names.
- MCP tool implementations refuse paths escaping the workspace root.
