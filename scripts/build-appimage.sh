#!/usr/bin/env bash
# Fully self-contained AppImage with a MODERN, good-looking Tk.
#
# python-build-standalone ships Tk without Xft → ugly X11 core fonts and no
# symbol glyphs (▶/⚙ render as tofu). So we build Tcl/Tk 8.6 WITH Xft and a
# matching _tkinter for the bundled CPython, bundle them (rpath'd to $ORIGIN so
# they relocate), and rely on the host's libXft/libfontconfig/libfreetype (on
# every desktop) → antialiased fonts identical to the system Tk. Also bundles
# cryptography + a CA store so login and all HTTPS work with nothing installed.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$(grep -m1 '^VERSION = ' "$SRC/bol/config.py" | cut -d'"' -f2)"
OUT="$SRC/dist"; CACHE="$OUT/.cache"; mkdir -p "$CACHE" "$OUT"
APPDIR="$OUT/BedrockOnLinux.AppDir"; rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"

PBS_TAG="${PBS_TAG:-20260610}"; PBS_PY="${PBS_PY:-3.12.13}"; PYABI=cpython-312-x86_64-linux-gnu
PBS_ASSET="cpython-${PBS_PY}+${PBS_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PBS_ASSET}"
PBS_TARBALL="$CACHE/$PBS_ASSET"
TKVER="${TKVER:-8.6.14}"

# patchelf (build-time only): pip-installs it if the host has none.
PATCHELF="${PATCHELF:-$(command -v patchelf || true)}"
if [[ -z "$PATCHELF" ]]; then
  python3 -m pip install --quiet --user patchelf 2>/dev/null || true
  PATCHELF="$(command -v patchelf || echo "$HOME/.local/bin/patchelf")"
fi
[[ -x "$PATCHELF" ]] || { echo "!! need patchelf (pip install patchelf)" >&2; exit 1; }

# --- 1. relocatable CPython (python-build-standalone) ------------------------
if [[ ! -f "$PBS_TARBALL" ]]; then
  echo "== downloading bundled Python: $PBS_ASSET"
  curl -fSL --retry 3 -o "$PBS_TARBALL.part" "$PBS_URL" && mv "$PBS_TARBALL.part" "$PBS_TARBALL"
fi
echo "== unpacking Python into the AppDir"
tar -C "$APPDIR/usr" -xzf "$PBS_TARBALL"
PYHOME="$APPDIR/usr/python"; PYBIN="$PYHOME/bin/python3.12"
PYLIB="$PYHOME/lib"; DYN="$PYLIB/python3.12/lib-dynload"
[[ -x "$PYBIN" ]] || { echo "!! bundled python missing" >&2; exit 1; }

# --- 2. Tcl/Tk 8.6 + Xft and a matching _tkinter (cached) --------------------
TKX="$CACHE/tkxft-${PBS_PY}-${TKVER}"
if [[ ! -f "$TKX/lib/libtk8.6.so" || ! -f "$TKX/_tkinter.${PYABI}.so" ]]; then
  echo "== building Tcl/Tk ${TKVER} with Xft (one-time, cached)"
  rm -rf "$TKX"; mkdir -p "$TKX"
  bdir="$CACHE/tk-build"; rm -rf "$bdir"; mkdir -p "$bdir"
  for kit in tcl tk; do
    [[ -f "$CACHE/${kit}${TKVER}-src.tar.gz" ]] || \
      curl -fsSL -o "$CACHE/${kit}${TKVER}-src.tar.gz" \
        "https://prdownloads.sourceforge.net/tcl/${kit}${TKVER}-src.tar.gz"
    tar -C "$bdir" -xzf "$CACHE/${kit}${TKVER}-src.tar.gz"
  done
  ( cd "$bdir/tcl${TKVER}/unix" && ./configure --prefix="$TKX" --enable-shared \
      --enable-threads >/dev/null && make -j"$(nproc)" >/dev/null && make install >/dev/null )
  ( cd "$bdir/tk${TKVER}/unix" && ./configure --prefix="$TKX" --enable-shared \
      --enable-threads --with-tcl="$TKX/lib" --with-x >/dev/null \
      && make -j"$(nproc)" >/dev/null && make install >/dev/null )
  ldd "$TKX/lib/libtk8.6.so" | grep -qi libXft \
    || { echo "!! Tk built WITHOUT Xft — aborting" >&2; exit 1; }
  # _tkinter for the bundled CPython, linked to this Tk
  tks="$CACHE/tksrc-${PBS_PY}"; mkdir -p "$tks/clinic"
  base="https://raw.githubusercontent.com/python/cpython/v${PBS_PY}/Modules"
  for f in _tkinter.c tkappinit.c tkinter.h clinic/_tkinter.c.h; do
    [[ -f "$tks/$f" ]] || curl -fsSL -o "$tks/$f" "$base/$f"
  done
  gcc -shared -fPIC -O2 -DWITH_APPINIT=1 -DPy_BUILD_CORE_MODULE \
    -I"$PYHOME/include/python3.12" -I"$PYHOME/include/python3.12/internal" \
    -I"$tks" -I"$TKX/include" \
    "$tks/_tkinter.c" "$tks/tkappinit.c" \
    -L"$TKX/lib" -ltk8.6 -ltcl8.6 -o "$TKX/_tkinter.${PYABI}.so"
fi

