# Quickstart

The Phase 0 + 1 MVP runs **headless with zero heavy dependencies** (mock
providers), so you can try the agent loop immediately, then enable real
GPU/perception/control on your Windows or Mac.

## 1. Install (core only — no GPU needed)

```bash
pip install -e .
```

## 2. Check what your machine offers

```bash
aica doctor
```

Shows detected GPUs/VRAM, the chosen acceleration backend (CUDA / Metal / CPU),
the per-OS perception + input backends, and a model recommendation.
**If VRAM exists, it enables the local GPU model; if not, it falls back to a
tiny CPU model + Claude escalation.**

## 3. List tools and run the loop (mock-safe)

```bash
aica plugins                       # built-in + discovered plugin tools
aica run "type hello into notepad" # runs perceive->plan->act->verify
```

## 4. Add a feature — drop in a plugin

Copy `plugins/hello/` to `plugins/<your-feature>/`, edit `plugin.toml` and
`plugin.py`, restart. Its tools appear automatically — no core changes.

## 5. Enable real capabilities (per machine)

| Want | Install | Notes |
|---|---|---|
| Local model (GPU) | `pip install -e ".[local-llm,gpu]"` + [Ollama](https://ollama.com) | Pull a model sized to your VRAM (see `aica doctor`) |
| Claude escalation | `pip install -e ".[cloud]"` + `ANTHROPIC_API_KEY` | Hard / high-stakes steps only |
| Screen capture | `pip install -e ".[perception]"` | `mss` + OCR |
| Mouse/keyboard control | `pip install -e ".[control]"` | Real simulated input |
| Windows a11y | `pip install -e ".[windows]"` | UI Automation |
| Business (Outlook/Teams/PPTX) | `pip install -e ".[business]"` | see below |

### Business plugins (opt-in)

The `outlook`, `teams`, and `powerpoint` plugins live in `plugins/` but ship
**disabled** (`enabled = false`) because they need extra deps / accounts. To turn
one on, set `enabled = true` in its `plugin.toml`:

| Plugin | Needs | Notes |
|---|---|---|
| `powerpoint` | `python-pptx` | Generates real `.pptx` decks (charts, big-number, sections) |
| `outlook` | `msal` + a signed-in account (`AICA_GRAPH_*` env) | Drafting is gated; **sending is confirmation-gated** |
| `teams` | `msal` + a signed-in account | Posting is confirmation-gated |

Outlook/Teams use the **Microsoft Graph API** (delegated OAuth, least-privilege
scopes), not UI scraping. Outward-facing actions (send mail, post to Teams) are
the `outward_facing` permission tier — the orchestrator asks before doing them.

> **macOS:** grant **Accessibility** + **Screen Recording** permissions in
> System Settings → Privacy & Security before perception/control will work.
> **Windows:** an NVIDIA GPU enables CUDA automatically.

## 6. Run the tests

```bash
pip install -e ".[dev]"
pytest -q
```

## Safety defaults

- `dry_run=True` until you wire real input — actions are simulated/logged.
- Outward-facing/destructive tools are gated by a confirmation callback.
- Kill switch: `Ctrl+Alt+Esc` (when a desktop hotkey backend is available), or
  slam the mouse into a screen corner (pyautogui failsafe).
