<div align="center">

# 🟩 BedrockOnLinux

**Minecraft Bedrock (Windows / GDK edition) on Linux — multiplayer included.
Install it, pick your version, play.**

`Ubuntu` · `Debian` · `Linux Mint / LMDE` · `Fedora` · `Arch` · `openSUSE`

![BedrockOnLinux](screenshot.png)

</div>

---

## What it does

One app, everything automatic:

- downloads **GDK-Proton** and applies the **2 binary patches** without which
  the game won't start (`combase.RoOriginateErrorW` + `ntdll` stub funnels);
- runs GDK-Proton **directly** (no Steam runtime / pressure-vessel — same as
  Heroic), with a bundled **Java 25** and the right **ProxyPass** build;
- runs **ProxyPass** in the background for multiplayer (WineGDK has no in-game
  Microsoft login — ProxyPass authenticates outside Wine and bridges to your
  server, shown in Minecraft as a LAN world);
- fixes curl/SSL and `options.txt`, then launches the game.

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

> Needs: `python3`, `python3-tk`, `tar`, `zstd`.
> `bedrock-on-linux doctor` reports anything missing.

## Play

1. Open **BedrockOnLinux**.
2. **① Minecraft version** — pick one (downloaded for you).
3. **④ Microsoft account** → *Sign in*: open the shown link, enter the
   code, sign in with the account that owns Minecraft.
4. **③ Multiplayer server** — set the destination IP.
5. **Install / Update**, then **▶ PLAY**.
6. In game: **Play ▸ Worlds tab ▸ "ProxyPass"**.

## Experimental: in-game login (no ProxyPass)

This branch can sign in **inside** Minecraft instead of relaying through
ProxyPass — the game then joins servers itself (real online play). It needs
a GDK-Proton whose WineGDK implements `XUser` + request signing. The
launcher can **build that for you** from the WineGDK fork:

```bash
bedrock-on-linux setup --winegdk     # clone + build the fork, package, wire in
bedrock-on-linux login               # link your Microsoft account
bedrock-on-linux play                # join your server in-game (Play ▸ Servers)
```

`setup --winegdk` (or GUI card ② → *"⚙ build from WineGDK (login)"*, then
**Install / Update**) clones the fork, builds Wine, overlays it onto a
stock GDK-Proton, and turns on in-game login. The Wine build is **long**
and needs build tools — the launcher checks and tells you what to install
(`sudo apt build-dep wine` + `flex bison gcc-mingw-w64-x86-64 …`). Builds
are cached by source commit. Revert anytime: `config --proton-auto`
(back to ProxyPass).

Default behaviour is unchanged (ProxyPass). Other engine options:
`config --proton-dir <dir>` / `--proton-url <url>` for a build you supply.

> The signing path is the standard proof-bound user-token scheme; if Xbox
> rejects it a device/SISU token may be needed (iterate from the build/run
> loop). Design: [`docs/native-login.md`](docs/native-login.md); the engine
> build: [`docs/build-xuser-engine.md`](docs/build-xuser-engine.md).

## If something fails

On exit the app prints a likely cause. Use **🗎 Open logs**
(`~/.local/share/bedrock-on-linux/logs/`) or **🔌 ProxyPass logs** for the
live relay log. **🛠 Repair** rebuilds a broken Wine prefix.

## Command line

```bash
bedrock-on-linux versions
bedrock-on-linux setup --mc 1.26.21.1
bedrock-on-linux config --server play.linesia.net:19132
bedrock-on-linux setup --winegdk             # in-game login, see above
bedrock-on-linux play
bedrock-on-linux doctor
```

## Legal

BedrockOnLinux ships **no Minecraft files** — it is a compatibility launcher.
Game files come from a source you choose (default: the community archive
[`bubbles-wow/mcbe-gdk-unpack-archive`](https://github.com/bubbles-wow/mcbe-gdk-unpack-archive))
or your own folder; you must own Minecraft. GDK-Proton, ProxyPass and Temurin
are free software under their own licenses. Realms and the in-game native
Microsoft login are not supported (WineGDK limitation).

## Build

```bash
scripts/build-release.sh        # .deb + AppImage + portable tarball → dist/
```

## License

MIT — see [`LICENSE`](LICENSE).
