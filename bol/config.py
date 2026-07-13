"""bol.config — constants, paths, repos and URLs (no logic, no side effects)."""
# SPDX-License-Identifier: MIT

import os
from pathlib import Path

APP = "bedrock-on-linux"
PRETTY = "BedrockOnLinux"
VERSION = "1.3.0"

HOME = Path.home()
DATA = Path(os.environ.get("BOL_HOME", HOME / ".local/share" / APP))
PROTON_DIR = DATA / "proton"
UMU_DIR = DATA / "umu"
COMPAT = DATA / "compatdata"
PFX = COMPAT / "pfx"
GAMES = DATA / "games"
CONTENT = DATA / "content"
CACHE = DATA / "cache"
LOGS = DATA / "logs"
MSA_DIR = DATA / "msa"
SETTINGS = DATA / "settings.json"

GDK_PROTON_REPO = "Weather-OS/GDK-Proton"
UMU_REPO = "Open-Wine-Components/umu-launcher"
UMU_VERSION = "1.4.0"
UMU_ASSET = "umu-launcher-1.4.0-zipapp.tar"
UMU_ARCHIVE_SHA256 = \
    "138ce4b8843608a257d4bee88191ca78a989778bcefd8abb3c1d1aaac3ac6fb8"
UMU_RUN_SHA256 = \
    "bdac203e74f77b8b375ce72de0671c5a227815b912faacd09ecf450ee6650f62"
GAME_ARCHIVE_REPO = "bubbles-wow/mcbe-gdk-unpack-archive"
MINGW_CURL = "https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-curl-8.17.0-1-any.pkg.tar.zst"
CACERT_URL = "https://curl.se/ca/cacert.pem"

# In-game Microsoft login: WineGDK's XUser has no sign-in UI — it reads an
# MSA OAuth refresh token from the prefix registry (WINEGDK_REG) and does the
# Xbox Live exchange itself. The launcher only runs the device-code flow and
# seeds that token. MSA_CLIENT_ID must equal WineGDK's hardcoded msaAppId or
# the refresh is rejected.
MSA_CLIENT_ID = "0000000048183522"
MSA_SCOPE = "service::user.auth.xboxlive.com::MBI_SSL"
MSA_CONNECT = "https://login.live.com/oauth20_connect.srf"
MSA_TOKEN = "https://login.live.com/oauth20_token.srf"
WINEGDK_REG = r"Software\Wine\WineGDK"

# Exact WineGDK source used for the reviewed r11 binary engine.
WINEGDK_SOURCE_COMMIT = "670eda2864dcb22d11c7f2c28973214d4755ad2f"
# OSS replacements for the game's GDK Xbox-Live DLLs (minecraft-linux project).
GDK_DEPS_URL = "https://github.com/minecraft-linux/mcpelauncher-gdk-dependencies/releases/download/v0.0.0"
GDK_DEPS_DLLS = ("libHttpClient.GDK.dll", "XCurl.dll")
# OpenSSL libcurl + CA-shim + cryptbase stub set: installed as XCurl.dll so
# Minecraft's PlayFab traffic goes over OpenSSL TLS instead of Wine secur32
# (whose handshake Azure Front Door silently FINs → endless sign-in loop).
# Too big to bundle (20 MB) — downloaded once from the app's releases as
# openssl-xcurl-set-<rev>.tar.gz. Republish: scripts/package-openssl-xcurl.sh.
OPENSSL_XCURL_SET = DATA / "xodus-xcurl" / "openssl-set"
OPENSSL_XCURL_REV = "17bc4b81e178"
# Exact reviewed online-login payload. A filename/revision alone is not an
# integrity boundary; local siblings and downloaded assets must match this pin.
OPENSSL_XCURL_ARCHIVE_SHA256 = "17bc4b81e178422e12b238cca7ce4be0f06d9f64fa9a0dae4076d861c2f66983"
WINEGDK_OUT = PROTON_DIR / "GDK-Proton-xuser"
# Prebuilt engine: users download GDK-Proton-xuser-<build-rev>.tar.gz from the
# app's releases instead of compiling Wine.  Managed engines are fail-closed:
# the launcher only accepts the exact archive hash compiled into this version.
# Build locally with scripts/package-engine.sh, then pin its printed SHA-256.
WINEGDK_PREBUILT_REPO = "Wyze3306/BedrockOnLinux"
# Bump when the build/packaging method changes → forces a clean rebuild.
WINEGDK_BUILD_REV = "wow64-archs-r11"
# SHA-256 of the reviewed, deterministic r11 archive.  An invalid value makes
# the installer fail closed rather than accepting a differently packed engine.
WINEGDK_ARCHIVE_SHA256 = "90959a664de8aed7ff4f5a9e8866ba9ba096fc7369f59069d4e873695ad9913c"

SELF_REPO = WINEGDK_PREBUILT_REPO
