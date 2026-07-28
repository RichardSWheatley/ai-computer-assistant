"""Hardware detection — the 'IF VRAM exists, use the GPU' logic.

Detection order (best-effort, no hard dependencies):
  1. NVIDIA   -> `nvidia-smi` (parse VRAM per GPU)
  2. PyTorch  -> torch.cuda / torch.backends.mps (if torch is installed)
  3. Apple    -> platform check for Apple Silicon (Metal / unified memory)
  4. Fallback -> CPU only

The result drives acceleration backend selection and a model recommendation,
so the assistant runs GPU-accelerated when VRAM exists and degrades gracefully
to CPU + heavier Claude escalation when it doesn't.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class GPU:
    name: str
    vram_mb: int
    backend: str  # "cuda" | "metal"


@dataclass
class Hardware:
    gpus: list[GPU] = field(default_factory=list)
    system_ram_mb: int = 0
    platform: str = field(default_factory=lambda: platform.system())

    @property
    def has_vram(self) -> bool:
        return any(g.vram_mb > 0 for g in self.gpus)

    @property
    def total_vram_mb(self) -> int:
        return sum(g.vram_mb for g in self.gpus)

    @property
    def acceleration(self) -> str:
        """Backend the model server should use."""
        if not self.gpus:
            return "cpu"
        # Prefer CUDA if any NVIDIA GPU is present, else Metal.
        if any(g.backend == "cuda" for g in self.gpus):
            return "cuda"
        if any(g.backend == "metal" for g in self.gpus):
            return "metal"
        return "cpu"


def _detect_nvidia() -> list[GPU]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    gpus: list[GPU] = []
    for line in out.stdout.strip().splitlines():
        if not line.strip():
            continue
        name, _, mem = line.partition(",")
        try:
            vram = int(float(mem.strip()))
        except ValueError:
            vram = 0
        gpus.append(GPU(name=name.strip(), vram_mb=vram, backend="cuda"))
    return gpus


def _detect_torch() -> list[GPU]:
    try:
        import torch  # type: ignore
    except Exception:
        return []
    gpus: list[GPU] = []
    try:
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                gpus.append(GPU(
                    name=props.name,
                    vram_mb=int(props.total_memory // (1024 * 1024)),
                    backend="cuda",
                ))
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            # Apple unified memory ≈ usable as VRAM; report system RAM as proxy.
            gpus.append(GPU(name="Apple Metal (unified)",
                            vram_mb=_system_ram_mb(), backend="metal"))
    except Exception:
        return gpus
    return gpus


def _detect_apple() -> list[GPU]:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return [GPU(name="Apple Silicon (unified)",
                    vram_mb=_system_ram_mb(), backend="metal")]
    return []


def _system_ram_mb() -> int:
    try:
        import os
        if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
            return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") // (1024 * 1024))
    except Exception:
        pass
    return 0


def detect_hardware() -> Hardware:
    gpus = _detect_nvidia()
    if not gpus:
        gpus = _detect_torch()
    if not gpus:
        gpus = _detect_apple()
    return Hardware(gpus=gpus, system_ram_mb=_system_ram_mb())


def recommend_model(hw: Hardware) -> dict:
    """Pick a sensible local model tier from available VRAM.

    Returns a dict describing the recommended local model and whether to lean
    on Claude escalation. Quantized (Q4/Q5) sizes assumed.
    """
    vram = hw.total_vram_mb
    if vram == 0:
        return {
            "tier": "cpu/cloud",
            "local_model": "llama3.2:3b (CPU, slow)",
            "note": "No VRAM detected — run a tiny local model and escalate hard "
                    "tasks to Claude. A GPU is strongly recommended.",
            "lean_on_claude": True,
        }
    if vram < 12_000:
        return {"tier": "entry", "local_model": "~7-8B Q4",
                "note": "Lean on Claude for hard reasoning.", "lean_on_claude": True}
    if vram < 24_000:
        return {"tier": "midrange", "local_model": "~14B Q4/Q5",
                "note": "Comfortable local agent; Claude for the hardest tasks.",
                "lean_on_claude": False}
    if vram < 48_000:
        return {"tier": "sweet-spot", "local_model": "~32B Q4 + small vision model",
                "note": "Fast local agent across most tasks.", "lean_on_claude": False}
    return {"tier": "top", "local_model": "~70B-class",
            "note": "Near-frontier quality fully local.", "lean_on_claude": False}
