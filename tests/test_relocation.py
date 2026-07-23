# tests/test_relocation.py
# SPDX-License-Identifier: MIT
"""Tests for the data directory relocation feature."""
import json
import shutil
import sys
from pathlib import Path

# Add project root to sys.path so 'bol' can be imported
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest

from bol import config
from bol import relocation
from bol.relocation import migrate_data, paths_overlap, RelocationError


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


# ===== helpers =====

def _make_user_data(base: Path, version="1.21.0"):
    """Populate `base` with a realistic user-data layout."""
    games_dir = base / "games" / version
    games_dir.mkdir(parents=True)
    (games_dir / "Minecraft.Windows.exe").write_text("exe")
    (games_dir / "test.txt").write_text("game file")

    (base / "compatdata" / "pfx").mkdir(parents=True)
    (base / "compatdata" / "pfx" / "test.txt").write_text("prefix file")

    (base / "content").mkdir()
    (base / "content" / "test.txt").write_text("content file")

    (base / "msa").mkdir()
    (base / "msa" / "token.json").write_text('{"token": "test"}')

    (base / "settings.json").write_text(json.dumps({
        "game_dir": str(games_dir),
        "other": "value",
    }))
    return games_dir


# ===== paths_overlap =====

def test_paths_overlap_same_dir(tmp_path):
    a = tmp_path / "data"
    a.mkdir()
    assert paths_overlap(a, a) is True


def test_paths_overlap_nested_new_inside_old(tmp_path):
    old_dir = tmp_path / "data"
    old_dir.mkdir()
    new_dir = old_dir / "sub" / "deeper"
    assert paths_overlap(old_dir, new_dir) is True


def test_paths_overlap_nested_old_inside_new(tmp_path):
    new_dir = tmp_path / "data"
    new_dir.mkdir()
    old_dir = new_dir / "sub"
    old_dir.mkdir()
    assert paths_overlap(old_dir, new_dir) is True


def test_paths_overlap_unrelated_dirs(tmp_path):
    a = tmp_path / "old"
    b = tmp_path / "new"
    a.mkdir()
    assert paths_overlap(a, b) is False


def test_migrate_data_rejects_overlap(tmp_path, monkeypatch):
    monkeypatch.setattr(
        config, "INSTALL_LOCATION_FILE",
        tmp_path / ".config" / "bedrock-on-linux" / "install_location")
    old_dir = tmp_path / "data"
    old_dir.mkdir()
    with pytest.raises(RelocationError):
        migrate_data(old_dir, old_dir / "nested")


# ===== end-to-end migration test (calls the real production code) =====

def test_migration_full_workflow(tmp_path, monkeypatch):
    monkeypatch.setattr(
        config, "INSTALL_LOCATION_FILE",
        tmp_path / ".config" / "bedrock-on-linux" / "install_location")
    old_dir = tmp_path / "old_data"
    old_dir.mkdir()
    games_dir = _make_user_data(old_dir)

    new_dir = tmp_path / "new_data"
    migrate_data(old_dir, new_dir)

    # Data actually moved
    new_games_dir = new_dir / "games" / games_dir.name
    assert (new_games_dir / "Minecraft.Windows.exe").exists()
    assert (new_games_dir / "test.txt").read_text() == "game file"
    assert (new_dir / "compatdata" / "pfx" / "test.txt").read_text() == "prefix file"
    assert (new_dir / "content" / "test.txt").read_text() == "content file"
    assert (new_dir / "msa" / "token.json").read_text() == '{"token": "test"}'

    # settings.json moved and game_dir re-anchored to the *exact*
    # relocated folder (not just "games")
    settings = json.loads((new_dir / "settings.json").read_text())
    assert settings["game_dir"] == str(new_games_dir.resolve())
    assert settings["other"] == "value"

    # Old location no longer has the moved items
    assert not (old_dir / "games").exists()

    # Install location pointer updated
    assert config.get_install_location() == str(config.DATA)  # sanity: importable
    assert config.INSTALL_LOCATION_FILE.read_text().strip() == str(new_dir)


def test_migration_recreates_content_symlink(tmp_path, monkeypatch):
    """Covers content symlinked to something OUTSIDE old_dir (e.g.
    imported content kept on a separate drive) -- target is untouched
    by the move, so the recreated link should point at the exact same
    external path."""
    monkeypatch.setattr(
        config, "INSTALL_LOCATION_FILE",
        tmp_path / ".config" / "bedrock-on-linux" / "install_location")
    old_dir = tmp_path / "old_data"
    old_dir.mkdir()
    _make_user_data(old_dir)

    external = tmp_path / "external_content"
    external.mkdir()
    (external / "pack.mcpack").write_text("pack")
    content_link = old_dir / "content"
    shutil.rmtree(content_link)
    content_link.symlink_to(external)

    new_dir = tmp_path / "new_data"
    migrate_data(old_dir, new_dir)

    new_content = new_dir / "content"
    assert new_content.is_symlink()
    assert new_content.resolve() == external.resolve()
    assert (new_content / "pack.mcpack").read_text() == "pack"


