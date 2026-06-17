"""bol.winegdk — WineGDK engine sync, build and prebuilt install."""
# SPDX-License-Identifier: MIT

import os
import shutil
import subprocess
import tarfile
from pathlib import Path

from .config import (
    CACHE,
    GDK_PROTON_REPO,
    LOGS,
    PROTON_DIR,
    WINEGDK_BRANCH,
    WINEGDK_BUILD_REV,
    WINEGDK_OUT,
    WINEGDK_PREBUILT_REPO,
    WINEGDK_REPO,
    WINEGDK_SRC,
    WINE_BUILD_PKGS,
)
from .log import BolError, die, info, ok, warn
from .proton import patch_proton
from .util import (
    asset_url,
    download,
    gh_latest,
    gh_releases,
    load_settings,
    run,
    save_settings,
)

def _pm_hint():
    return next((h for pm, h in (
        ("apt-get", "sudo apt install {}"), ("dnf", "sudo dnf install {}"),
        ("pacman", "sudo pacman -S {}"), ("zypper", "sudo zypper in {}"))
        if shutil.which(pm)), "install: {}")


def _stock_proton_root(progress=None):
    """Latest Weather-OS GDK-Proton extracted to PROTON_DIR/_stock — the
    overlay base for a WineGDK build (kept apart from the active proton)."""
    base = PROTON_DIR / "_stock"
    root = next(base.glob("GDK-Proton*"), None) if base.exists() else None
    if root and (root / "proton").exists():
        return root
    rel = gh_latest(GDK_PROTON_REPO)
    url, fname, _ = asset_url(rel, lambda n: n.endswith(".tar.gz"))
    if not url:
        die("Stock GDK-Proton archive not found.")
    tar = CACHE / fname
    if not tar.exists():
        info(f"Downloading base GDK-Proton {rel['tag_name']} …")
        download(url, tar, "GDK-Proton (base)", progress)
    info("Extracting base GDK-Proton …")
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    with tarfile.open(tar) as t:
        t.extractall(base)
    root = next(base.glob("GDK-Proton*"))
    if not (root / "proton").exists():
        die("Invalid base GDK-Proton archive.")
    return root


def _winegdk_sync():
    """Clone or shallow-update the WineGDK fork; return its HEAD commit."""
    s = load_settings()
    repo = s.get("winegdk_repo") or WINEGDK_REPO
    branch = s.get("winegdk_branch") or WINEGDK_BRANCH
    if not shutil.which("git"):
        die("git is required — " + _pm_hint().format("git"))
    synced = False
    if (WINEGDK_SRC / ".git").is_dir():
        info(f"Updating WineGDK ({branch}) …")
        # The configured repo/branch can change (pivot) — point origin at
        # it before fetching.
        subprocess.run(["git", "-C", str(WINEGDK_SRC), "remote", "set-url",
                        "origin", repo], capture_output=True)
        if subprocess.run(["git", "-C", str(WINEGDK_SRC), "fetch",
                           "--depth=1", "origin", branch],
                          capture_output=True).returncode == 0 and \
           subprocess.run(["git", "-C", str(WINEGDK_SRC), "checkout", "-q",
                           "-B", branch, "FETCH_HEAD"],
                          capture_output=True).returncode == 0:
            synced = True
        else:
            warn("WineGDK source out of sync — re-cloning cleanly.")
    if not synced:
        info(f"Cloning WineGDK {repo} ({branch}) — large, one time …")
        shutil.rmtree(WINEGDK_SRC, ignore_errors=True)
        run(["git", "clone", "--depth=1", "--branch", branch, repo,
             str(WINEGDK_SRC)])
    r = subprocess.run(["git", "-C", str(WINEGDK_SRC), "rev-parse", "HEAD"],
                        capture_output=True, text=True)
    return r.stdout.strip()


def _wire_winegdk():
    """Point the launcher at the WineGDK engine (however it was produced) and
    apply the runtime patches. Shared by the prebuilt and source-build paths."""
    s = load_settings()
    s["proton"] = str(WINEGDK_OUT)
    s["proton_tag"] = "winegdk"
    s["proton_dir"] = str(WINEGDK_OUT)   # so launch/patch treat it as custom
    s["proton_source"] = "winegdk"
    s["native_login"] = True             # the whole point of this engine
    save_settings(s)
    patch_proton(WINEGDK_OUT, strict=False)
    return WINEGDK_OUT


