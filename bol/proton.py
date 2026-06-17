"""bol.proton — GDK-Proton acquisition and patching."""
# SPDX-License-Identifier: MIT

import shutil
import struct
import tarfile
from pathlib import Path

from .config import CACHE, GDK_PROTON_REPO, PROTON_DIR
from .log import die, info, ok, warn
from .pe import PE, _backup_once, apply_patch
from .util import (
    asset_url,
    download,
    gh_latest,
    gh_releases,
    load_settings,
    save_settings,
)

def proton_path():
    p = load_settings().get("proton")
    return Path(p) if p else None


def custom_proton():
    """A user-supplied GDK-Proton (e.g. a fork built with WineGDK XUser).
    When set, our combase/ntdll offsets may not match — patch non-strict."""
    s = load_settings()
    return bool(s.get("proton_dir") or s.get("proton_url"))


def ensure_proton(tag=None, force=False, progress=None):
    s = load_settings()
    cur = proton_path()

    # (A) User-supplied build directory — a fork built with WineGDK XUser,
    #     etc. Used verbatim; never downloaded or auto-updated.
    pdir = s.get("proton_dir")
    if pdir:
        root = Path(pdir).expanduser()
        if not (root / "proton").exists():
            die(f"proton_dir has no 'proton' executable: {root}")
        s["proton"], s["proton_tag"] = str(root), "custom-dir"
        save_settings(s)
        ok(f"GDK-Proton (custom dir): {root}")
        patch_proton(root, strict=False)
        return root

    # (B) User-supplied archive URL.
    purl = s.get("proton_url")
    if purl:
        want = "custom-url:" + purl
        if cur and cur.exists() and not force and s.get("proton_tag") == want:
            info("GDK-Proton (custom URL) already installed")
            return cur
        fname = purl.rsplit("/", 1)[-1] or "gdk-proton-custom.tar.gz"
        tar = CACHE / ("custom-" + fname)
        if not tar.exists() or force:
            info("Downloading custom GDK-Proton …")
            download(purl, tar, "GDK-Proton (custom)", progress)
        info("Extracting custom GDK-Proton …")
        for d in PROTON_DIR.iterdir() if PROTON_DIR.exists() else []:
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
        with tarfile.open(tar) as t:
            t.extractall(PROTON_DIR)
        root = next((p for p in sorted(PROTON_DIR.glob("*"))
                     if (p / "proton").exists()), None)
        if not root:
            die("Invalid custom GDK-Proton archive (no 'proton' inside).")
        s["proton"], s["proton_tag"] = str(root), want
        save_settings(s)
        ok(f"GDK-Proton (custom URL) ready: {root}")
        patch_proton(root, strict=False)
        return root

    # (C) Default: Weather-OS/GDK-Proton releases.
    if cur and cur.exists() and not force and (not tag or s.get("proton_tag") == tag):
        return cur
    rel = (next((r for r in gh_releases(GDK_PROTON_REPO, 20)
                 if r["tag_name"] == tag), None) if tag else gh_latest(GDK_PROTON_REPO))
    if not rel:
        die(f"GDK-Proton version '{tag}' not found.")
    tag = rel["tag_name"]
    if cur and cur.exists() and s.get("proton_tag") == tag:
        info(f"GDK-Proton already up to date ({tag})")
        return cur
    url, fname, _ = asset_url(rel, lambda n: n.endswith(".tar.gz"))
    if not url:
        die("GDK-Proton archive not found.")
    tar = CACHE / fname
    if not tar.exists():
        info(f"Downloading GDK-Proton {tag} …")
        download(url, tar, f"GDK-Proton {tag}", progress)
    info("Extracting GDK-Proton (~1.5 GiB) …")
    for d in PROTON_DIR.glob("GDK-Proton*"):
        shutil.rmtree(d, ignore_errors=True)
    with tarfile.open(tar) as t:
        t.extractall(PROTON_DIR)
    root = next(PROTON_DIR.glob("GDK-Proton*"))
    if not (root / "proton").exists():
        die("Invalid GDK-Proton archive.")
    s["proton"], s["proton_tag"] = str(root), tag
    save_settings(s)
    ok(f"GDK-Proton {tag} ready")
    patch_proton(root)
    return root


def patch_proton(root: Path, strict=True):
    """Two binary patches that let Bedrock GDK 1.26 run under Wine.
    Idempotent; offsets found structurally; backups as *.bol-orig.
    strict=False (custom builds): a mismatch warns instead of aborting —
    a fork may already handle this or use a different Wine."""
    def fail(m):
        if strict:
            die(m)
        warn(m + " (custom build — continuing)")

    wine = root / "files/lib/wine/x86_64-windows"
    combase, ntdll = wine / "combase.dll", wine / "ntdll.dll"
    if not combase.exists() or not ntdll.exists():
        return fail(f"Wine DLLs missing in {wine}")

    # (1) combase.RoOriginateErrorW stub aborts at the package-identity check.
    off = PE(combase).export_off("RoOriginateErrorW")
    if off is None:
        return fail("RoOriginateErrorW not found in combase.dll")
    # The prologue varies by Wine build (4883ec28 / 4883ec48 / …), but the
    # entry offset is resolved from the export table, so stub it regardless:
    # plant `xor eax,eax; ret` so RoOriginateErrorW always returns S_OK.
    apply_patch(combase, off, bytes.fromhex("4883ec28"),
                bytes.fromhex("31c0c3") + b"\x90" * 21,
                "combase.RoOriginateErrorW", strict=strict, relax=True)

    # (2) ntdll: neutralise every unimplemented-stub funnel (prologue + call
    #     to RtlRaiseException + EB F6 never-return loop) so unimplemented
    #     imports (NtQueryWnfStateData via GameInput) return STATUS_NOT_IMPL
    #     instead of killing the game ~10 min in.
    pe = PE(ntdll)
    rre = pe.export_rva("RtlRaiseException")
    if rre is None:
        return fail("RtlRaiseException not resolved in ntdll.dll")
    d = pe.data
    sig = bytes.fromhex("55534881ecc8000000488dac24c0000000")
    new = bytes.fromhex("b8020000c0c3") + b"\x90\x90"
    funnels, i = [], d.find(sig)
    while i >= 0:
        j = d.find(bytes.fromhex("4889d9e8"), i, i + 0x90)
        if j >= 0:
            cf = j + 3
            rel = struct.unpack_from("<i", d, cf + 1)[0]
            if pe.off2rva(cf) + 5 + rel == rre and d[cf + 5:cf + 7] == b"\xeb\xf6":
                funnels.append(i)
        i = d.find(sig, i + 1)
    if funnels:
        raw = bytearray(d)
        for o in funnels:
            raw[o:o + len(new)] = new
        _backup_once(ntdll)
        ntdll.write_bytes(raw)
        ok(f"ntdll: {len(funnels)} stub(s) neutralised")
    elif d.count(new + bytes.fromhex("00488dac24c0000000")):
        info("ntdll: already patched")
    else:
        fail("ntdll: no stub found — Proton layout changed.")
