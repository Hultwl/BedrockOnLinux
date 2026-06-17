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
- builds and runs **GDK-Proton** from a **WineGDK** fork that implements
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
sudo apt install ./bedrock-on-linux_*_all.deb
```

**Any distro** — AppImage

```bash
chmod +x BedrockOnLinux-*-x86_64.AppImage && ./BedrockOnLinux-*-x86_64.AppImage
```

**Portable** — single-file `.pyz` (any distro with Python 3)

```bash
chmod +x bedrock-on-linux-*.pyz && ./bedrock-on-linux-*.pyz gui
```

**Flatpak**

```bash
flatpak install --user ./BedrockOnLinux-*-x86_64.flatpak
flatpak run io.github.wyze3306.BedrockOnLinux
```

> Build it yourself with `scripts/build-flatpak.sh` (see
> [`flatpak/README.md`](flatpak/README.md)).

> Needs: `python3`, `python3-tk`, `tar`, `zstd`, and Python `cryptography`
> (for Microsoft sign-in). The `.deb` and Flatpak pull these in; on the
> AppImage/`.pyz` the launcher auto-installs `cryptography` on first login (or
> run `pip install --user cryptography`). `bedrock-on-linux doctor` reports
> anything missing.

## Play

1. Open **BedrockOnLinux**.
2. Top-right **Sign in** — open the shown link, enter the code, and sign in
   with the account that owns Minecraft.
3. Pick a **version** (bottom-left), then hit **▶ PLAY**.
4. In game: **Play ▸ Servers** (or *Discover*) and join.

The first **PLAY** downloads the version and the engine (once); after that it
just starts. Everything else is handled for you — **no build tools needed**.

## The engine (first run)

The game runs on a WineGDK-based GDK-Proton ("the engine"). On first launch
the launcher **downloads a prebuilt engine** from the releases and unpacks it —
just like the game itself. You do **not** need a compiler or any `-dev`
packages.

Only when no prebuilt has been published for the current engine revision does
the launcher fall back to building Wine from source (a long build that needs
the mingw toolchain) — a path meant for developers iterating on the fork.

**Maintainers — publishing a prebuilt engine:** build it once
(`bedrock-on-linux setup --force`), then package and upload:

```bash
scripts/package-engine.sh            # → dist/GDK-Proton-xuser-<rev>.tar.gz
gh release upload v1.0.0 dist/GDK-Proton-xuser-*.tar.gz --clobber
```

The launcher finds the asset by name (`GDK-Proton-xuser-<rev>.tar.gz`) across
the app's releases, so it can hang off any tag. Bump `WINEGDK_BUILD_REV` in
`bol/config.py` whenever the engine changes, then publish a fresh asset.

## Command line

```bash
bedrock-on-linux              # open the launcher (same as 'gui')
bedrock-on-linux versions     # list available Minecraft versions
bedrock-on-linux setup --mc 1.26.21.1   # download + prepare a version
bedrock-on-linux login        # sign in to a Microsoft account
bedrock-on-linux play         # launch
bedrock-on-linux repair       # reset a broken Wine prefix
bedrock-on-linux doctor       # check host requirements
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
```

The launcher is a small Python package, [`bol/`](bol/) — one module per
concern (`config`, `auth`, `prefix`, `fixups`, `launch`, `gui`, …) behind the
thin `bedrock-on-linux` entry point. The portable artifact is that package
zipped into a single executable `.pyz`; the `.deb`/Flatpak/AppImage ship the
package alongside the entry point.

## License

MIT — see [`LICENSE`](LICENSE).
