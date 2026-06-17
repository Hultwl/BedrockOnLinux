"""bol.games — Minecraft version listing, download and selection."""
# SPDX-License-Identifier: MIT

import re
import shutil
import zipfile
from pathlib import Path

from .config import CACHE, CONTENT, GAMES, GAME_ARCHIVE_REPO
from .log import die, info, ok
from .util import asset_url, download, gh_releases, load_settings, save_settings

def list_mc_versions(include_beta=True):
    out = []
    for r in gh_releases(GAME_ARCHIVE_REPO, 60):
        url, name, size = asset_url(
            r, lambda n: n.lower().endswith(".zip") and "minecraft" in n.lower())
        if not url:
            continue
        if r.get("prerelease") and not include_beta:
            continue
        out.append({"tag": r["tag_name"], "beta": bool(r.get("prerelease")),
                    "url": url, "name": name, "size": size})
    return out


def _game_root(dest):
    """Folder of a complete extracted build (exe + appxmanifest), else None
    (a bare exe with no manifest means a truncated extract → reinstall)."""
    if not dest.exists():
        return None
    for exe in dest.rglob("Minecraft.Windows.exe"):
        if any((exe.parent / m).exists()
               for m in ("appxmanifest.xml", "AppxManifest.xml")):
            return exe.parent
    return None


def download_game(ver, progress=None, force=False):
    """ver: a list_mc_versions() entry. force re-extracts (re-downloads
    only if the archive isn't cached)."""
    GAMES.mkdir(parents=True, exist_ok=True)
    dest = GAMES / ver["tag"]
    root = _game_root(dest)
    if root and not force:
        info(f"Minecraft {ver['tag']} already installed")
        return root
    zp = CACHE / ver["name"]
    if not zp.exists():
        info(f"Downloading Minecraft {ver['tag']} "
             f"(~{ver['size']>>20} Mio) …")
        download(ver["url"], zp, f"Minecraft {ver['tag']}", progress)
    info(f"{'Reinstalling' if root else 'Installing'} Minecraft "
         f"{ver['tag']} …")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(zp) as z:
        z.extractall(dest)
    root = _game_root(dest)
    if not root:
        die("Minecraft.Windows.exe missing from the archive.")
    ok(f"Minecraft {ver['tag']} installed")
    return root


def use_game_dir(folder):
    folder = Path(folder).expanduser().resolve()
    if not (folder / "Minecraft.Windows.exe").exists():
        # Often a parent of version sub-folders → take the newest build.
        cands = list(folder.rglob("Minecraft.Windows.exe"))
        if not cands:
            die(f"Minecraft.Windows.exe not found in {folder} (nor in "
                f"its subfolders). Choose an extracted version folder, "
                f"or use '① Minecraft version'.")
        best = max(cands, key=lambda e: _vt(mc_version_str(e.parent) or "0"))
        folder = best.parent
        info(f"Minecraft found: {folder} "
             f"(version {mc_version_str(folder) or '?'})")
    if CONTENT.is_symlink() or CONTENT.exists():
        CONTENT.unlink() if CONTENT.is_symlink() else shutil.rmtree(CONTENT)
    CONTENT.symlink_to(folder)
    s = load_settings()
    s["game_dir"] = str(folder)
    save_settings(s)
    return folder


def mc_version_str(game_dir: Path):
    for nm in ("appxmanifest.xml", "AppxManifest.xml"):
        man = game_dir / nm
        if man.exists():
            m = re.search(r'Identity[^>]*Version="(\d+)\.(\d+)\.(\d+)\.\d+"',
                          man.read_text(errors="ignore"))
            if m:
                p = m.group(3)
                return f"{m.group(1)}.{m.group(2)}.{int(p[:2]) if len(p)>=2 else int(p)}"
    return None


def _vt(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def _auto_mc_version(s):
    vs = list_mc_versions(False) or list_mc_versions(True)
    if not vs:
        die("No Minecraft version available (check your network).")
    want = (s.get("mc_version") or "").strip()
    return next((v for v in vs if v["tag"] == want
                 or v["tag"].startswith(want + ".")), vs[0]) if want else vs[0]
