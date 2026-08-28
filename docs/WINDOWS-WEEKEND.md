# Weekend Quickstart — Windows, no GPU

You don't need a GPU. With no VRAM, the assistant uses **the cloud model in the cloud** as
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
python -m rita doctor
```

(No GPU → it reports `acceleration: cpu`, `default mode: auto`, and that it will
lean on the cloud model. That's expected.)

---

## Track A — Document generator (guaranteed, ~5 min, no API key)

Generates real PowerPoint / Word / Excel files. No GPU, no key, no permissions.

```powershell
pip install -e ".[business]"

python -m rita doc deck   examples\deck.json   -o demo.pptx
python -m rita doc report examples\report.json -o demo.docx
python -m rita doc sheet  examples\sheet.json  -o demo.xlsx
```

Open `demo.pptx` / `demo.docx` / `demo.xlsx` in Office. Edit the JSON in
`examples\` (titles, bullets, chart numbers) and re-run — that's your generator.

---

## Track B — the cloud model-powered computer-use (the real assistant)

The assistant sees the screen and drives your apps, with the cloud model as the brain.

### 1. Install + set your key

```powershell
pip install -e ".[cloud,control,windows]"
$env:<YOUR_LLM_API_KEY> = "..."   # from your model vendor's console
```

### 2. Dry-run first (safe — nothing moves)

```powershell
python -m rita run "open Notepad and type a hello note"
```

This runs the full perceive→plan→act loop in **simulation** (actions are logged,
not performed) so you can watch what it *would* do without risk.

### 3. Go live (it actually drives the mouse/keyboard)

```powershell
python -m rita run "open Notepad and type a hello note" --live --confirm
```

- `--live` performs real input. `--confirm` prompts you before any
  outward/destructive action.
- **Kill switch:** slam the mouse into a screen corner (pyautogui failsafe), or
  press the global hotkey, to halt instantly.
- Start with tiny, reversible goals (Notepad, Calculator) and grow from there.
  Reading the screen via UI Automation may need a little tuning per app — see
  `docs/SECURITY.md` and `docs/PERFORMANCE.md`.

---

## Track C — Talk to it (voice in + voice out)

Speak commands; the assistant runs them and speaks back. Listening is local
(Whisper, CPU — no GPU); speaking is offline (Windows SAPI via pyttsx3).

```powershell
pip install -e ".[voice]"
python -m rita talk --push-to-talk                    # press Enter to talk (recommended)
python -m rita talk --push-to-talk --live --confirm   # actually drives the screen
python -m rita talk                                    # continuous: ~5s turns, no button
```

- **Push-to-talk** (`--push-to-talk`): press **Enter** to start a turn, speak,
  press **Enter again to stop**. No fixed time limit, no accidental triggers.
  Type `q` at the prompt to quit.
- **Continuous** (default): records ~5 seconds per turn (`--seconds N` to change).
- Either way it transcribes, runs the task, and speaks a summary.
- Say **"stop listening"** (or Ctrl+C) to end.
- First run downloads the Whisper model (`--model tiny` is fastest; `base` is the
  default; `small` is more accurate). `sounddevice` needs a working mic.

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
`rita doctor` for the recommendation), and the assistant **automatically** makes
the local model the default — the cloud model becomes the fallback. No code changes.
