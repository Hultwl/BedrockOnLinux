<div align="center">

# 🟩 BedrockOnLinux

**Minecraft Bedrock (Windows / GDK edition) on Linux, with native in-game
Microsoft sign-in and multiplayer. Install it, pick a version, play.**

`Ubuntu` · `Debian` · `Linux Mint / LMDE` · `Fedora` · `Arch` · `openSUSE`

![BedrockOnLinux](screenshot.png)

</div>

---

## What it does

One app, everything automatic:

- downloads the Minecraft version you pick;
- downloads and runs a reviewed **GDK-Proton** engine built from a **WineGDK**
  fork that implements
  `XUser` + request signing, so you sign in to **Microsoft inside the game**
  — no relay, no proxy;
- applies the binary patches the game needs to start and to join online
  Bedrock servers;
- fixes curl/SSL and `options.txt`, then launches the game.

You then play like on any platform: sign in, open **Play ▸ Servers**, and
join native Bedrock servers (Hive, CubeCraft, …) or crossplay/Geyser servers.

## Install

**Debian / Ubuntu / Mint** — `.deb`

```bash
sudo apt install ./bedrock-on-linux_*_amd64.deb
```

**Current x86-64 desktop distros** — AppImage (glibc 2.31+ baseline)

```bash
chmod +x BedrockOnLinux-*-x86_64.AppImage && ./BedrockOnLinux-*-x86_64.AppImage
```

**Portable** — single-file `.pyz` (any x86-64 distro with Python 3.9+)

```bash
chmod +x bedrock-on-linux-*.pyz && ./bedrock-on-linux-*.pyz gui
```

