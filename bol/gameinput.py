"""bol.gameinput — Microsoft GameInput redistributable install (MSI/CAB extraction)."""
# SPDX-License-Identifier: MIT

import struct
import subprocess
import time
import zlib
from pathlib import Path

from .config import CACHE, LOGS
from .log import info, ok, warn
from .prefix import kill_prefix_procs, proton_umu_cmd

def gameinput_redist_ok(prefix: Path):
    """True when the NATIVE Microsoft GameInput redist is fully installed.
    Testing system32/gameinput.dll proves nothing: wineboot pre-seeds every
    fresh prefix with the Wine BUILTIN gameinput.dll, whose mouse/controller
    readers need HID devices winebus never exposes — that builtin taking over
    is exactly the "keyboard works but mouse is dead in-game" bug. The game
    loads GameInputRedist.dll directly (it exports GameInputCreate) via the
    RedistDir registry, bypassing the builtin, only when this tree exists."""
    return ((prefix / "drive_c/Program Files/Microsoft GameInput/x64"
                      "/GameInputRedist.dll").exists()
            and (prefix / "drive_c/Program Files/Microsoft GameInput/x64"
                          "/GameInputRedistService.exe").exists())


def _msi_embedded_cab(msi: bytes):
    """Return the embedded MSZip CAB bytes from an MSI, parsing the OLE
    compound-file container in pure Python (no msiexec, no host tools). The
    CAB is stored as a stream scattered across OLE sectors — not contiguous —
    so we must walk the FAT chains. Returns the CAB bytes, or None."""
    if msi[:8] != bytes.fromhex("d0cf11e0a1b11ae1"):
        return None
    u = struct.unpack_from
    ssz = 1 << u("<H", msi, 0x1e)[0]
    mssz = 1 << u("<H", msi, 0x20)[0]
    dir0 = u("<I", msi, 0x30)[0]
    minicut = u("<I", msi, 0x38)[0]
    minifat0 = u("<I", msi, 0x3c)[0]
    difat0, ndifat = u("<I", msi, 0x44)[0], u("<I", msi, 0x48)[0]
    FREE, ENDC = 0xFFFFFFFF, 0xFFFFFFFE
    sect = lambda n: msi[(n + 1) * ssz:(n + 2) * ssz]
    difat = list(u("<109I", msi, 0x4c))
    nxt = difat0
    for _ in range(ndifat):
        if nxt in (FREE, ENDC):
            break
        vals = list(u("<%dI" % (ssz // 4), sect(nxt), 0))
        difat += vals[:-1]
        nxt = vals[-1]
    fat = []
    for fs in (d for d in difat if d != FREE):
        fat += list(u("<%dI" % (ssz // 4), sect(fs), 0))

    def chain(start):
        out, n, seen = [], start, set()
        while n not in (ENDC, FREE) and n < len(fat) and n not in seen:
            seen.add(n)
            out.append(n)
            n = fat[n]
        return out

    rbig = lambda s, sz: b"".join(sect(n) for n in chain(s))[:sz]
    dird = rbig(dir0, len(chain(dir0)) * ssz)
    ents = []
    for i in range(0, len(dird), 128):
        e = dird[i:i + 128]
        if len(e) < 128:
            break
        if u("<H", e, 64)[0]:
            ents.append((e[66], u("<I", e, 116)[0], u("<Q", e, 120)[0]))
    root = next((e for e in ents if e[0] == 5), None)
    if not root:
        return None
    ministream = rbig(root[1], root[2])
    mfat = []
    for ms in chain(minifat0):
        mfat += list(u("<%dI" % (ssz // 4), sect(ms), 0))

    def rmini(s, sz):
        out, n, seen = b"", s, set()
        while n not in (ENDC, FREE) and n < len(mfat) and n not in seen:
            seen.add(n)
            out += ministream[n * mssz:(n + 1) * mssz]
            n = mfat[n]
        return out[:sz]

    for typ, start, size in ents:
        if typ != 2 or size < 4:
            continue
        head = rbig(start, size) if size >= minicut else rmini(start, size)
        if head[:4] == b"MSCF":
            return head
    return None


def _cab_payload(cab: bytes):
    """Decompress an MSZip CAB. Returns [(uncompressed_size, bytes), …]."""
    if not cab or cab[:4] != b"MSCF":
        return []
    u = struct.unpack_from
    coff_files = u("<I", cab, 16)[0]
    cfolders, cfiles, flags = u("<HHH", cab, 26)
    o, cb_folder, cb_data = 36, 0, 0
    if flags & 4:                       # per-CFDATA/CFFOLDER reserved areas
        cb_header, cb_folder, cb_data = u("<HBB", cab, o)
        o += 4 + cb_header
    folders = []
    for _ in range(cfolders):
        coff, ndata, _t = u("<IHH", cab, o)
        o += 8 + cb_folder
        folders.append((coff, ndata))
    files, p = [], coff_files
    for _ in range(cfiles):
        cb, uoff, ifol = u("<IIH", cab, p)[0], u("<IIH", cab, p)[1], u("<IIH", cab, p)[2]
        p += 16
        p = cab.index(b"\x00", p) + 1   # skip the NUL-terminated name
        files.append((cb, uoff, ifol))
    fdata = []
    for coff, ndata in folders:
        q, out, prev = coff, b"", b""
        for _ in range(ndata):
            cb_d = u("<IHH", cab, q)[1]
            q += 8 + cb_data
            blk = cab[q:q + cb_d]
            q += cb_d
            if blk[:2] != b"CK":        # not MSZip — give up, caller falls back
                return []
            d = zlib.decompressobj(-15, zdict=prev[-32768:] if prev else b"")
            out += d.decompress(blk[2:]) + d.flush()
            prev = out
        fdata.append(out)
    return [(cb, fdata[ifol][uoff:uoff + cb]) for cb, uoff, ifol in files]


def _pe_kind(data: bytes):
    """'dll' / 'exe' for a PE image, else None (e.g. the redist's .cat)."""
    if data[:2] != b"MZ" or len(data) < 0x40:
        return None
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        return None
    return "dll" if struct.unpack_from("<H", data, pe + 22)[0] & 0x2000 else "exe"


def _extract_gameinput_redist(msi_path: Path, prefix: Path):
    """Install the GameInput redist by EXTRACTING the MSI's CAB ourselves and
    placing the files + registry — no Windows Installer, so the RtlGenRandom
    custom-action hang that stalls msiexec on some hosts can't happen. Files
    are identified structurally (PE dll/exe + size rank), which matches the
    redist's stable shape; the MSI's own OriginalFilename fields are unreliable
    (GameInputBridge reports itself as GameInputRedist). Returns True on
    success, False to let the caller fall back to running the MSI."""
    cab = _msi_embedded_cab(msi_path.read_bytes())
    pes = [(len(d), k, d) for sz, d in _cab_payload(cab)
           for k in [_pe_kind(d)] if k]
    dlls = sorted([d for sz, k, d in pes if k == "dll"], key=len, reverse=True)
    exes = sorted([d for sz, k, d in pes if k == "exe"], key=len, reverse=True)
    if not dlls or not exes:            # unrecognised payload → MSI fallback
        return False
    x64 = prefix / "drive_c/Program Files/Microsoft GameInput/x64"
    x86 = prefix / "drive_c/Program Files/Microsoft GameInput/x86"
    sys32 = prefix / "drive_c/windows/system32"
    x64.mkdir(parents=True, exist_ok=True)
    sys32.mkdir(parents=True, exist_ok=True)   # may be absent on a fresh prefix
    # Largest dll = GameInputRedist.dll (exports GameInputCreate); next =
    # GameInputBridge.dll; smallest = the x86 build. Largest exe = the
    # service; next = the raw-input proxy.
    (x64 / "GameInputRedist.dll").write_bytes(dlls[0])
    (sys32 / "GameInputRedist.dll").write_bytes(dlls[0])
    (x64 / "GameInputRedistService.exe").write_bytes(exes[0])
    if len(dlls) >= 2:
        (x64 / "GameInputBridge.dll").write_bytes(dlls[1])
    if len(exes) >= 2:
        (x64 / "GameInputRawInputProxy.exe").write_bytes(exes[1])
    if len(dlls) >= 3:
        x86.mkdir(parents=True, exist_ok=True)
        (x86 / "GameInputRedist.dll").write_bytes(dlls[2])
    return gameinput_redist_ok(prefix)


def _set_gameinput_registry(prefix: Path):
    """Point the game's GameInput loader at the extracted redist: RedistDir
    (both registry views) + the demand-start service entry, matching what the
    MSI writes. Imported in one umu/reg pass."""
    reg = (
        "Windows Registry Editor Version 5.00\r\n\r\n"
        r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\GameInput]" "\r\n"
        r'"RedistDir"="C:\\Program Files\\Microsoft GameInput\\x64"' "\r\n\r\n"
        r"[HKEY_LOCAL_MACHINE\SOFTWARE\Wow6432Node\Microsoft\GameInput]" "\r\n"
        r'"RedistDir"="C:\\Program Files\\Microsoft GameInput\\x64"' "\r\n\r\n"
        r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\GameInputRedistService]" "\r\n"
        r'"DisplayName"="GameInput Redist Service"' "\r\n"
        r'"Description"="GameInput Redist Service"' "\r\n"
        r'"ImagePath"="C:\\Program Files\\Microsoft GameInput\\x64\\GameInputRedistService.exe"' "\r\n"
        r'"ObjectName"="LocalSystem"' "\r\n"
        r'"ErrorControl"=dword:00000000' "\r\n"
        r'"Start"=dword:00000003' "\r\n"
        r'"Type"=dword:00000010' "\r\n"
    )
    rf = CACHE / "gameinput.reg"
    CACHE.mkdir(parents=True, exist_ok=True)
    rf.write_text(reg, encoding="utf-16")        # UTF-16 + BOM (Wine needs it)
    cmd, env = proton_umu_cmd("reg", prefix=prefix)
    cmd += ["import", "Z:" + str(rf).replace("/", "\\")]
    try:
        subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=120)
    except Exception as e:
        warn(f"GameInput RedistDir registry import failed ({e}).")


def install_gameinput(prefix: Path, game_dir: Path):
    """Install the NATIVE Microsoft GameInput redist into the prefix. Heals
    prefixes from older releases (≤ 1.0.9) that fell back to Wine's builtin
    GameInput (no mouse) because the redist never actually installed.

    Primary path EXTRACTS the redist straight from the game's
    Installers/GameInputRedist.msi (pure-Python OLE+CAB) and writes the
    registry — this avoids running Windows Installer entirely, whose post-copy
    RtlGenRandom custom action hangs msiexec for minutes on some hosts. Only if
    extraction can't recognise the payload do we fall back to running the MSI
    (poll for the artifacts, then kill — never wait for the hang)."""
    if gameinput_redist_ok(prefix):
        return
    msi = game_dir / "Installers" / "GameInputRedist.msi"
    if not msi.exists():
        warn("GameInputRedist.msi missing from the game package — native "
             "GameInput not installed; the in-game mouse and controller "
             "will not work (Wine's builtin GameInput has no mouse backend).")
        return
    info("Installing Microsoft GameInput (native redist — in-game mouse) …")
    try:
        if _extract_gameinput_redist(msi, prefix):
            _set_gameinput_registry(prefix)
            ok("Microsoft GameInput installed (native redist)")
            return
    except Exception as e:
        warn(f"GameInput direct extraction failed ({e}) — trying the MSI.")
    _install_gameinput_via_msi(prefix, msi)
    if gameinput_redist_ok(prefix):
        _set_gameinput_registry(prefix)
        ok("Microsoft GameInput installed (native redist)")
    else:
        warn("GameInput install incomplete — the in-game mouse may not work; "
             "re-run Play or 'Install / Update' to retry.")


def _install_gameinput_via_msi(prefix: Path, msi: Path):
    """Fallback: run GameInputRedist.msi under umu, but never wait for it to
    finish — its final RtlGenRandom action hangs msiexec indefinitely on some
    hosts. Poll for the redist artifacts (they are written early) and kill the
    install the moment they appear, scoped to this prefix."""
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / "native-login.log", "a")
    cmd, env = proton_umu_cmd("msiexec", prefix=prefix)
    env["WINEDEBUG"] = "-all"
    overrides = ["cryptbase=n,b"]
    if env.get("WINEDLLOVERRIDES"):
        overrides.append(env["WINEDLLOVERRIDES"])
    env["WINEDLLOVERRIDES"] = ";".join(overrides)
    cmd += ["/i", "Z:" + str(msi).replace("/", "\\"), "/qn"]
    proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    end = time.time() + 120
    try:
        while time.time() < end:
            if proc.poll() is not None:
                break
            if gameinput_redist_ok(prefix):
                time.sleep(2)          # let the last writes flush
                break
            time.sleep(2)
    finally:
        log.close()
        if proc.poll() is None:
            kill_prefix_procs(prefix)
            try:
                proc.wait(10)
            except Exception:
                proc.kill()
        else:
            kill_prefix_procs(prefix)
