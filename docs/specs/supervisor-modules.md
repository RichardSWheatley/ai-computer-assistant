# Spec: Supervisor + versioned module processes (Fix 6)

## Shape

The installed deliverable is a **thin supervisor**: UI/voice shell, router
(Fix 1), task manager (Fix 4), PAUSE/STOP, and the module registry. Every
capability is a **module** — a separately versioned, self-contained process
under `~/.rita/modules/<name>/<version>/`.

## Manifest (`manifest.toml`, language-agnostic)

```toml
name = "zephyr-runner"
version = "1.0.0"
entrypoint = ["python", "-m", "rita.modules_impl.zephyr_runner"]  # any argv
capabilities = ["build", "twister", "flash"]
max_instances = 4
min_supervisor = "0.7.0"

[exclusivity]
keys = ["serial_port"]     # per-instance exclusive resource claims
```

`<name>/current` is a plain text file holding the active version (portable
where symlinks aren't). The manifest declares the entrypoint, not the
runtime — a Rust module ships a binary path.

## IPC: JSON-RPC over stdio (port-free, firewall-silent)

One JSON object per line, same wire shape as the existing worker protocol:
requests `{"id", "method", "params"}`, responses
`{"id", "ok", "result", "error"}`, plus **async events** (no `id`):
`{"event": "progress"|"checkpoint"|"log", "data": …}`. A dedicated reader
thread per handle demultiplexes responses from events, so a module can
stream progress while a call is in flight.

Protocol methods every module serves: `hello` (handshake), `start`,
`status`, `pause_at_checkpoint`, `resume`, `stop`, `result`, `shutdown`.

- **Handshake enforced at launch**: the supervisor sends `hello` with its
  version and protocol; the module echoes name/version/protocol. A protocol
  mismatch, a `min_supervisor` newer than the supervisor, or a handshake
  timeout is a launch error — the module never joins the registry.
- **Per-call timeouts are honored** (a hung call raises; it is not waited
  on forever).

## Registry rules

- **Updates**: drop a new version directory, flip `current`. Running
  instances drain on the old version (they keep the code they started
  with); new spawns read `current` fresh. Rollback = flip back.
- **Multiple instances** up to `max_instances`. Exclusivity keys make
  resource claims exclusive across live instances: one zephyr-runner per
  board serial port, one joulescope total (`max_instances = 1`),
  coder-worker per task up to its cap.
- **Crash isolation**: a dead or hung module is killed and surfaced as a
  failed call; the owning task goes FAILED with the module's stderr tail;
  the supervisor stays up and the registry accepts the next launch.
- Modules spawn under the existing `SandboxPolicy` env scrub.

## Modules shipped

voice-in, voice-out, zephyr-runner, coder-worker, scaffold — thin wrappers
over the Fix 2/3/4 seams. cerberus and joulescope are **honest stubs**:
valid manifests whose `start` reports "external tool/hardware not present"
(never fake capability). `rita modules install --dev` writes the manifests
+ `current` pointers for the installed package; `rita modules` lists state.

Install story: the supervisor ships via PyInstaller/Nuitka + a platform
installer; models and config live under `~/.rita/`. Laptop access beyond
the workspace stays an explicit enumerated permission layer
(`docs/ACCESS.md`) — nothing implicit.

## Acceptance criteria (each is a test)

- Manifest parse/validate; `min_supervisor` newer than the supervisor is
  rejected at launch.
- Update while running: a task in flight completes on the old version;
  the next launch uses the new one (`current` flip + drain).
- Two runner instances launch concurrently with different port claims; a
  duplicate claim or an over-cap launch is refused.
- Handshake failure (wrong protocol / bad echo / timeout) is a launch
  error.
- A killed module surfaces as a failed call with stderr captured, and the
  supervisor keeps working.
- `pause_at_checkpoint` round-trips through a real child process, and
  events stream independently of request/response traffic.
