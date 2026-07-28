"""RITA home directory (~/.rita) and persisted RitaConfig."""

from __future__ import annotations

from pathlib import Path

import pytest

from aica import home
from aica.config import RitaConfig, load_rita_config, save_rita_config


@pytest.fixture()
def rita_home(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "ritahome"
    monkeypatch.setenv("RITA_HOME", str(root))
    return root


class TestRitaHome:
    def test_env_override(self, rita_home):
        assert home.rita_home() == rita_home
        assert rita_home.is_dir()  # created on demand

    def test_defaults_to_dot_rita_under_home(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RITA_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
        assert home.rita_home() == tmp_path / ".rita"

    def test_path_constants(self, rita_home):
        assert home.boards_json_path() == rita_home / "boards.json"
        assert home.verification_index_path() == rita_home / "verification-index.json"
        assert home.config_path() == rita_home / "config"
        assert home.modules_dir() == rita_home / "modules"
        assert home.audio_dir() == rita_home / "audio"
        assert home.screens_dir() == rita_home / "screens"
        assert home.sandbox_dir() == rita_home / "sandbox"


class TestLegacyMigration:
    def test_migrates_aica_contents(self, tmp_path, monkeypatch):
        legacy = tmp_path / ".aica"
        (legacy / "audio").mkdir(parents=True)
        (legacy / "boards.json").write_text('{"boards": {}}')
        (legacy / "audio" / "utterance.wav").write_bytes(b"RIFF")
        new = tmp_path / ".rita"
        monkeypatch.setenv("RITA_HOME", str(new))

        assert home.migrate_legacy_home(legacy_root=legacy) is True
        assert (new / "boards.json").read_text() == '{"boards": {}}'
        assert (new / "audio" / "utterance.wav").read_bytes() == b"RIFF"

    def test_no_legacy_dir_is_a_noop(self, rita_home, tmp_path):
        assert home.migrate_legacy_home(legacy_root=tmp_path / "missing") is False

    def test_existing_rita_home_is_not_overwritten(self, tmp_path, monkeypatch):
        legacy = tmp_path / ".aica"
        legacy.mkdir()
        (legacy / "boards.json").write_text("old")
        new = tmp_path / ".rita"
        new.mkdir()
        (new / "boards.json").write_text("new")
        monkeypatch.setenv("RITA_HOME", str(new))

        assert home.migrate_legacy_home(legacy_root=legacy) is False
        assert (new / "boards.json").read_text() == "new"


class TestRitaConfig:
    def test_defaults(self):
        cfg = RitaConfig()
        assert cfg.assistant_name == "Rita"
        assert cfg.workspace is None
        assert cfg.hardware_map is None
        assert cfg.max_patch_cycles == 3
        assert cfg.device_tier_enabled is False

    def test_round_trip(self, rita_home):
        cfg = RitaConfig(assistant_name="Vera", workspace="/opt/zephyrproject",
                         hardware_map="/opt/map.yaml", max_patch_cycles=5)
        save_rita_config(cfg)
        loaded = load_rita_config()
        assert loaded == cfg

    def test_load_without_file_gives_defaults(self, rita_home):
        assert load_rita_config() == RitaConfig()

    def test_rename_persists_across_restart(self, rita_home):
        # Simulates the voice-rename flow: change name, save, then a fresh
        # process (fresh load) still sees the new name.
        cfg = load_rita_config()
        cfg.assistant_name = "Iris"
        save_rita_config(cfg)
        assert load_rita_config().assistant_name == "Iris"
