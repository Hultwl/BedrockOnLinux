# Native in-game Microsoft login (without ProxyPass)

Status: **experimental**, branch `feature/native-msa-login-no-proxypass`.
Default behaviour is unchanged — ProxyPass stays the supported path.

## Goal

Sign in to Microsoft / Xbox Live **inside** Minecraft so the game connects to
servers itself (real online play, Realms, marketplace) — instead of running
ProxyPass, which authenticates outside Wine and relays the server as a fake
LAN world.

## Why the obvious idea does not work

The blocker is **not** the SSL/CA bundle (that was the multiplayer-join bug,
fixed in v0.5.0) nor a missing sign-in window. It is that the GDK API itself
is absent under Wine:

- Minecraft (Windows GDK build) signs in through `XUserAddAsync` /
  `XUserGetTokenAndSignatureAsync`, exported by `xgameruntime.dll`.
- In `Weather-OS/WineGDK` (the GDK port GDK-Proton bundles) only the
  `System` component is implemented; `xgameruntime.spec` exports just the
  `QueryApiImpl` dispatcher. **`XUser` does not exist.**
- So the game never reaches any token cache — there is nothing to "inject".
  Seeding an XAL/token-cache file is a dead end.

Native login therefore requires an `XUser` implementation in WineGDK. That is
C/Wine work, upstream — not something this Python launcher can do alone.

## The upstream contract we target

`XUser` is being implemented upstream:

- **WineGDK PR #33 "WIP XUser"** (`olivi-r:master`, draft) adds
  `dlls/xgameruntime/GDKComponent/System/XUser.c`. It performs the Xbox Live
  (XBL/XSTS) exchange and request signing **itself**.
- It has **no login UI**. It reads an OAuth **refresh token** from the Wine
  registry:

  ```c
  RegGetValueA(HKEY_LOCAL_MACHINE, "Software\\Wine\\WineGDK",
               "RefreshToken", RRF_RT_REG_SZ, ...)
  ```

- Its hardcoded `msaAppId` is `0000000040159362` (the Bedrock **Win32**
  client_id; identical to gophertunnel's `Win32Config`). The token we mint
  must be issued for this client_id or WineGDK's refresh call rejects it.
- Flow WineGDK expects (so ours must match exactly):
  - device code — `POST https://login.live.com/oauth20_connect.srf`
    body `scope=service::user.auth.xboxlive.com::MBI_SSL&response_type=device_code&client_id=0000000040159362`
  - poll / refresh — `POST https://login.live.com/oauth20_token.srf`

Related upstream: PR #37 "XLauncher" (split from #33); issue #10 (maintainer
will not implement auth in Wine — prefers a native lib, `imLinguin/xodus`);
@ChristopherHX reported a working prototype (marketplace + public servers)
atop #33 on 2026-05-02, "months to a clean product".

## What this launcher does (and only this)

Because WineGDK does the XBL/XSTS/signature work, the launcher needs **only
the MSA device-code flow** — pure `urllib`, **no ECDSA/crypto, no Java**:

1. `POST oauth20_connect.srf` → show the user `verification_uri` + `user_code`
   (same place the ProxyPass code used to appear).
2. Poll `oauth20_token.srf` until the user finishes → obtain `refresh_token`.
3. Cache it (`$BOL_HOME/msa/token.json`).
4. **Before launch**, write it into the launch prefix
   (`_heroic_pfx()` or `PFX`):
   `reg add "HKLM\Software\Wine\WineGDK" /v RefreshToken /t REG_SZ /d <token> /f`
   run through the same proton/umu command used to start the game.
5. Launch the game with **no ProxyPass and no relay**. The player joins the
   real server from Minecraft's own server list.

## Safety / fallback

- Opt-in only: setting `native_login` (off by default). CLI:
  `bedrock-on-linux config --native-login on|off`.
- When off, the ProxyPass path is byte-for-byte unchanged.
- Native login only works on a GDK-Proton build that includes the WineGDK
  `XUser` implementation. The launcher cannot introspect the bundled
  `xgameruntime.dll`, so it cannot auto-detect this — it warns and the user
  must opt in knowingly.
- **Verified 2026-05-18**: with stock GDK-Proton the game shows
  *"Authentication failed — 0x80004001"* (`E_NOTIMPL`, the XUser-absent
  signature). `diagnose()` now recognises this and points back to ProxyPass.
  No public XUser-capable build exists yet — assembling one is upstream
  C/Wine work, see [`build-xuser-engine.md`](build-xuser-engine.md).
- To use a self-built / community engine, point the launcher at it:
  `bedrock-on-linux config --proton-dir <dir>` or `--proton-url <url>`
  (`--proton-auto` reverts). Custom builds patch non-strict
  (`patch_proton(strict=False)`).

## Testing notes

- The device-code module is testable in isolation (HTTPS to `login.live.com`,
  no game needed): start returns a real `user_code`; completing the flow with
  a Microsoft account yields a `refresh_token`.
- The registry handoff and launch wiring cannot be validated on a box without
  a PR#33-capable GDK-Proton, the game files, and a display. They are written
  to the exact contract above and kept behind the opt-in flag.

## References

- WineGDK XUser: `https://github.com/Weather-OS/WineGDK/pull/33`,
  `.../pull/37`, `.../issues/10`
- Auth chain reference: gophertunnel `minecraft/auth`
  (`https://github.com/Sandertv/gophertunnel/tree/master/minecraft/auth`)
- GDK-Proton: `https://github.com/Weather-OS/GDK-Proton`
