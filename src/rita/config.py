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
    use_cloud: bool = True
    # Operating mode: "auto" (hardware-driven: local LLM when VRAM exists, Claude
    # when none) or "local-only" (nothing leaves the machine). Default is auto.
    mode: str = "auto"
    small_model: str = "llama3.2:3b"
    large_model: str | None = None
    cloud_model: str = "claude-opus-4-8"
    acceleration: str = "cpu"
    plugins_dir: str = "plugins"
    max_steps: int = 20
    dry_run: bool = True
    # Polyglot boundary: when True, the eyes/hands run in a separate worker
    # process. `worker_command` defaults to the Python reference worker; point
    # it at a compiled Rust binary in production. Same protocol either way.
    use_native_worker: bool = False
    worker_command: list[str] | None = None
    # Tamper-evident audit log path; None keeps the log in-memory only.
    audit_path: str | None = None
    # Route untrusted free-text through a no-tools quarantined LLM before the
    # privileged planner sees it. Needs a local model; off by default.
    use_quarantine_llm: bool = False


@dataclass
class RitaConfig:
    """Persisted assistant settings at ~/.rita/config (TOML).

    Separate from the hardware-derived `Config`: these are the user's durable
    choices — the assistant's spoken name (data, not code), the Zephyr
    workspace it operates on, and the iterate-loop budgets.
    """

    assistant_name: str = "Rita"
    workspace: str | None = None       # Zephyr workspace root on this machine
    hardware_map: str | None = None    # twister map.yaml (device tier)
    applications_dir: str | None = None  # scaffold target; default <workspace>/applications
    # CERBERUS static-check gate: explicit command override (target dir is
    # appended). Unset -> the acquired ~/.rita/cerberus clone is used when
    # present; otherwise the STATIC stage reports skipped.
    cerberus_command: str | None = None
    # Deep mode: `analyze` (Oracle LLM + Unity heads) instead of the
    # deterministic keyless `scan`. Claude's seat inside CERBERUS.
    cerberus_deep: bool = False
    max_patch_cycles: int = 3
    # Device tier stays off until the bench milestone proves flash/serial/harness.
    device_tier_enabled: bool = False


def load_rita_config(path: str | Path | None = None) -> RitaConfig:
    from .home import config_path

    p = Path(path) if path else config_path()
    cfg = RitaConfig()
    if p.exists():
        data = tomllib.loads(p.read_text())
        for k, v in data.get("rita", data).items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
    return cfg


def save_rita_config(cfg: RitaConfig, path: str | Path | None = None) -> None:
    from .home import config_path

    p = Path(path) if path else config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[rita]"]
    for k, v in vars(cfg).items():
        if v is None:
            continue
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
        else:
            lines.append(f'{k} = "{v}"')
    p.write_text("\n".join(lines) + "\n")


def load_config(path: str | Path | None = None,
                hw: Hardware | None = None,
                local_only: bool | None = None) -> Config:
    import os

    hw = hw or detect_hardware()
    cfg = Config(acceleration=hw.acceleration)

    # Hardware-derived local model selection (enable GPU model only IF VRAM exists).
    if hw.has_vram:
        cfg.use_local_llm = True
        if hw.total_vram_mb >= 24_000:
            cfg.small_model, cfg.large_model = "llama3.1:8b", "qwen2.5:32b"
        elif hw.total_vram_mb >= 12_000:
            cfg.small_model, cfg.large_model = "llama3.1:8b", "qwen2.5:14b"
        else:
            cfg.small_model, cfg.large_model = "llama3.2:3b", "llama3.1:8b"
    else:
        cfg.use_local_llm = True   # tiny CPU model

    # Mode: default is cloud-default (heavy lifting -> Claude). local-only can be
    # forced via arg, env (RITA_LOCAL_ONLY=1; legacy AICA_LOCAL_ONLY honored),
    # or the config file.
    if local_only is None:
        raw = os.environ.get("RITA_LOCAL_ONLY",
                             os.environ.get("AICA_LOCAL_ONLY", ""))
        local_only = raw.lower() in ("1", "true", "yes")
    if local_only:
        cfg.mode = "local-only"

    # File overrides (optional) — may set mode too.
    if path and Path(path).exists():
        data = tomllib.loads(Path(path).read_text())
        for k, v in data.get("rita", data.get("aica", data)).items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)

    # Enforce: local-only mode means cloud is off, full stop.
    if cfg.mode == "local-only":
        cfg.use_cloud = False
    return cfg
