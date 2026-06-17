#!/usr/bin/env bash
# Package a *built* WineGDK GDK-Proton tree into the release asset that the
# launcher downloads, so end users never compile a full Wine themselves.
#
# The launcher (bedrock-on-linux) looks on its own GitHub releases for an
# asset named exactly:
#       GDK-Proton-xuser-<WINEGDK_BUILD_REV>.tar.gz
# and, when found, unpacks it instead of cloning + building the fork. Only
# when no such asset exists does it fall back to the from-source build.
#
# Usage:
#   scripts/package-engine.sh [ENGINE_DIR]
#
#   ENGINE_DIR   a built GDK-Proton-xuser tree (must contain ./proton and
#                ./files). Default: $BOL_HOME/proton/GDK-Proton-xuser
#                (i.e. ~/.local/share/bedrock-on-linux/proton/GDK-Proton-xuser),
#                which is exactly what a successful first-run build produces.
#
# Output: dist/GDK-Proton-xuser-<rev>.tar.gz  (+ the gh command to publish it).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$SRC/dist"; mkdir -p "$OUT"

# Pull the build rev straight from the launcher so the asset name always
# matches what the launcher will look for.
REV="$(grep -m1 '^WINEGDK_BUILD_REV = ' "$SRC/bol/config.py" | cut -d'"' -f2)"
[[ -n "$REV" ]] || { echo "!! could not read WINEGDK_BUILD_REV" >&2; exit 1; }

BOL_HOME="${BOL_HOME:-$HOME/.local/share/bedrock-on-linux}"
ENGINE_DIR="${1:-$BOL_HOME/proton/GDK-Proton-xuser}"

if [[ ! -f "$ENGINE_DIR/proton" || ! -d "$ENGINE_DIR/files" ]]; then
  echo "!! '$ENGINE_DIR' is not a built engine (need ./proton file and ./files dir)." >&2
  echo "   Build one first:  bedrock-on-linux setup --force   (then re-run)." >&2
  exit 1
fi

ASSET="GDK-Proton-xuser-${REV}.tar.gz"
TARBALL="$OUT/$ASSET"
echo "== Packaging engine '$REV' from: $ENGINE_DIR"
echo "   source size: $(du -sh "$ENGINE_DIR" | cut -f1)"

# Pack with the tree under a top-level 'GDK-Proton-xuser/' dir (the launcher
# accepts that, or a tarball whose root is already the proton tree). Use pigz
# when available — a 2.5 GB tree is slow to gzip single-threaded.
PARENT="$(cd "$ENGINE_DIR/.." && pwd)"
BASE="$(basename "$ENGINE_DIR")"
if command -v pigz >/dev/null; then
  tar -C "$PARENT" -cf - "$BASE" | pigz -6 > "$TARBALL"
else
  echo "   (install 'pigz' for a much faster pack)"
  tar -C "$PARENT" -czf "$TARBALL" "$BASE"
fi

SZ_BYTES="$(stat -c%s "$TARBALL")"
echo "   ✓ $TARBALL  ($(du -h "$TARBALL" | cut -f1))"
# GitHub caps a single release asset at 2 GiB.
if (( SZ_BYTES > 2147483648 )); then
  echo "!! WARNING: asset > 2 GiB — GitHub will reject it. Trim the tree" >&2
  echo "   (drop unused dxvk/vkd3d state) or split it before uploading." >&2
fi

echo
echo "Publish it (attach to ANY release on the app repo — the launcher scans"
echo "by asset name, not by tag):"
echo "  gh release upload v1.0.0 \"$TARBALL\" --clobber"
echo "or create a dedicated engine release:"
echo "  gh release create engine-$REV \"$TARBALL\" \\"
echo "      -t 'GDK-Proton-xuser engine ($REV)' \\"
echo "      -n 'Prebuilt WineGDK engine — auto-downloaded by the launcher.'"
