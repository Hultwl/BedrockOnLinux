#!/usr/bin/env bash
# Build a portable AppImage (single file, runs on any glibc Linux).
# Heavy components (GDK-Proton, the game) are fetched/built at first run by
# design (huge & version-specific), keeping the AppImage tiny.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$(grep -m1 '^VERSION = ' "$SRC/bol/config.py" | cut -d'"' -f2)"
OUT="$SRC/dist"
APPDIR="$OUT/BedrockOnLinux.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps" "$OUT"

[[ -f "$SRC/data/icon.png" ]] || { echo "data/icon.png missing" >&2; exit 1; }
install -m755 "$SRC/bedrock-on-linux" "$APPDIR/usr/bin/bedrock-on-linux"
# the implementation lives in the bol/ package next to the entry point
cp -r "$SRC/bol" "$APPDIR/usr/bin/bol"
find "$APPDIR/usr/bin/bol" -name __pycache__ -type d -exec rm -rf {} +
mkdir -p "$APPDIR/usr/bin/data"
cp "$SRC/data/icon.png" "$APPDIR/usr/bin/data/icon.png"
cp "$SRC/data/icon.png" "$APPDIR/bedrock-on-linux.png"
cp "$SRC/data/icon.png" \
   "$APPDIR/usr/share/icons/hicolor/256x256/apps/bedrock-on-linux.png"
sed 's|^Exec=.*|Exec=bedrock-on-linux gui|' \
   "$SRC/data/bedrock-on-linux.desktop" > "$APPDIR/bedrock-on-linux.desktop"
cp "$APPDIR/bedrock-on-linux.desktop" \
   "$APPDIR/usr/share/applications/bedrock-on-linux.desktop"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec python3 "$HERE/usr/bin/bedrock-on-linux" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL="$OUT/appimagetool"
if [[ ! -x "$TOOL" ]]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$TOOL"
fi

# One clean, version-stamped artifact. Drop any stale AppImages first so
# dist/ never accumulates an unversioned copy next to the versioned one.
APPIMG="$OUT/BedrockOnLinux-${VER}-x86_64.AppImage"
rm -f "$OUT"/BedrockOnLinux-*-x86_64.AppImage "$OUT"/BedrockOnLinux-x86_64.AppImage \
      "$OUT"/BedrockOnLinux-*.AppImage.old

# run appimagetool without FUSE (sandbox/CI friendly)
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$APPIMG"
echo "OK -> $APPIMG"
