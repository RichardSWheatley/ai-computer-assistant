# Spec: Zephyr knowledge pack + SDK awareness

## Problem

RITA must know **how and where** to build Zephyr applications, samples, and
tests — conventions that indexing the workspace cannot reveal (where apps
live, west flags, twister invocation shapes, ztest structure, devicetree
overlay rules, MSPI/PSRAM specifics, SDK layout). This knowledge is
researched from the official docs (docs.zephyrproject.org), distilled, and
**shipped with RITA** — every topic cites its source URL and research date.

The standing rule is unchanged: the pack carries *conventions and API
knowledge*; every **fact about the user's install** (boards, versions,
samples, SDK path) still comes only from the actual workspace/SDK.

## Design

### The pack (`src/rita/firmware/data/knowledge/`)

One markdown file per topic + `index.json`
(`topic -> {title, keywords, source, summary}`):

| Topic | Covers |
|---|---|
| `building-apps` | app types (workspace/freestanding/repo), required files, CMakeLists shape, `find_package(Zephyr)` |
| `app-locations` | where apps live: `<workspace>/applications/<app>` convention; RITA's `applications_dir` |
| `west-commands` | `west build -b <board> -d <dir> -p`, `-t run`, board qualifiers, `west config` |
| `twister` | `west twister -T -p -s`, `--device-testing --hardware-map`, outputs (`twister.json`), harnesses |
| `ztest` | `ZTEST_SUITE`/`ZTEST`, zassert macros, `CONFIG_ZTEST=y`, testcase.yaml registration |
| `devicetree-overlays` | overlay discovery order (`boards/<BOARD>.overlay`, `app.overlay`, `EXTRA_DTC_OVERLAY_FILE`), patterns |
| `mspi` | the multi-bit SPI API: io modes single→hex SDR/DDR, `mspi_*` functions, DT properties, in-tree samples |
| `psram` | PSRAM over MSPI: `memc` drivers (e.g. `memc_mspi_aps6404l`), XIP, `ambiq,mspi-device` binding |
| `flash-and-debug` | `west flash --runner`, runners (jlink…), hardware maps |
| `sdk` | install locations, `ZEPHYR_SDK_INSTALL_DIR`, bundle variants, `sdk_version` |

### Retrieval (`rita.firmware.knowledge`) — deterministic, no LLM

- `list_topics()`, `get_topic(name) -> str`
- `match_topics(terms, limit=3)` — keyword overlap against the index
- `notes_for(terms, max_chars)` — bounded knowledge block for prompt
  enrichment

### Consumers

1. **MCP tools** `zephyr_howto(topic)` and `list_topics()` — the
   claude-worker's source for conventions (alongside the workspace tools).
2. **Prompt enrichment**: the pipeline appends matched topic notes to the
   scaffold goal and the test-writer goal (patching already carries a
   concrete failure artifact).
3. **Chat**: "how do I…" questions matching a topic get the topic summary
   (deterministic keyword match).

### Where applications are built

`RitaConfig.applications_dir` (default `<workspace>/applications`).
Scaffolded apps go to `<applications_dir>/<slug-of-goal>/`; the pipeline
builds from there. Never inside `zephyr/` itself.

### Routing (the flagship utterance)

"Rita, please build me an example for MSPI that communicates with a PSRAM
on MSPI0 in hex mode":

- `mspi`, `psram` join the peripheral vocabulary; `example`, `sample`,
  `test` join the artifact tokens.
- Deterministic upgrade rule: verb `build` + an artifact token + **no
  named existing sample** → `scaffold` (the user is asking for a new
  application, not a build of something that exists).

### SDK facts — from the actual install

`read_sdk_info()`: `ZEPHYR_SDK_INSTALL_DIR` first, else standard install
locations (`~/zephyr-sdk-*`, `/opt/zephyr-sdk-*`, `%PROGRAMFILES%`);
version from the SDK's `sdk_version` file, else the directory name.
Surfaced in `read_workspace_info`, boards.json, the `workspace_info` MCP
tool, and the GUI status bar. Missing SDK is reported as missing.

## Acceptance criteria (each is a test)

- Index integrity: every topic file exists, is non-empty, cites a
  `docs.zephyrproject.org` source; every file is in the index.
- `match_topics(["mspi","psram"])` returns the mspi + psram topics;
  `notes_for` output is bounded and contains their content.
- MCP `zephyr_howto("twister")` returns the twister topic text.
- The flagship MSPI/PSRAM utterance routes to
  `(work, scaffold, peripheral=mspi)`.
- A scaffold pipeline run creates the app under `applications_dir` and
  the scaffold prompt carries the matched knowledge notes.
- SDK detection: env var wins; `sdk_version` file read; absent SDK →
  `None`, never guessed.
- Chat: "how do I add a devicetree overlay" answers with the topic
  summary.
