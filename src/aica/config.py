"""Configuration, derived from a TOML file + detected hardware.

Hardware drives defaults: if VRAM exists we enable the local GPU model and pick
a size to match; otherwise we fall back to a tiny CPU model and lean on Claude.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .hardware import Hardware, detect_hardware, recommend_model


@dataclass
class Config:
    use_local_llm: bool = False
    use_cloud: bool = False
    small_model: str = "llama3.2:3b"
    large_model: str | None = None
    cloud_model: str = "claude-opus-4-8"
    acceleration: str = "cpu"
    plugins_dir: str = "plugins"
    max_steps: int = 20
    dry_run: bool = True


def load_config(path: str | Path | None = None,
                hw: Hardware | None = None) -> Config:
    hw = hw or detect_hardware()
    cfg = Config(acceleration=hw.acceleration)

    # Hardware-derived defaults: enable the GPU model only IF VRAM exists.
    rec = recommend_model(hw)
    if hw.has_vram:
        cfg.use_local_llm = True
        cfg.use_cloud = rec["lean_on_claude"]
        if hw.total_vram_mb >= 24_000:
            cfg.small_model, cfg.large_model = "llama3.1:8b", "qwen2.5:32b"
        elif hw.total_vram_mb >= 12_000:
            cfg.small_model, cfg.large_model = "llama3.1:8b", "qwen2.5:14b"
        else:
            cfg.small_model, cfg.large_model = "llama3.2:3b", "llama3.1:8b"
    else:
        cfg.use_local_llm = True   # tiny CPU model
        cfg.use_cloud = True       # lean on Claude for hard tasks

    # File overrides (optional).
    if path and Path(path).exists():
        data = tomllib.loads(Path(path).read_text())
        for k, v in data.get("aica", data).items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
    return cfg