The installed `.deb` and Flatpak appear in the application menu and launch
normally with one click. A downloaded AppImage or `.pyz` may lose its
executable bit; run the matching `chmod +x` command above once, or enable
“Allow executing file as program” in the file manager, before double-clicking.
AppImage also needs FUSE; on a system without it, use:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./BedrockOnLinux-*-x86_64.AppImage
```

The supported target is an x86-64 glibc desktop with X11 or XWayland. The
AppImage bundles Python, Tk, `cryptography`, and CA certificates, but still
uses the host's common X11/Xft/fontconfig libraries and graphics driver. ARM,
musl-only distributions (such as stock Alpine), pure Wayland without XWayland,
and GPUs which do not meet the Vulkan requirements below are not supported.

The game path needs a Vulkan-capable GPU/driver exposing either
`VK_EXT_device_generated_commands` or the older NVIDIA
`VK_NV_device_generated_commands`. The managed 1.3 engine contains both paths,
requires Vulkan 1.3, and honours explicit vkd3d overrides
(`VKD3D_VULKAN_DEVICE` and `VKD3D_FILTER_DEVICE_NAME`). The launcher never
opens Vulkan to guess an adapter: the universal DLL validates the real device
and selects EXT/NV inside the one game process. This matters on broken kernel
drivers, where a supposedly harmless launcher-side Vulkan probe can itself
freeze the whole machine.

**Flatpak**

```bash
flatpak install --user ./BedrockOnLinux-*-x86_64.flatpak
flatpak run io.github.wyze3306.BedrockOnLinux
```

> Build it yourself with `scripts/build-flatpak.sh` (see
> [`flatpak/README.md`](flatpak/README.md)).

> The `.deb` and Flatpak declare their runtime dependencies. The AppImage
> bundles its Python GUI and authentication stack. The `.pyz` uses the host's
> Python 3.9+, Tk, archive tools, and installs Python `cryptography` on first
> login when needed. `bedrock-on-linux doctor` reports anything missing.

## Play

1. Open **BedrockOnLinux**.
2. Top-right **Sign in** — open the shown link, enter the code, and sign in
   with the account that owns Minecraft.
3. Pick a **version** (bottom-left), then hit **▶ PLAY**.
4. In game: **Play ▸ Servers** (or *Discover*) and join.

The first **PLAY** downloads the version and the engine (once); after that it
just starts. Everything else is handled for you — **no build tools needed**.

Before starting any Wine or Vulkan process, 1.3 performs a GPU-safe preflight
using only the existing display server and text system logs. A degraded X11
session with zero hardware providers, FBDEV/llvmpipe fallback, or a fatal GPU
kernel fault is refused with an actionable message. Run
`bedrock-on-linux doctor` after repairing the host driver and rebooting. The
advanced `BOL_ALLOW_UNSAFE_GPU=1` bypass exists for false positives, but can
re-expose a kernel hard-lock and is not a normal compatibility setting.

Microsoft/Xbox server access is enabled by default. When a guarded engine is
upgraded, the launcher retries online access once instead of silently keeping
an old compatibility toggle disabled. For emergency troubleshooting only,
`BOL_DISABLE_SERVER_PATCHES=1 bedrock-on-linux play` disables the memory
patches for that single launch without changing the saved preference.

## The engine (first run)

The game runs on a WineGDK-based GDK-Proton ("the engine"). On first launch
the launcher **downloads a prebuilt engine** from the releases and unpacks it —
just like the game itself. You do **not** need a compiler or any `-dev`
packages.

The 1.3 engine contains one reviewed vkd3d-proton 3.0.1 compatibility build
with both DGC implementations. vkd3d uses
`VK_EXT_device_generated_commands` when the selected GPU and driver support
it, and falls back internally to the restored
`VK_NV_device_generated_commands` path on older NVIDIA drivers. The launcher
also enables the raw-VA root-CBV mode required by Minecraft's indirect menu
commands. Together these changes prevent the live-game process from freezing
in the menu while audio keeps playing (#27, #29, #30).

On an existing prefix, PLAY starts no Wine helper before Minecraft. Microsoft,
Xbox, TLS, and GameInput registry values are written directly to the stopped
prefix under a lock, atomically and with private permissions; this replaces the
old sequence of `umu reg` processes which unnecessarily started Explorer and
the graphics stack. A brand-new prefix still needs one headless `wineboot`,
with Vulkan/D3D/display drivers disabled for that setup-only step. A second
PLAY is refused while the prefix is active, and automatic repair/relaunch loops
are disabled: recovery is always an explicit user action.

Managed installs accept only the exact prebuilt archive hash carried by the
launcher. If that candidate is unavailable or invalid, an existing engine is
kept and a first install stops with an actionable error; it never substitutes
an unreproducible source build.

**Maintainers — building a prebuilt engine candidate:** build the pinned
WineGDK source on the Debian 11/glibc 2.31 baseline, combine that prefix with a
clean GDK-Proton base and the reviewed vkd3d 3.0.1 universal DGC compatibility
build, then package it:

```bash
scripts/build-winegdk-bullseye.sh /path/to/empty-workdir /path/to/WineGDK
scripts/package-engine.sh \
  /path/to/staged/GDK-Proton-xuser \
  /path/to/vkd3d-proton-3.0.1-universal-dgc \
  670eda2864dcb22d11c7f2c28973214d4755ad2f \
  /path/to/GDK-Proton10-32.tar.gz
