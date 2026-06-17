"""bol.prefix — Wine prefix and umu lifecycle: boot, kill, reset, options."""
# SPDX-License-Identifier: MIT

import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

from .config import CACHE, COMPAT, HOME, LOGS, PFX, UMU_DIR, UMU_REPO
from .log import die, info, ok, warn
from .proton import proton_path
from .util import _pkill, asset_url, download, gh_latest

def ensure_umu(force=False):
    binp = UMU_DIR / "umu-run"
    if binp.exists() and not force:
        return binp
    rel = gh_latest(UMU_REPO)
    url, fname, _ = asset_url(
        rel, lambda n: n.endswith("zipapp.tar") or n == "umu-run")
    if not url:
        url, fname, _ = asset_url(rel, lambda n: n.endswith((".tar", ".tar.gz")))
    if not url:
        die("umu-launcher asset not found.")
    pkg = CACHE / fname
    info("Downloading umu-launcher …")
    download(url, pkg, "umu-launcher")
    if fname == "umu-run":
        shutil.copy2(pkg, binp)
    else:
        with tarfile.open(pkg) as t:
            t.extractall(UMU_DIR)
        found = next((p for p in UMU_DIR.rglob("umu-run")), None)
        if not found:
            die("umu-run missing from the package.")
        if found != binp:
            shutil.copy2(found, binp)
    os.chmod(binp, 0o755)
    ok("umu-launcher ready")
    return binp


def _existing_gdk_pfx():
    """Reuse an already-working GDK Wine prefix if the host happens to have one
    (some users set one up via another GDK launcher). It already carries
    Microsoft GameInput and the GDK runtime, so reusing it verbatim is a touch
    more reliable than our own. Returns None when there's none — we then build
    and populate our own prefix, so a fresh machine works with no extra setup."""
    base = HOME / "Games/Heroic/Prefixes"
    if not base.is_dir():
        return None
    for d in sorted(base.iterdir()):
        p = d / "pfx" if (d / "pfx").is_dir() else d
        if (p / "drive_c/Program Files/Microsoft GameInput").is_dir():
            return p
    return None


def active_prefix():
    """The Wine prefix the game runs in: an existing GDK prefix when present,
    otherwise our own self-contained one (populated by do_setup)."""
    return _existing_gdk_pfx() or PFX


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
    (HOME / ".steam/steam").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({"GAMEID": "0", "PROTONPATH": str(proton_path()),
                "PROTON_VERB": "run", "WINEPREFIX": str(prefix),
                "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(HOME / ".steam/steam"),
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
    info("Initialising the Wine prefix (first run) …")
    cmd, env = proton_umu_cmd("wineboot", prefix=pfx)
    cmd.append("-u")
    env.setdefault("WINEDEBUG", "-all")
    LOGS.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOGS / "native-login.log", "a") as log:
            subprocess.run(cmd, env=env, stdout=log,
                           stderr=subprocess.STDOUT, timeout=300)
    except Exception as e:
        warn(f"wineboot failed ({e}).")
    end = time.time() + 30
    while time.time() < end and not sys32.is_dir():
        time.sleep(1)
    if not sys32.is_dir():
        warn(f"Wine prefix not initialised (no {sys32}); the in-game mouse "
             "and native login may not work until the next launch.")
        return False
    return True


def kill_prefix_procs(prefix: Path):
    """Kill every process running in a specific Wine prefix, matched by its
    WINEPREFIX env var via /proc — so tearing down one prefix's install never
    touches a game running in another prefix."""
    target = ("WINEPREFIX=" + str(prefix)).encode() + b"\0"
    for pdir in Path("/proc").glob("[0-9]*"):
        try:
            if target in pdir.joinpath("environ").read_bytes():
                os.kill(int(pdir.name), 9)
        except Exception:
            continue


def kill_wine():
    """Kill leftover wine/Proton (a hung run locks the prefix)."""
    for pat in ("wineserver", "winedevice.exe", "GDK-Proton",
                "Minecraft.Windows.exe", "umu_run.py", "umu-shim",
                "pv-adverb", "pressure-vessel"):
        _pkill(pat)


def reset_prefix():
    kill_wine()
    time.sleep(1)
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
    try:
        return subprocess.run(["pgrep", "-f", "Minecraft.Windows.exe"],
                              capture_output=True).returncode == 0
    except Exception:
        return False
