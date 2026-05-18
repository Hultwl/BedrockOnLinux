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
ProxyPass — the game then joins servers itself (real online play). It only
works on a GDK-Proton build that includes the WineGDK `XUser` implementation
(upstream WIP); otherwise keep the default ProxyPass path. Opt in:

```bash
bedrock-on-linux config --native-login on
bedrock-on-linux login          # link your Microsoft account
bedrock-on-linux play           # then join your server in-game (Play ▸ Servers)
```

In the GUI it's the *"In-game login — no ProxyPass"* checkbox in card ④.
Default behaviour is unchanged.

> **Status (2026-05-18):** no public GDK-Proton ships WineGDK `XUser` yet,
> so on the stock build the game shows *"Authentication failed (0x80004001)"*.
> Until an XUser-capable engine exists, use ProxyPass. To point the launcher
> at a self-built engine: `config --proton-dir <dir>` / `--proton-url <url>`
> (`--proton-auto` reverts). Design: [`docs/native-login.md`](docs/native-login.md);
> building the engine: [`docs/build-xuser-engine.md`](docs/build-xuser-engine.md).

## If something fails

On exit the app prints a likely cause. Use **🗎 Open logs**
(`~/.local/share/bedrock-on-linux/logs/`) or **🔌 ProxyPass logs** for the
live relay log. **🛠 Repair** rebuilds a broken Wine prefix.

## Command line

```bash
bedrock-on-linux versions
bedrock-on-linux setup --mc 1.26.21.1
bedrock-on-linux config --server play.linesia.net:19132
bedrock-on-linux config --native-login on   # experimental, see above
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
