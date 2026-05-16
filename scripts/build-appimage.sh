#!/usr/bin/env bash
# Build a portable AppImage (single file, runs on any glibc Linux).
# Scaffold: bundles the launcher + a python3 requirement note. Heavy
# components (Proton/Java/ProxyPass) are still fetched at first run by design
# (they are huge and version-specific), keeping the AppImage small.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$SRC/dist"
APPDIR="$OUT/BedrockOnLinux.AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps" "$OUT"

cp "$SRC/bedrock-on-linux" "$APPDIR/usr/bin/bedrock-on-linux"
chmod +x "$APPDIR/usr/bin/bedrock-on-linux"
cp "$SRC/data/bedrock-on-linux.desktop" "$APPDIR/bedrock-on-linux.desktop"
cp "$SRC/data/bedrock-on-linux.desktop" \
   "$APPDIR/usr/share/applications/bedrock-on-linux.desktop"
[[ -f "$SRC/data/icon.png" ]] && cp "$SRC/data/icon.png" \
   "$APPDIR/bedrock-on-linux.png" || : > "$APPDIR/bedrock-on-linux.png"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec python3 "$HERE/usr/bin/bedrock-on-linux" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL="$OUT/appimagetool"
if [[ ! -x "$TOOL" ]]; then
  echo ":: fetching appimagetool"
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$TOOL"
fi

ARCH=x86_64 "$TOOL" "$APPDIR" "$OUT/BedrockOnLinux-x86_64.AppImage"
echo "OK -> $OUT/BedrockOnLinux-x86_64.AppImage"
