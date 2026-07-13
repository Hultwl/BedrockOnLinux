"""bol.prefix — Wine prefix and umu lifecycle: boot, kill, reset, options."""
# SPDX-License-Identifier: MIT

import hashlib
import fcntl
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .archive import safe_extract_tar
from .config import (
    CACHE,
    COMPAT,
    DATA,
    HOME,
    LOGS,
    PFX,
    UMU_ARCHIVE_SHA256,
    UMU_ASSET,
    UMU_DIR,
    UMU_REPO,
    UMU_RUN_SHA256,
    UMU_VERSION,
)
from .log import BolError, die, info, ok, warn
from .proton import proton_path
from .util import download

def ensure_umu(force=False):
    binp = UMU_DIR / "umu-run"
    if binp.is_file() and not force:
        try:
            if hashlib.sha256(binp.read_bytes()).hexdigest() == UMU_RUN_SHA256:
                return binp
        except OSError:
            pass
        warn("Installed umu-launcher is stale or modified; repairing it.")
    url = (f"https://github.com/{UMU_REPO}/releases/download/"
           f"{UMU_VERSION}/{UMU_ASSET}")
    pkg = CACHE / UMU_ASSET
    expected_archive_hash = UMU_ARCHIVE_SHA256.lower()
    actual_archive_hash = None
    if pkg.is_file():
        try:
            actual_archive_hash = hashlib.sha256(pkg.read_bytes()).hexdigest()
        except OSError:
            pass
    if actual_archive_hash != expected_archive_hash:
        pkg.unlink(missing_ok=True)
        info("Downloading umu-launcher …")
        download(url, pkg, "umu-launcher")
        actual_archive_hash = hashlib.sha256(pkg.read_bytes()).hexdigest()
    if actual_archive_hash != expected_archive_hash:
        pkg.unlink(missing_ok=True)
        raise ValueError(
            "umu-launcher archive SHA-256 mismatch (expected %s, got %s)" %
            (expected_archive_hash, actual_archive_hash))
    UMU_DIR.mkdir(parents=True, exist_ok=True)
    staging = None
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".umu-run-", dir=UMU_DIR)
    os.close(tmp_fd)
    tmp_bin = Path(tmp_name)
    try:
        staging = Path(tempfile.mkdtemp(
            prefix=".umu-extract-", dir=UMU_DIR.parent))
        with tarfile.open(pkg) as archive:
            safe_extract_tar(archive, staging)
        source = next((p for p in staging.rglob("umu-run")
                       if p.is_file()), None)
        if not source:
            die("umu-run missing from the package.")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if source_hash != UMU_RUN_SHA256:
            raise ValueError(
                "umu-run SHA-256 mismatch (expected %s, got %s)" %
                (UMU_RUN_SHA256, source_hash))
        shutil.copy2(source, tmp_bin)
        os.chmod(tmp_bin, 0o755)
        tmp_bin.replace(binp)
    finally:
        tmp_bin.unlink(missing_ok=True)
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    ok("umu-launcher ready")
    return binp


def active_prefix():
    """Return the app-owned prefix, unless the user explicitly opts out.

    Older builds silently reused the first Heroic GDK prefix they found.  That
    made PLAY/Repair/Force-stop modify or kill another application's Wine
    session.  Isolation is the safe default on every distribution; advanced
    users can still opt in deliberately with ``BOL_WINEPREFIX``.
    """
    override = os.environ.get("BOL_WINEPREFIX", "").strip()
    return Path(override).expanduser() if override else PFX


@contextmanager
def prefix_operation_lock(operation="modify the Wine prefix"):
    """Serialize every prefix-mutating operation.

    The lock is intentionally held for the complete game session. Repair and
    setup therefore cannot delete or rewrite the prefix behind a running game,
    while the explicit Force-stop action remains lock-free so it can end that
    session.
    """
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / ".launch.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(path, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BolError(
                f"Cannot {operation}: another BedrockOnLinux setup, repair, "
                "or game session is already in progress. Close Minecraft or "
                "use 'Force stop Minecraft' before trying again."
            ) from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextmanager
def launch_lock():
    """Serialize PLAY with setup/repair and without stale crash locks."""
    with prefix_operation_lock("start Minecraft"):
        yield