def _install_prebuilt_winegdk(progress=None):
    """Fetch + unpack a prebuilt GDK-Proton-xuser engine so end users never
    compile a full Wine. Looks for an asset named for the current build rev on
    the app's own releases. Returns True on success, False (→ source-build
    fallback) when no matching asset is published or the archive is unusable.
    Any network/IO error degrades to False — it never breaks the build path."""
    asset = f"GDK-Proton-xuser-{WINEGDK_BUILD_REV}.tar.gz"
    try:
        rels = gh_releases(WINEGDK_PREBUILT_REPO, 30)
    except Exception as e:
        warn(f"Prebuilt engine lookup failed ({e}) — will build from source.")
        return False
    url = name = None
    for rel in rels or []:
        url, name, _ = asset_url(rel, lambda n: n == asset)
        if url:
            break
    if not url:
        return False
    tar = CACHE / name
    if not tar.exists():
        info("Downloading the game engine (prebuilt, one-time) …")
        try:
            download(url, tar, "Game engine", progress)
        except BolError:
            return False
    info("Unpacking the game engine …")
    tmp = PROTON_DIR / ".xuser-dl"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(tar) as t:
            t.extractall(tmp)
    except Exception as e:
        warn(f"Prebuilt engine archive unreadable ({e}) — building instead.")
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            tar.unlink()                 # drop the bad/partial cache copy
        except OSError:
            pass
        return False
    # Accept a tarball whose top level IS the proton tree, or one that wraps a
    # single GDK-Proton* directory.
    root = tmp if (tmp / "proton").exists() else next(
        (p for p in tmp.iterdir() if (p / "proton").exists()), None)
    if root is None:
        warn("Prebuilt engine archive has no proton tree — building instead.")
        shutil.rmtree(tmp, ignore_errors=True)
        return False
    WINEGDK_OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(WINEGDK_OUT, ignore_errors=True)
    root.replace(WINEGDK_OUT)            # same filesystem (both under PROTON_DIR)
    shutil.rmtree(tmp, ignore_errors=True)
    ok("Game engine ready (prebuilt — no compiler needed).")
    return True


