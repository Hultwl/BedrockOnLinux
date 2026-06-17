#!/usr/bin/env bash
# Build a .deb so BedrockOnLinux installs like a normal app (menu + search).
# Usage: scripts/build-deb.sh        -> dist/bedrock-on-linux_<ver>_all.deb
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$(grep -m1 '^VERSION = ' "$SRC/bol/config.py" | cut -d'"' -f2)"
OUT="$SRC/dist"
PKG="$OUT/deb"
rm -rf "$PKG"
mkdir -p "$OUT" \
  "$PKG/DEBIAN" \
  "$PKG/usr/lib/bedrock-on-linux/data" \
  "$PKG/usr/bin" \
  "$PKG/usr/share/applications" \
  "$PKG/usr/share/icons/hicolor/256x256/apps" \
  "$PKG/usr/share/doc/bedrock-on-linux"

[[ -f "$SRC/data/icon.png" ]] || { echo "data/icon.png missing" >&2; exit 1; }

install -m755 "$SRC/bedrock-on-linux" "$PKG/usr/lib/bedrock-on-linux/bedrock-on-linux"
cp -r "$SRC/bol"                       "$PKG/usr/lib/bedrock-on-linux/bol"
find "$PKG/usr/lib/bedrock-on-linux/bol" -name __pycache__ -type d -exec rm -rf {} +
install -m644 "$SRC/data/icon.png"    "$PKG/usr/lib/bedrock-on-linux/data/icon.png"
ln -s /usr/lib/bedrock-on-linux/bedrock-on-linux "$PKG/usr/bin/bedrock-on-linux"
install -m644 "$SRC/data/icon.png" \
  "$PKG/usr/share/icons/hicolor/256x256/apps/bedrock-on-linux.png"
install -m644 "$SRC/data/bedrock-on-linux.desktop" \
  "$PKG/usr/share/applications/bedrock-on-linux.desktop"
install -m644 "$SRC/README.md" "$PKG/usr/share/doc/bedrock-on-linux/README.md"

cat > "$PKG/DEBIAN/control" <<EOF
Package: bedrock-on-linux
Version: ${VER}
Section: games
Priority: optional
Architecture: all
Depends: python3 (>= 3.9), python3-tk, python3-cryptography, tar, zstd, xdg-utils, x11-xserver-utils, ca-certificates, curl | wget
Recommends: mesa-vulkan-drivers | nvidia-driver
Maintainer: BedrockOnLinux contributors <noreply@bedrockonlinux.invalid>
Homepage: https://github.com/Wyze3306/BedrockOnLinux
Description: Run Minecraft Bedrock (Windows GDK) on Linux, multiplayer included
 One graphical launcher that downloads and builds a WineGDK-based GDK-Proton,
 applies the binary patches the game needs, and signs you in to Microsoft
 inside the game (no relay, no proxy) so native and crossplay servers work.
 No game files are shipped; you supply your own.
EOF

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
update-desktop-database -q /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache -q -t /usr/share/icons/hicolor 2>/dev/null || true
exit 0
EOF
chmod 755 "$PKG/DEBIAN/postinst"

DEB="$OUT/bedrock-on-linux_${VER}_all.deb"
dpkg-deb --build --root-owner-group "$PKG" "$DEB" >/dev/null
rm -rf "$PKG"
ls "$OUT"/*.deb 2>/dev/null | grep -v "_${VER}_" | xargs -r rm -f
ls "$OUT"/*.AppImage 2>/dev/null | grep -v "${VER}" | xargs -r rm -f
ls "$OUT"/*portable.tar.gz 2>/dev/null | grep -v "${VER}" | xargs -r rm -f
echo "Built: $DEB"
dpkg-deb -I "$DEB" | sed -n '1,12p'
echo "Install:  sudo apt install $DEB     (or: sudo dpkg -i $DEB)"
