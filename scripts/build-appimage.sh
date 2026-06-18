#!/usr/bin/env bash
# Build a fully self-contained AppImage: a relocatable CPython (with tkinter and
# Tcl/Tk) plus cryptography are bundled inside, so the launcher runs on any
# glibc Linux with NOTHING pre-installed — no system python3, no python3-tk.
# Heavy, version-specific components (GDK-Proton, the game) are still fetched at
# first run by design.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$(grep -m1 '^VERSION = ' "$SRC/bol/config.py" | cut -d'"' -f2)"
OUT="$SRC/dist"
APPDIR="$OUT/BedrockOnLinux.AppDir"
CACHE="$OUT/.cache"; mkdir -p "$CACHE" "$OUT"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# --- 1. relocatable Python (python-build-standalone, includes tkinter) -------
# install_only + gnu (glibc) build; pin the latest release at build time.
PBS_TAG="${PBS_TAG:-20260610}"
PBS_PY="${PBS_PY:-3.12.13}"
PBS_ASSET="cpython-${PBS_PY}+${PBS_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PBS_ASSET}"
PBS_TARBALL="$CACHE/$PBS_ASSET"
if [[ ! -f "$PBS_TARBALL" ]]; then
  echo "== downloading bundled Python: $PBS_ASSET"
  curl -fSL --retry 3 -o "$PBS_TARBALL.part" "$PBS_URL"
  mv "$PBS_TARBALL.part" "$PBS_TARBALL"
fi
echo "== unpacking Python into the AppDir"
# the tarball unpacks to a top-level 'python/' dir
tar -C "$APPDIR/usr" -xzf "$PBS_TARBALL"
PYHOME="$APPDIR/usr/python"
PYBIN="$PYHOME/bin/python3.12"
[[ -x "$PYBIN" ]] || { echo "!! bundled python missing at $PYBIN" >&2; exit 1; }

# --- 2. bake in the login dependency (cryptography) so it works offline ------
echo "== installing cryptography into the bundle"
"$PYBIN" -m pip install --no-cache-dir --no-compile cryptography >/dev/null

# --- 3. trim weight that a launcher never needs ------------------------------
PYLIB="$PYHOME/lib/python3.12"
rm -rf "$PYLIB/test" "$PYLIB/idlelib" "$PYLIB/turtledemo" \
       "$PYLIB/tkinter/test" "$PYLIB/lib2to3" "$PYLIB/ensurepip" \
       "$PYHOME/share" "$PYHOME/include" 2>/dev/null || true
find "$PYHOME" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$PYHOME" -name '*.pyc' -delete 2>/dev/null || true

# --- 4. the launcher itself --------------------------------------------------
[[ -f "$SRC/data/icon.png" ]] || { echo "data/icon.png missing" >&2; exit 1; }
install -m755 "$SRC/bedrock-on-linux" "$APPDIR/usr/bin/bedrock-on-linux"
cp -r "$SRC/bol" "$APPDIR/usr/bin/bol"          # package sits next to the entry
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

# --- 5. AppRun: run the BUNDLED python, never the host's ---------------------
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
PY="$HERE/usr/python/bin/python3.12"
# Tcl/Tk ship inside the bundle; point at them so tkinter works even on a host
# that has no Tcl/Tk at all.
for d in "$HERE"/usr/python/lib/tcl8.*; do [[ -d "$d" ]] && export TCL_LIBRARY="$d"; done
for d in "$HERE"/usr/python/lib/tk8.*;  do [[ -d "$d" ]] && export TK_LIBRARY="$d"; done
# self-contained: don't let a host PYTHON* env leak in
unset PYTHONHOME PYTHONPATH
exec "$PY" "$HERE/usr/bin/bedrock-on-linux" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# --- 6. prove the bundle is self-sufficient before packaging -----------------
echo "== verifying the bundle imports tkinter + cryptography (no host deps)"
env -i "$PYBIN" - <<'PY'
import tkinter, cryptography, ssl, ctypes
from cryptography.hazmat.primitives.asymmetric import ec   # the login path
print("  bundle OK: tkinter", tkinter.TkVersion, "| cryptography", cryptography.__version__)
PY

# --- 7. package --------------------------------------------------------------
TOOL="$OUT/appimagetool"
if [[ ! -x "$TOOL" ]]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$TOOL"
fi
APPIMG="$OUT/BedrockOnLinux-${VER}-x86_64.AppImage"
rm -f "$OUT"/BedrockOnLinux-*-x86_64.AppImage "$OUT"/BedrockOnLinux-x86_64.AppImage \
      "$OUT"/BedrockOnLinux-*.AppImage.old
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$APPIMG"
rm -rf "$APPDIR"
echo "OK -> $APPIMG ($(du -h "$APPIMG" | cut -f1))"
