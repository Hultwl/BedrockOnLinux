#!/usr/bin/env bash
# Build the native Tcl/Tk + _tkinter part of the AppImage cache.  Called by
# build-appimage.sh either directly or inside its optional Bullseye rootfs.
set -euo pipefail

if (( $# != 6 )); then
  echo "usage: $0 BUILD_DIR INSTALL_DIR PYTHON_HOME TKINTER_SOURCE TK_VERSION PY_ABI" >&2
  exit 2
fi

BDIR="$1"
TKX="$2"
PYHOME="$3"
TKS="$4"
TKVER="$5"
PYABI="$6"
JOBS="${MAKE_JOBS:-$(nproc)}"

for tool in gcc make pkg-config strip; do
  command -v "$tool" >/dev/null 2>&1 \
    || { echo "!! Tcl/Tk build tool missing: $tool" >&2; exit 1; }
done
pkg-config --exists xft \
  || { echo "!! Tcl/Tk Xft headers missing (install libxft-dev)" >&2; exit 1; }

# Configure with the logical path used inside the AppImage, then stage through
# DESTDIR. Configuring directly with the host cache path bakes that maintainer-
# specific directory into libtcl and makes the bundle non-relocatable.
LOGICAL_PREFIX="/usr/python"
INSTALL_ROOT="${TKX}.install-root"
rm -rf "$TKX" "$INSTALL_ROOT"
mkdir -p "$TKX" "$INSTALL_ROOT"

(
  cd "$BDIR/tcl${TKVER}/unix"
  make distclean >/dev/null 2>&1 || true
  ./configure --prefix="$LOGICAL_PREFIX" --enable-shared \
    --enable-threads >/dev/null
  make -j"$JOBS" >/dev/null
  make DESTDIR="$INSTALL_ROOT" install >/dev/null
)
(
  cd "$BDIR/tk${TKVER}/unix"
  make distclean >/dev/null 2>&1 || true
  ./configure --prefix="$LOGICAL_PREFIX" --enable-shared --enable-threads \
    --with-tcl="$BDIR/tcl${TKVER}/unix" --with-x --disable-xss >/dev/null
  make -j"$JOBS" >/dev/null
  make DESTDIR="$INSTALL_ROOT" install >/dev/null
)
cp -a "$INSTALL_ROOT$LOGICAL_PREFIX/." "$TKX/"
rm -rf "$INSTALL_ROOT"
ldd "$TKX/lib/libtk8.6.so" | grep -qi libXft \
  || { echo "!! Tk built WITHOUT Xft — aborting" >&2; exit 1; }
ldd "$TKX/lib/libtk8.6.so" | grep -q 'libXss' \
  && { echo "!! Tk unexpectedly depends on optional libXss" >&2; exit 1; }

gcc -shared -fPIC -O2 -g0 -DWITH_APPINIT=1 -DPy_BUILD_CORE_MODULE \
  -ffile-prefix-map="$BDIR"=/usr/src/tcl-tk \
  -ffile-prefix-map="$TKX"="$LOGICAL_PREFIX" \
  -ffile-prefix-map="$PYHOME"="$LOGICAL_PREFIX" \
  -ffile-prefix-map="$TKS"=/usr/src/cpython/Modules \
  -I"$PYHOME/include/python3.12" -I"$PYHOME/include/python3.12/internal" \
  -I"$TKS" -I"$TKX/include" \
  "$TKS/_tkinter.c" "$TKS/tkappinit.c" \
  -L"$TKX/lib" -ltk8.6 -ltcl8.6 \
  -o "$TKX/_tkinter.${PYABI}.so"
strip --strip-debug "$TKX/lib/libtcl8.6.so" "$TKX/lib/libtk8.6.so" \
  "$TKX/_tkinter.${PYABI}.so"