scripts/run-candidate.sh gui         # force-installs that exact archive, then runs
```

The Wine build script uses an unprivileged Bullseye chroot and rejects every
ELF that imports a symbol newer than `GLIBC_2.31`. The second argument to
`package-engine.sh` is a staging tree containing the
reviewed universal EXT+NV DGC DLLs for both Windows architectures. It validates
the 3.0.1 payload and restores the exact hash-pinned native XThreading delegate
from Weather-OS GDK-Proton 10-32 (required by WineGDK for XAsync/XTaskQueue).
It writes a hash-pinned `engine-manifest.json` before
creating a deterministic archive. Pin the printed archive SHA-256 in
`bol/config.py`; the launcher verifies both that archive and its manifest before
it replaces a working engine.

The launcher finds the asset by name (`GDK-Proton-xuser-<rev>.tar.gz`) across
the app's releases. Bump `WINEGDK_BUILD_REV` in `bol/config.py` whenever the
engine contents or packaging changes, then build and test a fresh asset before
publishing it.

## Command line

```bash
bedrock-on-linux              # open the launcher (same as 'gui')
bedrock-on-linux versions     # list available Minecraft versions
bedrock-on-linux setup --mc 1.26.21.1   # download + prepare a version
bedrock-on-linux login        # sign in to a Microsoft account
bedrock-on-linux play         # launch
bedrock-on-linux repair       # reset a broken Wine prefix
bedrock-on-linux doctor       # check host requirements
bedrock-on-linux doctor --acknowledge-gpu-crash  # after driver repair + reboot
bedrock-on-linux update       # check for and install a launcher update
```

The launcher also checks for updates on its own: when a newer version is
released, a banner appears at the top of the window with an **Update now**
button (one click downloads and installs it, then offers to restart). Git
checkouts are left alone — `git pull` there — and packaged installs (`.deb`,
Flatpak) point you at your package manager instead.

## If something fails

Use **⚙ Settings ▸ Open logs folder**
(`~/.local/share/bedrock-on-linux/logs/`), or **⚙ Settings ▸ Repair** to
rebuild a broken Wine prefix. The live step-by-step log is also under
**Details** in the launcher.

If the whole desktop freezes or the machine needs the physical power button,
do not retry. After reboot, run `bedrock-on-linux doctor`. The launcher checks
the current and previous kernel boots without opening Vulkan/OpenGL and keeps a
durable marker for a Minecraft session interrupted by a power loss. A report
such as “zero RandR GPU providers”, “FBDEV/software rendering”, “fatal kernel
fault”, or “previous session did not return cleanly” means the host
Mesa/NVIDIA/AMD/Intel driver installation must be fixed before Minecraft can be
tested safely; resetting Wine cannot repair a kernel graphics driver.

After repairing/updating the driver and rebooting, run
`bedrock-on-linux doctor --acknowledge-gpu-crash`. This clears only the old
interrupted-session/previous-boot block; a current kernel fault or an unsafe
X11 RandR state remains blocked. On X11, install the distribution package that
provides `xrandr` if Doctor cannot verify a hardware provider. Wayland and
sandboxed Flatpak sessions cannot always expose the system journal, so a first
unknown driver failure cannot be predicted; the durable marker prevents a
blind second attempt.

## Legal

BedrockOnLinux ships **no Minecraft files** — it is a compatibility launcher.
Game files come from a source you choose (default: the community archive
[`bubbles-wow/mcbe-gdk-unpack-archive`](https://github.com/bubbles-wow/mcbe-gdk-unpack-archive))
or your own folder; **you must own Minecraft**. GDK-Proton and WineGDK are
free software under their own licenses. Realms is not supported.

## Build

```bash
scripts/build-release.sh        # .deb + AppImage + portable .pyz → dist/
scripts/build-flatpak.sh        # Flatpak bundle → dist/ (needs flatpak-builder)
scripts/run-candidate.sh gui    # run the local candidate; never publishes
```

For an **unreleased local candidate**, keep
`GDK-Proton-xuser-<rev>.tar.gz` in the same `dist/` directory as the AppImage
or `.pyz`. The launcher detects that exact sibling archive and installs it
before Wine can start; moving only the application file would instead require
the matching engine asset to already exist online. `scripts/run-candidate.sh`
is the safest checkout-level smoke-test because it refuses to fall back to an
older installed engine.

The launcher is a small Python package, [`bol/`](bol/) — one module per
concern (`config`, `auth`, `prefix`, `fixups`, `launch`, `gui`, …) behind the
thin `bedrock-on-linux` entry point. The portable artifact is that package
zipped into a single executable `.pyz`; the `.deb`/Flatpak/AppImage ship the
package alongside the entry point.

## License

MIT — see [`LICENSE`](LICENSE).