def ensure_winegdk(force=False, progress=None):
    """Provide the WineGDK engine (XUser + request signing) and wire it in:
    download the prebuilt asset when published, else build the fork from
    source (long; cached by source commit)."""
    s = load_settings()
    if not force and (WINEGDK_OUT / "proton").exists() \
            and s.get("winegdk_built", "").endswith(":" + WINEGDK_BUILD_REV):
        info(f"WineGDK engine ready ({WINEGDK_BUILD_REV}).")
        return _wire_winegdk()
    # Engine present but built for a different rev → a newer engine was
    # published; auto-update it (same mechanism as the launcher's self-update).
    if (WINEGDK_OUT / "proton").exists() and s.get("winegdk_built"):
        info(f"Updating the game engine → {WINEGDK_BUILD_REV} …")
    if _install_prebuilt_winegdk(progress):     # re-fetched on --force too
        s = load_settings()
        s["winegdk_built"] = "prebuilt:" + WINEGDK_BUILD_REV
        save_settings(s)
        return _wire_winegdk()
    info("No prebuilt engine published — building from source (one-time, long).")
    commit = _winegdk_sync()
    want = commit + ":" + WINEGDK_BUILD_REV
    s = load_settings()
    if (WINEGDK_OUT / "proton").exists() and s.get("winegdk_built") == want \
            and not force:
        info(f"WineGDK build up to date ({commit[:9]})")
    else:
        need = [t for t in ("git", "gcc", "make", "flex", "bison",
                             "x86_64-w64-mingw32-gcc",
                             "i686-w64-mingw32-gcc") if not shutil.which(t)]
        if need:
            die("No prebuilt engine was available to download, so it has to "
                "be built from source — but these tools are missing: "
                + " ".join(need) + "\n"
                "  This usually means no prebuilt was published for this "
                "version yet (please report it). To build locally instead "
                "(no deb-src needed):\n  "
                + _pm_hint().format(WINE_BUILD_PKGS)
                + "\n  then re-run.")
        base = _stock_proton_root(progress)
        # Build Wine straight into a fresh copy of the stock GDK-Proton's
        # files/ so wine + wineserver + libwine come from the SAME build
        # (a partial overlay gives "wineserver version mismatch" crashes).
        info("Preparing GDK-Proton base …")
        shutil.rmtree(WINEGDK_OUT, ignore_errors=True)
        run(["cp", "-a", str(base), str(WINEGDK_OUT)])
        prefix = WINEGDK_OUT / "files"
        bdir = WINEGDK_SRC / "build-bol"
        cfg_stamp = bdir / ".bol-configured"
        logf = LOGS / "winegdk-build.log"
        LOGS.mkdir(parents=True, exist_ok=True)
        info(f"Building WineGDK — long (full Wine build); log: {logf}")
        # Incremental: the build dir is stamped with commit + build rev +
        # prefix, and only wiped when that changes (or --force) — an aborted
        # build resumes via `make`. A build-rev change means a different
        # Wine layout, so cached objects must be discarded.
        stamp_want = f"{commit}|{WINEGDK_BUILD_REV}|{prefix}"
        stamp_have = cfg_stamp.read_text().strip() if cfg_stamp.exists() else ""
        # Legacy stamp formats only match while the layout rev is unchanged.
        if stamp_have in (str(prefix), f"{commit}|{prefix}") \
                and WINEGDK_BUILD_REV == "ovl2-prefix":
            stamp_have = stamp_want
        clean = force or stamp_have != stamp_want
        if clean:
            shutil.rmtree(bdir, ignore_errors=True)
            bdir.mkdir(parents=True, exist_ok=True)
        else:
            info(f"  resuming previous build ({commit[:9]}) — incremental.")
        with open(logf, "a" if not clean else "w") as lf:
            def sh(cmd, cwd):
                lf.write("\n$ " + " ".join(cmd) + "\n")
                lf.flush()
                if subprocess.run(cmd, cwd=str(cwd), stdout=lf,
                                  stderr=subprocess.STDOUT).returncode:
                    die(f"WineGDK build failed: {' '.join(cmd[:2])} … — "
                        f"see {logf}")
            if clean:
                # --enable-archs builds the i386 PE half too — WoW64 needs it
                # to run 32-bit binaries (msiexec, installers); --enable-win64
                # alone makes any 32-bit exec die in loader_init.
                sh([str(WINEGDK_SRC / "configure"),
                    "--enable-archs=i386,x86_64",
                    "--disable-tests", f"--prefix={prefix}"], bdir)
                cfg_stamp.write_text(stamp_want)
            info("  configure done — compiling (the long part) …")
            sh(["make", f"-j{os.cpu_count() or 2}"], bdir)
            info("  compiled — installing Wine into the Proton tree …")
            sh(["make", "install"], bdir)
        # Wine 11 produces a single `wine` binary, but the Proton script
        # still calls `wine64`/`wine64-preloader` by name — left stale from
        # the base copy, those abort with "could not load ntdll.so". Symlink
        # the legacy names to the unified loader.
        bin_dir = prefix / "bin"
        if (bin_dir / "wine").is_file():
            for legacy in ("wine64", "wine64-preloader", "wine-preloader"):
                p = bin_dir / legacy
                try:
                    if p.exists() or p.is_symlink():
                        p.unlink()
                    p.symlink_to("wine")
                except OSError as e:
                    warn(f"wine binary symlink {legacy} failed: {e}")
        # Wine 11 ntdll.so needs libunwind.so.8, which the Steam Linux
        # Runtime container doesn't carry — stage the host copy into
        # files/lib/x86_64-linux-gnu (on Proton's LD_LIBRARY_PATH).
        for cand in ("/lib/x86_64-linux-gnu/libunwind.so.8.1.0",
                     "/usr/lib/x86_64-linux-gnu/libunwind.so.8.1.0",
                     "/lib/x86_64-linux-gnu/libunwind.so.8",
                     "/usr/lib/x86_64-linux-gnu/libunwind.so.8"):
            src = Path(cand)
            if src.is_file():
                real = src.resolve()
                dest_dir = prefix / "lib" / "x86_64-linux-gnu"
                dest_dir.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(real, dest_dir / real.name)
                    link = dest_dir / "libunwind.so.8"
                    if link.exists() or link.is_symlink():
                        link.unlink()
                    link.symlink_to(real.name)
                except OSError as e:
                    warn(f"libunwind staging failed: {e}")
                break
        else:
            warn("libunwind.so.8 not found on host — install libunwind8 "
                 "(or libunwind-dev) so the runtime can load ntdll.so.")
        if not any((prefix).rglob("xgameruntime.dll")):
            warn("xgameruntime.dll absent after install — build/layout off "
                 "(see logs).")
        s = load_settings()
        s["winegdk_built"] = want
        save_settings(s)
        ok(f"WineGDK GDK-Proton ready ({commit[:9]})")
    return _wire_winegdk()
