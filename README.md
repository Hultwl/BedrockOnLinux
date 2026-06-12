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

**Portable** — tarball

```bash
tar xzf bedrock-on-linux-*-portable.tar.gz && cd bedrock-on-linux
./bedrock-on-linux gui
```

**Flatpak**

```bash
flatpak install --user ./BedrockOnLinux-*-x86_64.flatpak
flatpak run io.github.wyze3306.BedrockOnLinux
```

> Build: `scripts/build-flatpak.sh`. The manifest is Flathub-ready — see
> [`flatpak/README.md`](flatpak/README.md) for testing and the submission steps.

> Needs (`.deb`/AppImage/portable): `python3`, `python3-tk`, `tar`, `zstd`.
> `bedrock-on-linux doctor` reports anything missing.

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
`bedrock-on-linux` whenever the engine changes, then publish a fresh asset.

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

**Mouse (and controller) dead in-game, keyboard fine?** Fixed in v1.0.11 —
older releases never actually installed Microsoft's native GameInput redist
into the Wine prefix (the check matched a pre-seeded Wine builtin DLL that has
no mouse backend), on X11 and Wayland alike. Just update and press **Play**:
the launcher detects the broken prefix and installs the redist automatically,
one time. It extracts the redist straight from the game package, so it can't
stall the way the Windows installer does on some machines. gamescope is no
longer needed for this; wrap the game in it only if you want to, with
`BOL_GAMESCOPE=1` or `BOL_GAMESCOPE="-f -W 2560 -H 1440"`.

## Legal

BedrockOnLinux ships **no Minecraft files** — it is a compatibility launcher.
Game files come from a source you choose (default: the community archive
[`bubbles-wow/mcbe-gdk-unpack-archive`](https://github.com/bubbles-wow/mcbe-gdk-unpack-archive))
or your own folder; **you must own Minecraft**. GDK-Proton and WineGDK are
free software under their own licenses. Realms is not supported.

## Build

```bash
scripts/build-release.sh        # .deb + AppImage + portable tarball → dist/
scripts/build-flatpak.sh        # Flatpak bundle → dist/ (needs flatpak-builder)
```

## License

MIT — see [`LICENSE`](LICENSE).
