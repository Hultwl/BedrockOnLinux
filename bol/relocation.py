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
import os
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
    # Record *before* attempting the source move: if the backup above
    # succeeded but the move below throws partway through (e.g. a
    # cross-filesystem move that dies mid-copy), rollback still needs
    # to know a backup exists at dst_path.name + ".old" so it can be
    # restored. Recording only after both steps succeed would leave
    # that backup permanently stranded on failure.
    moved_items.append((src_path, dst_path, backup))
    shutil.move(str(src_path), str(dst_path))


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


def _restore_original_settings(old_dir: Path, original_bytes) -> None:
    """After a rollback, put settings.json's original *content* back.

    _rollback() only restores which file lives at old_dir/settings.json
    -- it doesn't know or care what's inside it. If _rewrite_game_dir
    already mutated the file in place (pointing game_dir at new_dir)
    before a later step failed, the moved-back file would still contain
    that rewritten, now-wrong value unless we explicitly overwrite it
    with what was there before relocation started.
    """
    if original_bytes is None:
        return
    try:
        (old_dir / "settings.json").write_bytes(original_bytes)
    except Exception as e:
        log.warn(f"Could not restore original settings.json: {e}")


def _restore_original_content_link(old_dir: Path, original_target) -> None:
    """After a rollback, put the content symlink's original (literal,
    pre-relocation) target back.

    _recreate_content_symlink() doesn't move the original symlink -- it
    deletes whatever's at new_dir/content and creates a brand new link
    with a re-anchored target. If a later step then fails, _rollback()
    moves that *recreated* link back to old_dir/content, which now
    points somewhere that only made sense relative to new_dir. This
    restores the exact original link target captured before anything
    was touched.
    """
    if original_target is None:
        return
    old_content = old_dir / "content"
    try:
        if old_content.is_symlink() or old_content.exists():
            if old_content.is_dir() and not old_content.is_symlink():
                shutil.rmtree(old_content)
            else:
                old_content.unlink()
        old_content.symlink_to(original_target)
    except Exception as e:
        log.warn(f"Could not restore original content symlink: {e}")


def _rewrite_game_dir(new_dir: Path, old_games_dir: Path) -> None:
    """Update settings.json's game_dir to point at the relocated games
    folder.

    game_dir is an absolute path to the exact folder containing
    Minecraft.Windows.exe (e.g. .../games/<version>/), not just the
    games directory itself -- launch() needs that exact folder. So we
    re-anchor it by preserving its path *relative to* the old games
    directory, rather than collapsing it to "games".

    Any I/O or JSON error here (corrupt file, permission denied, disk
    full mid-write) is allowed to propagate. migrate_data() must treat
    that as a fatal relocation failure and roll back -- silently
    swallowing it here would report success with a stale or corrupted
    game_dir.
    """
    settings_path = new_dir / "settings.json"
    if not settings_path.exists():
        return
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
            # layout, e.g. set manually) -- leave it as-is rather than
            # guess. This is a legitimate, non-fatal case, unlike an
            # I/O or JSON error above.
            log.warn(
                "game_dir was not under the old games directory; "
                "leaving it unchanged")
    with open(settings_path, "w") as f:
        json.dump(settings_data, f, indent=2)


def _recreate_content_symlink(old_content_target, old_dir: Path, new_dir: Path) -> None:
    """If "content" was a symlink (not a real directory) before the
    move, recreate it at the new location.

    If the original target lived *inside* old_dir (e.g.
    content -> games/<version>/resource_packs), it's re-anchored under
    new_dir -- otherwise it would keep pointing at a path that no
    longer exists once games/ has moved. If the target was external to
    old_dir (e.g. content imported from a separate drive), it's left
    unchanged since it never moved.

    old_content_target must be captured *before* anything is moved --
    once the link itself has been relocated by _move_item, there's
    nothing left at the old path to inspect.

    Any OSError here (unsupported on this filesystem, permission
    denied, etc.) is allowed to propagate. migrate_data() must treat
    that as fatal and roll back -- silently swallowing it here would
    report success with a broken symlink.
    """
    if old_content_target is None:
        return
    new_content = new_dir / "content"
    target = old_content_target
    try:
        rel = target.relative_to(old_dir.resolve())
        target = new_dir.resolve() / rel
    except ValueError:
        pass  # target isn't under old_dir -- leave it as-is
    if new_content.is_symlink() or new_content.exists():
        if new_content.is_dir() and not new_content.is_symlink():
            shutil.rmtree(new_content)
        else:
            new_content.unlink()
    new_content.symlink_to(target)


def migrate_data(old_dir, new_dir) -> None:
    """Move user data (worlds/saves, imported content, login tokens,
    settings) from old_dir to new_dir, and persist new_dir as the
    install location.

    On any failure, everything moved so far is rolled back, the
    original settings.json content and content-symlink target are
    restored (not just "a" settings.json / symlink -- the exact
    pre-relocation ones), and the install location pointer is restored
    to old_dir, then RelocationError is raised.
    """
    old_dir = Path(old_dir)
    new_dir = Path(new_dir)
    if paths_overlap(old_dir, new_dir):
        raise RelocationError(
            "The new location overlaps with the current location.")

    moved_items = []

    # Captured *before* anything is touched. This has to happen up
    # front, not just before each individual step, because a failure
    # in ANY later step -- including inside _rewrite_game_dir,
    # _recreate_content_symlink, or set_install_location itself --
    # must be fully undoable, not just the plain file-move part.
    old_content = old_dir / "content"
    content_target = old_content.resolve() if old_content.is_symlink() else None
    original_content_link = (
        os.readlink(str(old_content)) if old_content.is_symlink() else None
    )
    settings_src = old_dir / "settings.json"
    original_settings_bytes = (
        settings_src.read_bytes() if settings_src.exists() else None
    )
    old_games_dir = old_dir / "games"

    try:
        new_dir.mkdir(parents=True, exist_ok=True)

        for sub in DIRS_TO_MOVE:
            _move_item(old_dir / sub, new_dir / sub, moved_items)
        for fname in FILES_TO_MOVE:
            _move_item(old_dir / fname, new_dir / fname, moved_items)

        _recreate_content_symlink(content_target, old_dir, new_dir)
        _rewrite_game_dir(new_dir, old_games_dir)
        set_install_location(new_dir)
    except Exception as e:
        _rollback(moved_items)
        _restore_original_content_link(old_dir, original_content_link)
        _restore_original_settings(old_dir, original_settings_bytes)
        try:
            set_install_location(old_dir)
        except Exception:
            try:
                INSTALL_LOCATION_FILE.parent.mkdir(parents=True, exist_ok=True)
                INSTALL_LOCATION_FILE.write_text(str(old_dir), encoding="utf-8")
            except Exception:
                pass
        raise RelocationError(str(e)) from e