def steam_compat_dir():
    """A directory for STEAM_COMPAT_CLIENT_INSTALL_PATH — umu/Proton require one.

    We prefer the host's ~/.steam/steam: on a machine with Steam it's a symlink
    to the real client install, which umu happily reuses. That preference is
    also the trap — on a Steam Deck ~/.steam/steam points at ~/.local/share/Steam,
    which our Flatpak sandbox can't see (we only grant ~/.steam, not the target),
    leaving a *dangling* symlink: the name exists yet isn't a directory, so even
    mkdir(exist_ok=True) raises FileExistsError on it and the launch aborts
    (issue #19). So only create it when nothing is in the way; if anything is
    (a dangling/foreign symlink, an unwritable ~/.steam), fall back to a dir we
    own. Proton needs no real Steam files here — a writable empty dir is enough,
    which is exactly what a fresh, Steam-less machine already runs with."""
    steam = HOME / ".steam/steam"
    if steam.is_dir():                     # real Steam, or one we made earlier
        return steam
    try:
        steam.mkdir(parents=True, exist_ok=True)
        return steam
    except OSError:
        fallback = DATA / "steamcompat"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def proton_umu_cmd(exe, prefix=None):
    """Launch GDK-Proton through umu-launcher (Steam Linux Runtime). The GDK
    networking the LAN/server join needs only works inside that runtime, not
    with a bare `proton run`."""
    if prefix is None:
        prefix = active_prefix()
    if prefix == PFX:
        COMPAT.mkdir(parents=True, exist_ok=True)
        if PFX.is_symlink():               # drop any legacy symlink layout
            PFX.unlink()
            for junk in ("pfx.lock", "version", "tracked_files",
                         "config_info"):
                (COMPAT / junk).unlink(missing_ok=True)
    else:
        info(f"Using existing GDK prefix: {prefix}")
    steam_compat = steam_compat_dir()
    env = dict(os.environ)
    env.update({"GAMEID": "0", "PROTONPATH": str(proton_path()),
                "PROTON_VERB": "run", "WINEPREFIX": str(prefix),
                "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(steam_compat),
                "UMU_RUNTIME_UPDATE": "0"})
    return [sys.executable, str(ensure_umu()), exe], env


def boot_prefix(prefix=None):
    """Ensure the Wine prefix is initialised — i.e. drive_c/windows/system32
    exists. Proton/umu create and boot the prefix on first use, but several
    setup steps (the cryptbase RNG stub, the GameInput redist) write straight
    into system32; on a brand-new prefix they otherwise fail with 'system32
    not found' (issue #10). This runs wineboot through umu and waits for
    system32 to appear. Idempotent: returns at once once the prefix is ready."""
    pfx = Path(prefix or active_prefix())
    sys32 = pfx / "drive_c/windows/system32"
    if sys32.is_dir():
        return True
    # This is the only setup helper which may execute Wine.  Refuse a known
    # broken display/driver before UMU or Wine can open a device.
    from .gpu_safety import require_safe_graphics_session
    require_safe_graphics_session()
    info("Initialising the Wine prefix (first run) …")
    cmd, env = proton_umu_cmd("wineboot", prefix=pfx)
    cmd.append("-u")
    env = headless_setup_env(env)
    env.setdefault("WINEDEBUG", "-all")
    LOGS.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOGS / "native-login.log", "a") as log:
            subprocess.run(cmd, env=env, stdout=log,
                           stderr=subprocess.STDOUT, timeout=300)
    except Exception as e:
        warn(f"wineboot failed ({e}).")
    finally:
        # wineboot sometimes leaves services behind.  Registry updates which
        # follow are offline, so finish the setup session gracefully first.
        stop_prefix_procs(pfx, grace=5)
    end = time.time() + 30
    while time.time() < end and not sys32.is_dir():
        time.sleep(1)
    if not sys32.is_dir():
        warn(f"Wine prefix not initialised (no {sys32}); the in-game mouse "
             "and native login may not work until the next launch.")
        return False
    return True


def prefix_processes(prefix: Path):
    """Return live PIDs carrying this exact ``WINEPREFIX`` environment."""
    target = ("WINEPREFIX=" + str(prefix)).encode() + b"\0"
    found = []
    for pdir in Path("/proc").glob("[0-9]*"):
        try:
            if target in pdir.joinpath("environ").read_bytes():
                pid = int(pdir.name)
                if pid != os.getpid():
                    found.append(pid)
        except Exception:
            continue
    return sorted(set(found))