def test_migration_recreates_content_symlink_pointing_inside_old_dir(tmp_path, monkeypatch):
    """Covers content symlinked to somewhere INSIDE old_dir (e.g.
    content -> games/<version>/resource_packs). That target moves along
    with everything else, so the recreated link must be re-anchored
    under new_dir instead of kept pointing at the now-gone old path."""
    monkeypatch.setattr(
        config, "INSTALL_LOCATION_FILE",
        tmp_path / ".config" / "bedrock-on-linux" / "install_location")
    old_dir = tmp_path / "old_data"
    old_dir.mkdir()
    games_dir = _make_user_data(old_dir)

    internal_target = games_dir / "resource_packs"
    internal_target.mkdir()
    (internal_target / "pack.mcpack").write_text("internal pack")

    content_link = old_dir / "content"
    shutil.rmtree(content_link)
    content_link.symlink_to(internal_target)

    new_dir = tmp_path / "new_data"
    migrate_data(old_dir, new_dir)

    new_content = new_dir / "content"
    expected_target = new_dir / "games" / games_dir.name / "resource_packs"
    assert new_content.is_symlink()
    assert new_content.resolve() == expected_target.resolve()
    assert (new_content / "pack.mcpack").read_text() == "internal pack"


def test_migration_rollback_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        config, "INSTALL_LOCATION_FILE",
        tmp_path / ".config" / "bedrock-on-linux" / "install_location")
    old_dir = tmp_path / "old_data"
    old_dir.mkdir()
    _make_user_data(old_dir)

    new_dir = tmp_path / "new_data"

    def boom(*a, **kw):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(relocation, "_rewrite_game_dir", boom)

    with pytest.raises(RelocationError):
        migrate_data(old_dir, new_dir)

    # Everything should be back where it started
    assert (old_dir / "games").exists()
    assert (old_dir / "compatdata" / "pfx" / "test.txt").read_text() == "prefix file"
    assert (old_dir / "content" / "test.txt").read_text() == "content file"
    assert (old_dir / "msa" / "token.json").exists()
    assert (old_dir / "settings.json").exists()

    # Pointer restored to the old location
    assert config.INSTALL_LOCATION_FILE.read_text().strip() == str(old_dir)


def test_migration_rollback_restores_backup_when_source_move_fails(tmp_path, monkeypatch):
    """If a pre-existing destination folder is backed up to '.old' and
    THEN the source move fails, the backup must be restored -- not left
    stranded under 'games.old' forever."""
    monkeypatch.setattr(
        config, "INSTALL_LOCATION_FILE",
        tmp_path / ".config" / "bedrock-on-linux" / "install_location")
    old_dir = tmp_path / "old_data"
    old_dir.mkdir()
    _make_user_data(old_dir)

    new_dir = tmp_path / "new_data"
    new_dir.mkdir()
    # Pre-populate the destination "games" folder so _move_item has to
    # back it up (.old) before attempting the source move.
    existing_games = new_dir / "games"
    existing_games.mkdir(parents=True)
    (existing_games / "marker.txt").write_text("pre-existing destination data")

    real_move = shutil.move
    call_count = {"n": 0}

    def flaky_move(src, dst, *a, **kw):
        call_count["n"] += 1
        # Call 1 = backup of the pre-existing "games" -> "games.old".
        # Call 2 = the actual src -> dst move for "games" -- fail here,
        # *after* the backup has already succeeded.
        if call_count["n"] == 2:
            raise RuntimeError("simulated mid-move failure")
        return real_move(src, dst, *a, **kw)

    monkeypatch.setattr(relocation.shutil, "move", flaky_move)

    with pytest.raises(RelocationError):
        migrate_data(old_dir, new_dir)

    # Pre-existing destination data must be restored, not stranded in
    # "games.old".
    assert (new_dir / "games" / "marker.txt").read_text() == "pre-existing destination data"
    assert not (new_dir / "games.old").exists()
    # Source data untouched.
    assert (old_dir / "games").exists()
    assert config.INSTALL_LOCATION_FILE.read_text().strip() == str(old_dir)
