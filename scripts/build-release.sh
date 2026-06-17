#!/usr/bin/env bash
# Build every Linux artifact for a release: .deb, AppImage, portable .pyz.
# Usage: scripts/build-release.sh
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$(grep -m1 '^VERSION = ' "$SRC/bol/config.py" | cut -d'"' -f2)"
OUT="$SRC/dist"
mkdir -p "$OUT"

echo "== BedrockOnLinux $VER — building release artifacts =="

# 1) .deb -----------------------------------------------------------------
if command -v dpkg-deb >/dev/null; then
  bash "$SRC/scripts/build-deb.sh" >/dev/null && \
    echo "  ✓ dist/bedrock-on-linux_${VER}_all.deb"
else
  echo "  – .deb skipped (dpkg-deb absent)"
fi

# 2) portable single-file zipapp (.pyz — universal, no root, self-updating) -
# The bol/ package + a tiny __main__ are zipped into one executable file with a
# `#!/usr/bin/env python3` shebang. It needs only a host python3 (+ tkinter for
# the GUI; cryptography is auto-installed at first login — see bol/deps.py).
STAGE="$OUT/pyz-stage"
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -r "$SRC/bol" "$STAGE/bol"
find "$STAGE/bol" -name __pycache__ -type d -exec rm -rf {} +
cat > "$STAGE/__main__.py" <<'PYEOF'
import sys
from bol.cli import main
try:
    main()
except KeyboardInterrupt:
    print(); sys.exit(130)
PYEOF
python3 -m zipapp "$STAGE" -p "/usr/bin/env python3" \
    -o "$OUT/bedrock-on-linux-${VER}.pyz"
chmod +x "$OUT/bedrock-on-linux-${VER}.pyz"
rm -rf "$STAGE"
echo "  ✓ dist/bedrock-on-linux-${VER}.pyz"

# 3) AppImage (best effort: needs network for appimagetool) ----------------
# build-appimage.sh already produces the version-stamped artifact.
if bash "$SRC/scripts/build-appimage.sh" >/dev/null 2>&1; then
  echo "  ✓ dist/BedrockOnLinux-${VER}-x86_64.AppImage"
else
  echo "  – AppImage skipped (no network/FUSE) — build later with scripts/build-appimage.sh"
fi

# 4) Flatpak (best effort: needs flatpak-builder + network) ----------------
# build-flatpak.sh self-skips (exit 0) when flatpak-builder is absent.
if command -v flatpak-builder >/dev/null; then
  if bash "$SRC/scripts/build-flatpak.sh" >/dev/null 2>&1; then
    echo "  ✓ dist/BedrockOnLinux-${VER}-x86_64.flatpak"
  else
    echo "  – Flatpak skipped (build failed) — run scripts/build-flatpak.sh to see why"
  fi
else
  echo "  – Flatpak skipped (flatpak-builder absent) — see flatpak/README.md"
fi

# keep only the release artifacts
rm -rf "$OUT/appimagetool" "$OUT/BedrockOnLinux.AppDir" "$OUT/deb" \
       "$OUT/portable" "$OUT/pyz-stage" "$OUT/flatpak-build"
ls "$OUT"/*.deb 2>/dev/null | grep -v "_${VER}_" | xargs -r rm -f
ls "$OUT"/*.AppImage 2>/dev/null | grep -v "${VER}" | xargs -r rm -f
ls "$OUT"/*.pyz 2>/dev/null | grep -v "${VER}" | xargs -r rm -f
ls "$OUT"/*portable.tar.gz 2>/dev/null | xargs -r rm -f
ls "$OUT"/*.flatpak 2>/dev/null | grep -v "${VER}" | xargs -r rm -f

echo
echo "Release artifacts in $OUT :"
ls -1sh "$OUT" 2>/dev/null | grep -E '\.(deb|AppImage|pyz|flatpak)$' || true
echo
echo "Tag & publish (needs a GitHub remote + gh):"
echo "  git tag -a v$VER -m 'BedrockOnLinux v$VER' && git push origin v$VER"
echo "  gh release create v$VER dist/* -t 'BedrockOnLinux v$VER'"
