#!/usr/bin/env bash
# Build every Linux artifact for a release: .deb, AppImage, portable tarball.
# Usage: scripts/build-release.sh
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$(grep -m1 '^VERSION = ' "$SRC/bedrock-on-linux" | cut -d'"' -f2)"
OUT="$SRC/dist"
mkdir -p "$OUT"

echo "== BedrockOnLinux $VER — building release artifacts =="
python3 "$SRC/scripts/make_icon.py"

# 1) .deb -----------------------------------------------------------------
if command -v dpkg-deb >/dev/null; then
  bash "$SRC/scripts/build-deb.sh" >/dev/null && \
    echo "  ✓ dist/bedrock-on-linux_${VER}_all.deb"
else
  echo "  – .deb skipped (dpkg-deb absent)"
fi

# 2) portable tarball (universal, no root) --------------------------------
TMP="$OUT/portable/bedrock-on-linux"
rm -rf "$OUT/portable"; mkdir -p "$TMP/data" "$TMP/scripts"
install -m755 "$SRC/bedrock-on-linux" "$TMP/bedrock-on-linux"
cp "$SRC/data/icon.png" "$TMP/data/icon.png"
cp "$SRC/data/bedrock-on-linux.desktop" "$TMP/data/"
cp "$SRC/scripts/install.sh" "$TMP/scripts/"
cp "$SRC/README.md" "$SRC/LICENSE" "$TMP/"
tar -C "$OUT/portable" -czf "$OUT/bedrock-on-linux-${VER}-portable.tar.gz" \
    bedrock-on-linux
rm -rf "$OUT/portable"
echo "  ✓ dist/bedrock-on-linux-${VER}-portable.tar.gz"

# 3) AppImage (best effort: needs network for appimagetool) ----------------
if bash "$SRC/scripts/build-appimage.sh" >/dev/null 2>&1; then
  [ -f "$OUT/BedrockOnLinux-x86_64.AppImage" ] && \
    mv "$OUT/BedrockOnLinux-x86_64.AppImage" \
       "$OUT/BedrockOnLinux-${VER}-x86_64.AppImage"
  echo "  ✓ dist/BedrockOnLinux-${VER}-x86_64.AppImage"
else
  echo "  – AppImage skipped (no network/FUSE) — build later with scripts/build-appimage.sh"
fi

# keep only the release artifacts
rm -rf "$OUT/appimagetool" "$OUT/BedrockOnLinux.AppDir" "$OUT/deb" \
       "$OUT/portable"
ls "$OUT"/*.deb 2>/dev/null | grep -v "_${VER}_" | xargs -r rm -f
ls "$OUT"/*.AppImage 2>/dev/null | grep -v "${VER}" | xargs -r rm -f
ls "$OUT"/*portable.tar.gz 2>/dev/null | grep -v "${VER}" | xargs -r rm -f

echo
echo "Release artifacts in $OUT :"
ls -1sh "$OUT" 2>/dev/null | grep -E '\.(deb|AppImage|tar\.gz)$' || true
echo
echo "Tag & publish (needs a GitHub remote + gh):"
echo "  git tag -a v$VER -m 'BedrockOnLinux v$VER' && git push origin v$VER"
echo "  gh release create v$VER dist/* -t 'BedrockOnLinux v$VER'"