# --- 3. graft the Xft Tk into the bundled Python -----------------------------
echo "== grafting Xft Tk into the bundle"
install -m644 "$TKX/lib/libtcl8.6.so" "$TKX/lib/libtk8.6.so" "$PYLIB/"
cp -r "$TKX/lib/tcl8.6" "$TKX/lib/tk8.6" "$PYLIB/"
install -m755 "$TKX/_tkinter.${PYABI}.so" "$DYN/_tkinter.${PYABI}.so"
# drop python-build-standalone's no-Xft Tcl/Tk 9 so it can never be picked up
rm -f "$PYLIB"/libtcl9*.so "$PYLIB"/libtcl9tk9*.so
rm -rf "$PYLIB"/tcl9* "$PYLIB"/tk9* 2>/dev/null || true
# rpath so the grafted libs find each other relative to the AppImage mount
"$PATCHELF" --set-rpath '$ORIGIN'        "$PYLIB/libtk8.6.so"
"$PATCHELF" --set-rpath '$ORIGIN/../..'  "$DYN/_tkinter.${PYABI}.so"

# --- 4. python deps: cryptography (login) + certifi (CA store) +
#       customtkinter (the modern rounded GUI; pulls darkdetect + packaging) --
echo "== installing cryptography + certifi + customtkinter into the bundle"
"$PYBIN" -m pip install --no-cache-dir --no-compile \
    cryptography certifi customtkinter >/dev/null

# --- 5. trim weight a launcher never needs -----------------------------------
PY3="$PYLIB/python3.12"
rm -rf "$PY3/test" "$PY3/idlelib" "$PY3/turtledemo" "$PY3/tkinter/test" \
       "$PY3/lib2to3" "$PY3/ensurepip" "$PYHOME/share" "$PYHOME/include" 2>/dev/null || true
find "$PYHOME" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$PYHOME" -name '*.pyc' -delete 2>/dev/null || true

# --- 6. the launcher itself --------------------------------------------------
[[ -f "$SRC/data/icon.png" ]] || { echo "data/icon.png missing" >&2; exit 1; }
install -m755 "$SRC/bedrock-on-linux" "$APPDIR/usr/bin/bedrock-on-linux"
cp -r "$SRC/bol" "$APPDIR/usr/bin/bol"
find "$APPDIR/usr/bin/bol" -name __pycache__ -type d -exec rm -rf {} +
mkdir -p "$APPDIR/usr/bin/data"
cp "$SRC/data/icon.png" "$APPDIR/usr/bin/data/icon.png"
cp "$SRC/data/icon.png" "$APPDIR/bedrock-on-linux.png"
cp "$SRC/data/icon.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/bedrock-on-linux.png"
sed 's|^Exec=.*|Exec=bedrock-on-linux gui|' \
   "$SRC/data/bedrock-on-linux.desktop" > "$APPDIR/bedrock-on-linux.desktop"
cp "$APPDIR/bedrock-on-linux.desktop" \
   "$APPDIR/usr/share/applications/bedrock-on-linux.desktop"

# --- 7. AppRun ---------------------------------------------------------------
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
PY="$HERE/usr/python/bin/python3.12"
export TCL_LIBRARY="$HERE/usr/python/lib/tcl8.6"
export TK_LIBRARY="$HERE/usr/python/lib/tk8.6"
CERT="$HERE/usr/python/lib/python3.12/site-packages/certifi/cacert.pem"
[[ -f "$CERT" ]] && { export SSL_CERT_FILE="$CERT"; export REQUESTS_CA_BUNDLE="$CERT"; }
unset PYTHONHOME PYTHONPATH        # self-contained; libs found via rpath
exec "$PY" "$HERE/usr/bin/bedrock-on-linux" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# --- 8. prove self-sufficiency (no LD_LIBRARY_PATH, host certs hidden) -------
echo "== verifying the bundle: Xft Tk + cryptography + HTTPS, all self-contained"
env -i TCL_LIBRARY="$PYHOME/lib/tcl8.6" TK_LIBRARY="$PYHOME/lib/tk8.6" \
   SSL_CERT_FILE="$PYLIB/python3.12/site-packages/certifi/cacert.pem" \
   SSL_CERT_DIR=/nonexistent \
   ${DISPLAY:+DISPLAY="$DISPLAY"} ${XAUTHORITY:+XAUTHORITY="$XAUTHORITY"} \
   "$PYBIN" - <<'PY'
import _tkinter, cryptography, customtkinter, ssl, urllib.request, os
from cryptography.hazmat.primitives.asymmetric import ec
assert _tkinter.TK_VERSION == "8.6", _tkinter.TK_VERSION   # Xft build, not PBS Tk9
urllib.request.urlopen("https://api.github.com", timeout=20).read(16)  # bundled CA
msg = (f"  bundle OK: Tk {_tkinter.TK_VERSION} | cryptography {cryptography.__version__}"
       f" | customtkinter {customtkinter.__version__} | HTTPS via bundled CA")
if os.environ.get("DISPLAY"):
    import tkinter; from tkinter import font
    r = tkinter.Tk(); r.withdraw()
    fams = set(font.families()); n = len(fams)
    r.destroy()
    assert n > 100, f"Xft not active — only {n} fonts"
    msg += f" | {n} font families (Xft, antialiased)"
print(msg)
PY

# --- 9. package --------------------------------------------------------------
TOOL="$OUT/appimagetool"
if [[ ! -x "$TOOL" ]]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$TOOL"
fi
APPIMG="$OUT/BedrockOnLinux-${VER}-x86_64.AppImage"
rm -f "$OUT"/BedrockOnLinux-*-x86_64.AppImage "$OUT"/BedrockOnLinux-x86_64.AppImage
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$APPIMG"
rm -rf "$APPDIR"
echo "OK -> $APPIMG ($(du -h "$APPIMG" | cut -f1))"
