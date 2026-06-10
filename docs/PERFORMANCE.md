# Performance & Hardware

Goal: a **local** assistant that feels instant. The honest headline:

> For a local LLM, **GPU VRAM and memory bandwidth dominate speed — not system
> RAM.** A model is fast only when it fits *entirely* in fast memory and stays
> resident. The thing to "dedicate" is **VRAM** (or Apple **unified memory**),
> and the move is to **keep the model pinned** so it never reloads.

## Where the time goes (optimize in this order)

1. **Keep the model warm in VRAM.** Cold reloads are the #1 latency killer. Use
   a persistent server (Ollama `keep_alive=-1`, or llama.cpp / vLLM running as a
   service) so the model stays resident between steps.
2. **Model routing.** Most agent steps are easy. Use a small fast model (~3–8B)
   for routine steps and only escalate to a big local model — or **Claude** —
   for genuinely hard reasoning. This is the single biggest end-to-end win.
3. **Perceive cheaply.** Read the **accessibility tree first** (instant, no
   model). Run the vision model only when the UI isn't accessible, and
   **downscale** screenshots. Vision-on-every-frame is the second biggest cost.
4. **Quantization.** Q4/Q5 GGUF cuts VRAM ~3–4× with minimal quality loss, so a
   smarter model fits in the same card.
5. **Caching & decoding tricks.** Reuse the system prompt + tool context across
   steps (prompt/KV cache); **speculative decoding** can roughly 2× throughput.
6. **Batch / stream.** Stream tokens so the UI reacts immediately; batch
   embedding/RAG work.

### What does *not* help much
- **System RAM for model speed** — CPU offload is slow; avoid spilling out of
  VRAM. RAM matters for the OS, vector DB, and many tools at once, not inference.
- **RAM disk for the model** — only speeds the *first* load from disk. Once the
  model is resident in VRAM it's irrelevant. Just keep it warm instead.

## Recommended hardware (local)

| Tier | Hardware | Runs locally | Notes |
|---|---|---|---|
| **Sweet spot** | NVIDIA **24 GB VRAM** (RTX 4090 / 3090) + 64 GB RAM + NVMe | 14–32B quantized + a small vision model, fast | Best price/perf, mature CUDA stack |
| **Top tier** | **48 GB+ VRAM** (2×3090, RTX 6000 Ada) | 70B-class local | Closest to frontier quality, fully local |
| **Apple** | M3/M4 **Max/Ultra, 64–128 GB unified** | up to 70B via Metal | "Dedicated RAM" = unified memory; great bandwidth, silent, simplest setup |
| **Entry** | **16 GB VRAM** | 7–14B quantized | Workable; lean harder on Claude escalation for hard tasks |

**Supporting specs:** 32–64 GB system RAM, a fast **NVMe SSD** (model load +
vector store), and on NVIDIA, current CUDA drivers.

### "Dedicated RAM" — what to actually do
- **NVIDIA:** the relevant memory is **VRAM**, already dedicated to the GPU. Pick
  a card whose VRAM holds your model + KV cache + vision model with headroom,
  and keep it resident.
- **Apple Silicon:** there's no separate VRAM — you allocate a large share of
  **unified memory** to the GPU. 64 GB+ lets big models run with strong
  bandwidth. This is the closest thing to "dedicate RAM to the model."

## Local-first with Claude escalation

Stay local by default; escalate to the **Claude API** only when it's worth it:

- **Triggers:** local planner confidence is low, the task is high-stakes, it
  needs a much larger context window, or it stalls/re-plans repeatedly.
- **Privacy:** redact sensitive screen/email content before anything leaves the
  machine, and gate escalation behind your consent / a permission tier.
- **Result:** local = the private, fast default; Claude = on-demand horsepower.

```
step ─▶ small local model ──(easy)──▶ act
             │
          (hard / low confidence / high stakes)
             ▼
     big local model ──(still stuck / needs huge context)──▶ Claude API
```

## Latency budget (targets to design against)

| Stage | Target |
|---|---|
| Screenshot + a11y grounding | < 50 ms (a11y), ~150–400 ms if vision needed |
| Routine planning step (small local model) | < 300 ms to first token |
| Action execution (click/type) | < 50 ms |
| Hard reasoning (big local / Claude) | seconds — used sparingly |

Designing each step to prefer the cheap path keeps the *common* case snappy and
reserves the expensive path for when it actually matters.
