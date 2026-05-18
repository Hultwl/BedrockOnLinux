#!/usr/bin/env bash
# Build the WineGDK XUser fork and overlay it onto a stock GDK-Proton, so
# `bedrock-on-linux config --proton-dir <out>` enables native in-game login.
#
# This automates the mechanical steps only. It builds a large Wine fork
# (long, environment-heavy) and the overlay packaging is NOT verified by
# this repo — you MUST test the result in-game. See docs/build-xuser-engine.md.
#
# Usage:
#   scripts/build-winegdk-proton.sh [WINEGDK_SRC] [BASE_GDK_PROTON] [OUT_DIR]
# Defaults:
#   WINEGDK_SRC      = ~/Bureau/WineGDK            (branch: xuser-login)
#   BASE_GDK_PROTON  = settings.json "proton", else ~/.local/share/bedrock-on-linux/proton/GDK-Proton*
#   OUT_DIR          = ~/.local/share/bedrock-on-linux/proton/GDK-Proton-xuser
set -euo pipefail

SRC="${1:-$HOME/Bureau/WineGDK}"
DATA="${BOL_HOME:-$HOME/.local/share/bedrock-on-linux}"
BASE="${2:-}"
OUT="${3:-$DATA/proton/GDK-Proton-xuser}"

say() { printf '\n\033[1;32m:: %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mxx %s\033[0m\n' "$*" >&2; exit 1; }

[ -d "$SRC/dlls/xgameruntime" ] || die "Not a WineGDK tree: $SRC"

if [ -z "$BASE" ]; then
  if [ -f "$DATA/settings.json" ]; then
    BASE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("proton",""))' "$DATA/settings.json" 2>/dev/null || true)"
  fi
  [ -n "$BASE" ] && [ -d "$BASE" ] || BASE="$(ls -d "$DATA"/proton/GDK-Proton* 2>/dev/null | head -1 || true)"
fi
[ -n "$BASE" ] && [ -x "$BASE/proton" ] || die "No base GDK-Proton found. Run BedrockOnLinux setup once, or pass it as arg 2."

# --- prerequisites -------------------------------------------------------
miss=()
for t in gcc make flex bison pkg-config x86_64-w64-mingw32-gcc; do
  command -v "$t" >/dev/null 2>&1 || miss+=("$t")
done
if [ "${#miss[@]}" -gt 0 ]; then
  cat >&2 <<EOF
xx Missing build tools: ${miss[*]}
   Debian/Ubuntu (64-bit WineGDK build):
     sudo apt build-dep wine        # or wine-development
     sudo apt install flex bison gcc-mingw-w64-x86-64 pkg-config \\
       libfreetype-dev libvulkan-dev libgnutls28-dev
   Then re-run this script.
EOF
  exit 1
fi

say "WineGDK source : $SRC"
git -C "$SRC" rev-parse --abbrev-ref HEAD 2>/dev/null | grep -qx xuser-login \
  || echo "!! branch is not 'xuser-login' — continuing with current checkout"
say "Base GDK-Proton: $BASE"
say "Output         : $OUT"

# --- build (64-bit; Minecraft GDK is x86_64) -----------------------------
BD="$SRC/build-xuser"
mkdir -p "$BD"
say "configure (this is slow the first time) …"
# Keep X support — the game must display; do NOT pass --without-x.
( cd "$BD" && ../configure --enable-win64 --disable-tests \
    --prefix="$BD/_install" )
say "make -j$(nproc) … (long — a full Wine build)"
( cd "$BD" && make -j"$(nproc)" )
say "make install (staging) …"
( cd "$BD" && make install >/dev/null )

# --- overlay onto a copy of the stock GDK-Proton -------------------------
say "Cloning base GDK-Proton → $OUT"
rm -rf "$OUT"
cp -a "$BASE" "$OUT"

WINEROOT="$(find "$BD/_install" -maxdepth 3 -type d -name wine -path '*/lib/*' | head -1)"
[ -n "$WINEROOT" ] || die "Built wine libdir not found under $BD/_install"
DEST_WINE="$(find "$OUT/files" -maxdepth 3 -type d -name wine -path '*/lib*/*' | head -1)"
[ -n "$DEST_WINE" ] || die "wine libdir not found in $OUT/files (unexpected GDK-Proton layout)"

say "Overlaying built WineGDK ($WINEROOT) → $DEST_WINE"
cp -a "$WINEROOT/." "$DEST_WINE/"
# wine loader binaries
for b in wine wine64 wineserver; do
  s="$(find "$BD/_install" -maxdepth 3 -type f -name "$b" | head -1 || true)"
  d="$(find "$OUT/files" -maxdepth 3 -type f -name "$b" | head -1 || true)"
  [ -n "$s" ] && [ -n "$d" ] && cp -a "$s" "$d" && echo "   replaced $d"
done

# sanity: the whole point — xgameruntime.dll with XUser must be present
if find "$DEST_WINE" -name xgameruntime.dll | grep -q .; then
  say "OK: xgameruntime.dll present in the overlay"
else
  echo "!! xgameruntime.dll not found in overlay — build/layout needs checking"
fi

cat <<EOF

Done (build + overlay). NOT verified in-game by this script.

Point BedrockOnLinux at it and enable native login:

  bedrock-on-linux config --proton-dir "$OUT"
  bedrock-on-linux config --native-login on
  bedrock-on-linux login
  bedrock-on-linux play

Revert any time:  bedrock-on-linux config --proton-auto
If the game still shows 0x80004001, the build/overlay didn't take effect;
see docs/build-xuser-engine.md for the manual GDK-Proton packaging route.
EOF
