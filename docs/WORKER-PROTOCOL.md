# Worker Protocol (v1.0)

The contract between the **Python brain** and a **native worker** (Rust in
production, a Python reference worker today). Any worker that speaks this
protocol is a drop-in — that's how we mix languages without coupling them.

## Transport

- **Newline-delimited JSON** over the worker's **stdin/stdout** (one message per
  line). Simple, debuggable, and language-agnostic.
- Production can upgrade the same message shapes to a Unix domain socket / named
  pipe; bulk data (screen frames) is passed by **file or shared-memory path**,
  never inlined in JSON.

## Messages

Request:
```json
{"id": 1, "method": "capture", "params": {}}
```
Response:
```json
{"id": 1, "ok": true, "result": { ... }, "error": null}
```
`id` correlates request/response. On failure: `"ok": false, "error": "..."`.

## Methods

| Method | Params | Result |
|---|---|---|
| `ping` | — | `{version, impl}` |
| `capture` | — | `{summary, screenshot_path, elements[]}` |
| `click` | `{x, y, button}` | `{detail}` |
| `type_text` | `{text}` | `{detail}` |
| `hotkey` | `{keys: [str]}` | `{detail}` |
| `kill` | — | `{detail}` (engage kill switch) |
| `shutdown` | — | `{detail}` then exit |

`elements[]` items: `{label, role, x, y, source}` where `source` is
`a11y | vision | ocr`.

## Versioning

`PROTOCOL_VERSION` lives in `src/rita/workers/protocol.py` — the single source of
truth. Bump it on breaking changes; the client checks it via `ping`.

## Swapping in the Rust worker

```python
# Today (default): bundled Python reference worker
WorkerClient()

# Production: a compiled Rust binary speaking the same protocol
WorkerClient(["/usr/local/bin/rita-worker"])
```
Or set `worker_command` in config. Nothing else changes.

## Why this shape

- **stdio + JSON lines** means a Rust worker needs only stdin/stdout and a JSON
  lib — no gRPC/codegen toolchain to start.
- **Paths, not inlined frames** keeps the hot capture path off the JSON channel,
  so high-FPS screen data uses shared memory while control stays simple.
