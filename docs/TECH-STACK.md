# Tech Stack

Concrete, opinionated library choices. **First pass targets Windows + macOS**
(the two desktops where this gets daily use). Linux is best-effort later.

| Concern | Windows | macOS |
|---|---|---|
| GPU acceleration | **CUDA** (NVIDIA) | **Metal** (Apple Silicon unified memory) |
| Accessibility tree | UI Automation (`pywinauto`, `uiautomation`) | Accessibility API / `AXUIElement` (`pyobjc`) |
| Simulated input | `pyautogui` + `pydirectinput` | `pyautogui` + Quartz |
| Permissions | input access | grant **Accessibility + Screen Recording** in System Settings → Privacy |

`rita/platform_support.py` selects these per-OS so the rest of the code is
platform-agnostic. Run `rita doctor` to see what's detected on each machine.

## Language

- **Python 3.11+** — best ecosystem for AI, automation, and Office generation.
  (A Tauri/Electron or .NET shell can wrap the UI later if desired.)

## Reasoning / LLM

| Need | Choice |
|---|---|
| Local model runtime | **Ollama** or **llama.cpp** (privacy, offline) |
| Local multimodal (vision) | A local vision-language model for screen grounding |
| Cloud (optional, hard reasoning) | A frontier model (e.g. the cloud model) with a **computer-use** tool API |
| Agent framework | Lightweight custom loop, or LangGraph / a small agent lib |
| Model routing | Cheap/fast local for routine steps → cloud for hard ones |

## Perception (seeing the screen)

| Need | Choice |
|---|---|
| Screenshots | `mss` (fast cross-platform capture) |
| Accessibility tree (Windows) | **UI Automation** via `pywinauto` / `uiautomation` |
| OCR | `RapidOCR` / `Tesseract` (text in canvases/images) |
| Element grounding | Fuse a11y + vision + OCR into one target list |

## Action (controlling the computer)

| Need | Choice |
|---|---|
| Mouse & keyboard | `pyautogui` (+ `pydirectinput` for games/low-level) |
| Window/app control | `pywinauto` (Windows), `pygetwindow` |
| Clipboard | `pyperclip` |
| Kill switch | Global hotkey listener (`keyboard` / `pynput`) |

## Business / Microsoft 365

| Need | Choice |
|---|---|
| Teams, Outlook, Calendar, OneDrive | **Microsoft Graph API** (`msgraph-sdk` + `msal` auth) |
| PowerPoint | **`python-pptx`** |
| Word | `python-docx` |
| Excel | `openpyxl` (local) / Graph (cloud files) |
| Charts/diagrams | `matplotlib` / `plotly` (render), native PPTX charts |
| AI imagery | An image-generation model (local or API) for hero art/backgrounds |

## Developer toolkit

- Sandboxed shell, `git` (via `subprocess` or `GitPython`), test runners.
- Codebase RAG: embeddings + a vector DB (**Chroma** / `faiss` / `sqlite-vec`).
- IDE control: VS Code CLI + extension, terminal automation.

## Memory / RAG

- Vector store: **Chroma** (simple, local) or `sqlite-vec`.
- Embeddings: a local embedding model for privacy.

## UI / control surface

- Overlay HUD + chat: a desktop UI (PySide/Qt, or a Tauri/Electron front-end).
- Voice (optional): local STT (**Whisper**) + TTS.

## Security

- Secrets: OS keychain (`keyring`).
- Sandboxing: contained workspace dir, shell allow-list.
- Audit log: append-only JSONL of observations + actions.

## Note on "computer use"

Several frontier model providers now expose a **computer-use** capability — the
model is given screenshots and emits click/type actions directly. This project
can use that as the cloud path for #3/#4, while keeping the local
vision+a11y+action stack as the private default. Best of both: use the API when
you want max capability, run fully local when you want privacy.
