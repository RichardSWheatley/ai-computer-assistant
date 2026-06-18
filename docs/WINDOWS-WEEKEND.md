# Weekend Quickstart — Windows, no GPU

You don't need a GPU. With no VRAM, the assistant uses **Claude in the cloud** as
its brain and runs everything else on your PC. Two tracks below: a 5-minute
guaranteed win, then the real computer-use assistant.

## 0. One-time setup

Install Python 3.11+ (tick "Add to PATH"), then in PowerShell from the repo:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

Check what the assistant detects on your machine:

```powershell
python -m aica doctor
```

(No GPU → it reports `acceleration: cpu`, `default mode: auto`, and that it will
lean on Claude. That's expected.)

---

## Track A — Document generator (guaranteed, ~5 min, no API key)

Generates real PowerPoint / Word / Excel files. No GPU, no key, no permissions.

```powershell
pip install -e ".[business]"

python -m aica doc deck   examples\deck.json   -o demo.pptx
python -m aica doc report examples\report.json -o demo.docx
python -m aica doc sheet  examples\sheet.json  -o demo.xlsx
```

Open `demo.pptx` / `demo.docx` / `demo.xlsx` in Office. Edit the JSON in
`examples\` (titles, bullets, chart numbers) and re-run — that's your generator.

---

## Track B — Claude-powered computer-use (the real assistant)

The assistant sees the screen and drives your apps, with Claude as the brain.

### 1. Install + set your key

```powershell
pip install -e ".[cloud,control,windows]"
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # from console.anthropic.com
```

### 2. Dry-run first (safe — nothing moves)

```powershell
python -m aica run "open Notepad and type a hello note"
```

This runs the full perceive→plan→act loop in **simulation** (actions are logged,
not performed) so you can watch what it *would* do without risk.

### 3. Go live (it actually drives the mouse/keyboard)

```powershell
python -m aica run "open Notepad and type a hello note" --live --confirm
```

- `--live` performs real input. `--confirm` prompts you before any
  outward/destructive action.
- **Kill switch:** slam the mouse into a screen corner (pyautogui failsafe), or
  press the global hotkey, to halt instantly.
- Start with tiny, reversible goals (Notepad, Calculator) and grow from there.
  Reading the screen via UI Automation may need a little tuning per app — see
  `docs/SECURITY.md` and `docs/PERFORMANCE.md`.

### 4. (Optional) Business apps — Outlook / Teams

These are opt-in. Put your token in the vault (never in a prompt), then enable
the plugin:

```powershell
# store a secret in the OS keychain (Windows Credential Manager)
pip install -e ".[secrets]"
# then set plugins\outlook\plugin.toml -> enabled = true
```

Sending mail / posting to Teams is **confirmation-gated** — the assistant always
asks first.

---

## Safety defaults (already on)

- **Simulation by default** — real input only with `--live`.
- **Secure-by-default gate** — outward/destructive actions are blocked unless you
  pass `--confirm` and approve them.
- **Prompt-injection defense** — on-screen/email/web text is treated as untrusted
  data, scanned, and quarantined (see `docs/SECURITY.md`).
- **Local-only option** — `--local-only` cuts all cloud/network (needs a local
  model to be useful, so it's for later when you get a GPU).

## When you get a GPU later

Install [Ollama](https://ollama.com), pull a model sized to your VRAM (run
`aica doctor` for the recommendation), and the assistant **automatically** makes
the local model the default — Claude becomes the fallback. No code changes.
