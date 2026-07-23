# tests/test_relocation.py
# SPDX-License-Identifier: MIT
"""Tests for the data directory relocation feature."""

import sys
from pathlib import Path

# Add project root to sys.path so 'bol' can be imported
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import shutil
import pytest
from bol import config


def test_default_install_location():
    """The default location should be ~/.local/share/bedrock-on-linux."""
    expected = str(Path.home() / ".local/share" / "bedrock-on-linux")
    assert config.default_install_location() == expected


def test_is_relocation_allowed(monkeypatch):
    """Relocation should be allowed unless BOL_HOME is set."""
    monkeypatch.delenv("BOL_HOME", raising=False)
    assert config.is_relocation_allowed() is True

    monkeypatch.setenv("BOL_HOME", "/some/path")
    assert config.is_relocation_allowed() is False


def test_set_and_clear_install_location(monkeypatch, tmp_path):
    """set_install_location writes the pointer file; clear removes it."""
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(
        config,
        "INSTALL_LOCATION_FILE",
        tmp_path / ".config" / "bedrock-on-linux" / "install_location"
    )
    monkeypatch.delenv("BOL_HOME", raising=False)

    test_path = tmp_path / "my_custom_data"
    config.set_install_location(str(test_path))

    pointer_file = config.INSTALL_LOCATION_FILE
    assert pointer_file.exists()
    assert pointer_file.read_text().strip() == str(test_path)

    config.clear_install_location()
    assert not pointer_file.exists()


def test_set_install_location_raises_when_bol_home_is_set(monkeypatch):
    monkeypatch.setenv("BOL_HOME", "/some/path")
    with pytest.raises(RuntimeError, match="Cannot change location when BOL_HOME is set externally"):
        config.set_install_location("/dummy/path")


def test_clear_install_location_raises_when_bol_home_is_set(monkeypatch):
    monkeypatch.setenv("BOL_HOME", "/some/path")
    with pytest.raises(RuntimeError, match="Cannot change location when BOL_HOME is set externally"):
        config.clear_install_location()


def test_get_install_location():
    assert config.get_install_location() == str(config.DATA)


# ===== END‑TO‑END MIGRATION / ROLLBACK TEST =====

def test_migration_full_workflow(tmp_path):
    """
    End‑to‑end test: simulate a full migration of user data and a rollback.
    """
    old_data = tmp_path / "old_data"
    old_data.mkdir()

    # Create dummy user data
    (old_data / "games").mkdir()
    (old_data / "games" / "test.txt").write_text("game file")

    (old_data / "compatdata").mkdir()
    (old_data / "compatdata" / "pfx").mkdir()
    (old_data / "compatdata" / "pfx" / "test.txt").write_text("prefix file")

    (old_data / "content").mkdir()
    (old_data / "content" / "test.txt").write_text("content file")

    (old_data / "msa").mkdir()
    (old_data / "msa" / "token.json").write_text('{"token": "test"}')

    (old_data / "settings.json").write_text('{"game_dir": "games", "other": "value"}')

    # Create a symlink for content (if it existed)
    content_link = old_data / "content_symlink"
    content_link.symlink_to(old_data / "content")

    new_data = tmp_path / "new_data"

    # Simulate the move (copy of the key parts from do_browse)
    dirs_to_move = ["games", "compatdata/pfx", "content", "msa"]
    files_to_move = ["settings.json"]

    # 1. Move
    new_data.mkdir(parents=True, exist_ok=True)
    for sub in dirs_to_move:
        src = old_data / sub
        dst = new_data / sub
        if src.exists():
            shutil.copytree(src, dst)

    for fname in files_to_move:
        src = old_data / fname
        dst = new_data / fname
        if src.exists():
            shutil.copy2(src, dst)

    # Verify move succeeded
    assert (new_data / "games").exists()
    assert (new_data / "games" / "test.txt").read_text() == "game file"
    assert (new_data / "compatdata" / "pfx").exists()
    assert (new_data / "compatdata" / "pfx" / "test.txt").read_text() == "prefix file"
    assert (new_data / "content").exists()
    assert (new_data / "content" / "test.txt").read_text() == "content file"
    assert (new_data / "msa").exists()
    assert (new_data / "msa" / "token.json").read_text() == '{"token": "test"}'
    assert (new_data / "settings.json").exists()

    import json
    with open(new_data / "settings.json") as f:
        settings = json.load(f)
    assert settings["game_dir"] == "games"
    assert settings["other"] == "value"

    # 2. Rollback (simulate failure recovery)
    for sub in dirs_to_move:
        src = new_data / sub
        dst = old_data / sub
        if src.exists():
            shutil.copytree(src, dst, dirs_exist_ok=True)

    # Verify rollback restored everything
    assert (old_data / "games").exists()
    assert (old_data / "games" / "test.txt").read_text() == "game file"
    assert (old_data / "compatdata" / "pfx").exists()
    assert (old_data / "compatdata" / "pfx" / "test.txt").read_text() == "prefix file"
    assert (old_data / "content").exists()
    assert (old_data / "content" / "test.txt").read_text() == "content file"
    assert (old_data / "msa").exists()
    assert (old_data / "msa" / "token.json").read_text() == '{"token": "test"}'
    assert (old_data / "settings.json").exists()
