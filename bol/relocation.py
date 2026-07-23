# bol/relocation.py
# SPDX-License-Identifier: MIT
"""bol.relocation — moves the data directory's user content to a new
location (worlds/saves, imported content, login tokens, settings).

This is deliberately kept separate from bol.gui so it can be exercised
directly by tests: the GUI's "Game files location" feature (Settings ->
Advanced) is a thin wrapper that collects a target directory from the
user and calls migrate_data() on a background thread.
"""

import json
import shutil
from pathlib import Path

from . import log
from .config import INSTALL_LOCATION_FILE, set_install_location

# Directories moved as part of relocation, relative to the data dir.
DIRS_TO_MOVE = ["games", "compatdata/pfx", "content", "msa"]
# Files moved as part of relocation, relative to the data dir.
FILES_TO_MOVE = ["settings.json"]


class RelocationError(Exception):
    """Raised when a relocation fails. The data directory is guaranteed
    to have been rolled back to its pre-relocation state (best effort)
    before this is raised."""


def paths_overlap(old_dir: Path, new_dir: Path) -> bool:
    """True if old_dir and new_dir are the same directory, or one is
    nested inside the other, once both are resolved to their canonical
    (symlink-free, absolute) form.

    A relocation into a subdirectory of itself (or vice versa) is not a
    safe operation: moving old_dir/games into new_dir when new_dir is
    itself old_dir/games/foo would move a directory into its own
    descendant mid-walk, corrupting the source and destination alike.
    """
    old_r = old_dir.resolve()
    # new_dir may not exist yet -- resolve() still normalizes safely.
    new_r = new_dir.resolve()

    if old_r == new_r:
        return True
    try:
        new_r.relative_to(old_r)
        return True
    except ValueError:
        pass
    try:
        old_r.relative_to(new_r)
        return True
    except ValueError:
        pass
    return False


def _move_item(src_path: Path, dst_path: Path, moved_items: list) -> None:
    """Move src_path -> dst_path, backing up any pre-existing dst_path
    with a '.old' suffix first. Records what happened in moved_items so
    it can be undone by _rollback().
    """
    if not src_path.exists() and not src_path.is_symlink():
        return
    backup = None
    if dst_path.exists() or dst_path.is_symlink():
        backup = dst_path.with_name(dst_path.name + ".old")
        if backup.exists() or backup.is_symlink():
            if backup.is_dir() and not backup.is_symlink():
                shutil.rmtree(backup)
            else:
                backup.unlink()
        shutil.move(str(dst_path), str(backup))
    shutil.move(str(src_path), str(dst_path))
    moved_items.append((src_path, dst_path, backup))


def _rollback(moved_items: list) -> None:
    """Best-effort undo of everything _move_item() did, in reverse
    order. Never raises -- a rollback failure is logged, not thrown,
    since it typically runs from inside an except block already
    handling a more important error."""
    for src, dst, backup in reversed(moved_items):
        try:
            if dst.exists() or dst.is_symlink():
                shutil.move(str(dst), str(src))
            if backup is not None and (backup.exists() or backup.is_symlink()):
                shutil.move(str(backup), str(dst))
        except Exception as e:
            log.warn(f"Rollback step failed for {src} <- {dst}: {e}")


def _rewrite_game_dir(new_dir: Path, old_games_dir: Path) -> None:
    """Update settings.json's game_dir to point at the relocated games
    folder.

    game_dir is an absolute path to the exact folder containing
    Minecraft.Windows.exe (e.g. .../games/<version>/), not just the
    games directory itself -- launch() needs that exact folder. So we
    re-anchor it by preserving its path *relative to* the old games
    directory, rather than collapsing it to "games".
    """
    settings_path = new_dir / "settings.json"
    if not settings_path.exists():
        return
    try:
        with open(settings_path, "r") as f:
            settings_data = json.load(f)
        old_game_dir = settings_data.get("game_dir")
        if old_game_dir:
            try:
                rel = Path(old_game_dir).resolve().relative_to(
                    old_games_dir.resolve())
                settings_data["game_dir"] = str((new_dir / "games" / rel).resolve())
            except ValueError:
                # game_dir wasn't under the old games dir (unexpected
                # layout, e.g. set manually) -- leave it as-is rather
                # than guess and point launch() at the wrong folder.
                log.warn(
                    "game_dir was not under the old games directory; "
                    "leaving it unchanged")
        with open(settings_path, "w") as f:
            json.dump(settings_data, f, indent=2)
    except Exception as e:
        # Not fatal to the relocation itself, but worth surfacing.
        log.warn(f"Could not update game_dir in settings.json: {e}")


def _recreate_content_symlink(old_content_target, new_dir: Path) -> None:
    """If "content" was a symlink (not a real directory) before the
    move, recreate it at the new location pointing at the same target.

    This must be captured *before* content is moved -- once the link
    itself has been relocated by _move_item, there's nothing left at
    the old path to inspect.
    """
    if old_content_target is None:
        return
    new_content = new_dir / "content"
    try:
        if new_content.is_symlink() or new_content.exists():
            if new_content.is_dir() and not new_content.is_symlink():
                shutil.rmtree(new_content)
            else:
                new_content.unlink()
        new_content.symlink_to(old_content_target)
    except OSError as e:
        log.warn(f"Could not recreate content symlink: {e}")


def migrate_data(old_dir, new_dir) -> None:
    """Move user data (worlds/saves, imported content, login tokens,
    settings) from old_dir to new_dir, and persist new_dir as the
    install location.

    On any failure, everything moved so far is rolled back and the
    install location pointer is restored to old_dir, then
    RelocationError is raised.
    """
    old_dir = Path(old_dir)
    new_dir = Path(new_dir)

    if paths_overlap(old_dir, new_dir):
        raise RelocationError(
            "The new location overlaps with the current location.")

    moved_items = []
    try:
        new_dir.mkdir(parents=True, exist_ok=True)

        # Capture the "content" symlink's target (if any) before it's
        # moved out from under us.
        old_content = old_dir / "content"
        content_target = old_content.resolve() if old_content.is_symlink() else None
        old_games_dir = old_dir / "games"

        for sub in DIRS_TO_MOVE:
            _move_item(old_dir / sub, new_dir / sub, moved_items)

        for fname in FILES_TO_MOVE:
            _move_item(old_dir / fname, new_dir / fname, moved_items)

        _recreate_content_symlink(content_target, new_dir)
        _rewrite_game_dir(new_dir, old_games_dir)

        set_install_location(new_dir)

    except Exception as e:
        _rollback(moved_items)
        try:
            set_install_location(old_dir)
        except Exception:
            try:
                INSTALL_LOCATION_FILE.parent.mkdir(parents=True, exist_ok=True)
                INSTALL_LOCATION_FILE.write_text(str(old_dir), encoding="utf-8")
            except Exception:
                pass
        raise RelocationError(str(e)) from e