def require_prefix_idle(prefix: Path, action="modify the Wine prefix"):
    """Fail before an offline mutation while wineserver still owns the hive."""
    live = prefix_processes(Path(prefix))
    if live:
        raise BolError(
            f"Cannot {action}: {len(live)} Wine/Proton process(es) still use "
            "this prefix. Close Minecraft or use 'Force stop Minecraft' first."
        )
    return True


def stop_prefix_procs(prefix: Path, grace=5, kill_grace=2):
    """Stop a prefix, including children spawned during shutdown.

    A one-shot PID snapshot misses services which wineserver/explorer creates
    while their parents are exiting. Keep rescanning through both TERM and KILL
    phases, and do not let an offline registry writer proceed until the prefix
    is demonstrably idle.
    """
    prefix = Path(prefix)
    seen = set()
    term_sent = set()
    deadline = time.monotonic() + max(0, grace)

    while True:
        live = set(prefix_processes(prefix))
        if not live:
            return len(seen), 0
        seen.update(live)
        for pid in live - term_sent:
            try:
                os.kill(pid, 15)
            except (ProcessLookupError, PermissionError):
                pass
            term_sent.add(pid)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.1, remaining))

    forced = set()
    kill_deadline = time.monotonic() + max(0, kill_grace)
    while True:
        live = set(prefix_processes(prefix))
        if not live:
            return len(seen), len(forced)
        seen.update(live)
        for pid in live:
            try:
                os.kill(pid, 9)
            except (ProcessLookupError, PermissionError):
                pass
            else:
                forced.add(pid)
        remaining = kill_deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.1, remaining))

    live = prefix_processes(prefix)
    if live:
        raise BolError(
            f"Could not stop {len(live)} Wine/Proton process(es) for this "
            "prefix; refusing unsafe offline changes."
        )
    return len(seen), len(forced)


def headless_setup_env(env):
    """Prevent non-graphical Wine setup helpers from initialising a GPU."""
    result = dict(env)
    result.pop("DISPLAY", None)
    result.pop("WAYLAND_DISPLAY", None)
    result.pop("XAUTHORITY", None)
    result.pop("PROTON_ENABLE_WAYLAND", None)
    result["SDL_VIDEODRIVER"] = "dummy"
    disabled = "winevulkan=;dxgi=;d3d11=;d3d12="
    current = result.get("WINEDLLOVERRIDES", "")
    result["WINEDLLOVERRIDES"] = disabled + (";" + current if current else "")
    return result


def kill_wine():
    """Explicit GUI action: stop only this application's Wine prefix."""
    stopped, forced = stop_prefix_procs(active_prefix())
    if stopped:
        ok(f"Stopped {stopped} BedrockOnLinux process(es)"
           + (f" ({forced} forced)." if forced else "."))
    else:
        info("No BedrockOnLinux Wine process is running.")


def reset_prefix():
    # Repair never deletes an explicitly supplied third-party prefix.
    with prefix_operation_lock("repair the Wine prefix"):
        stop_prefix_procs(PFX)
        require_prefix_idle(PFX, "repair the Wine prefix")
        if COMPAT.exists():
            shutil.rmtree(COMPAT, ignore_errors=True)
        ok("Wine prefix reset — rebuilt on next launch.")


OPTIONS_REL = ("drive_c/users/steamuser/AppData/Roaming/Minecraft Bedrock/"
               "Users/Shared/games/com.mojang/minecraftpe/options.txt")


def patch_options():
    opt = PFX / OPTIONS_REL
    if not opt.exists():
        return
    kv, order = {}, []
    for l in opt.read_text(errors="ignore").splitlines():
        if ":" in l:
            k, _, v = l.partition(":")
            k = k.strip()
            if k not in kv:
                order.append(k)
            kv[k] = v.strip()
    if kv.get("do_not_show_multiplayer_online_safety_warning") == "1":
        return
    if "do_not_show_multiplayer_online_safety_warning" not in order:
        order.append("do_not_show_multiplayer_online_safety_warning")
    kv["do_not_show_multiplayer_online_safety_warning"] = "1"
    opt.write_text("\n".join(f"{k}:{kv[k]}" for k in order) + "\n")
    ok("Multiplayer warning disabled")


def _mc_running():
    for pid in prefix_processes(active_prefix()):
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
            if b"Minecraft.Windows.exe" in cmdline:
                return True
        except OSError:
            continue
    return False
