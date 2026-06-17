#!/usr/bin/env bash
# Build the BedrockOnLinux Flatpak.
#
#   scripts/build-flatpak.sh             # local dev: app module = working tree
#   scripts/build-flatpak.sh --release   # exact Flathub manifest (needs the
#                                        # git tag referenced in the manifest)
#
# Output: dist/BedrockOnLinux-<ver>-x86_64.flatpak. Uses the flatpak-builder
# binary if present, else the no-root org.flatpak.Builder Flatpak.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$(grep -m1 '^VERSION = ' "$SRC/bol/config.py" | cut -d'"' -f2)"
APPID="io.github.wyze3306.BedrockOnLinux"
MANIFEST="$SRC/flatpak/$APPID.yml"
DEV_MANIFEST="$SRC/flatpak/.$APPID.resolved.yml"   # same dir → ../ paths resolve
RTVER="$(grep -m1 'runtime-version:' "$MANIFEST" | tr -d "'\" " | cut -d: -f2)"
OUT="$SRC/dist"
WORK="$OUT/flatpak-build"

if command -v flatpak-builder >/dev/null; then
  FB=(flatpak-builder)
elif flatpak info org.flatpak.Builder >/dev/null 2>&1; then
  # --device=all gives /dev/fuse, which flatpak-builder's rofiles-fuse overlay
  # needs (org.flatpak.Builder ships none → eu-strip 'Permission denied').
  FB=(flatpak run --device=all org.flatpak.Builder)
else
  echo "– Flatpak skipped: no builder. Install one of:"
  echo "    flatpak install -y flathub org.flatpak.Builder      # no root"
  echo "    sudo apt install flatpak-builder                    # Debian/Ubuntu"
  exit 0
fi

mkdir -p "$WORK"

flatpak remote-add --user --if-not-exists flathub \
  https://flathub.org/repo/flathub.flatpakrepo 2>/dev/null || true
flatpak install -y --user --noninteractive flathub \
  org.freedesktop.Platform//"$RTVER" org.freedesktop.Sdk//"$RTVER" 2>/dev/null || \
  echo "  (runtime/SDK pre-install skipped — the builder will fetch them)"

BUILD_FLAGS=(--user --force-clean)

if [[ "${1:-}" == "--release" ]]; then
  BUILD_MANIFEST="$MANIFEST"
else
  # Dev build: swap the app module's pinned git source for the working tree.
  python3 -c 'import yaml' 2>/dev/null || {
    echo "needs PyYAML (e.g. sudo apt install python3-yaml)" >&2; exit 1; }
  python3 - "$MANIFEST" "$DEV_MANIFEST" <<'PY'
import sys, yaml
src, dst = sys.argv[1], sys.argv[2]
with open(src) as f:
    m = yaml.safe_load(f)
# Local builds run flatpak-builder as the real user (not uid-0 in a sandbox),
# so eu-strip can't open Tcl/Tk's 0555-mode .so files read-write. Skip strip
# for the dev build only — the shipped manifest still strips on Flathub CI.
m["build-options"] = {"strip": False, "no-debuginfo": True}
app = m["modules"][-1]
assert app["name"] == "bedrock-on-linux", "app module must be last"
app["sources"] = [
    {"type": "file", "path": "../bedrock-on-linux"},
    {"type": "dir", "path": "../bol", "dest": "bol"},
    {"type": "file", "path": "../data/icon.png", "dest": "data"},
    {"type": "file", "path": "io.github.wyze3306.BedrockOnLinux.desktop",
     "dest": "flatpak"},
]
# Drop the metainfo in dev: flatpak-builder would run 'appstreamcli compose',
# whose /usr/libexec helper isn't on a plain host. The metainfo is validated
# separately with 'appstreamcli validate'.
app["build-commands"] = [c for c in app["build-commands"] if "metainfo" not in c]
with open(dst, "w") as f:
    yaml.safe_dump(m, f, sort_keys=False)
print("dev manifest ->", dst)
PY
  BUILD_MANIFEST="$DEV_MANIFEST"
fi

"${FB[@]}" "${BUILD_FLAGS[@]}" --repo="$WORK/repo" \
  "$WORK/builddir" "$BUILD_MANIFEST"

BUNDLE="$OUT/BedrockOnLinux-${VER}-x86_64.flatpak"
flatpak build-bundle "$WORK/repo" "$BUNDLE" "$APPID"
# drop any stale-version bundles (|| true: grep -v exits 1 when none match)
{ ls "$OUT"/*.flatpak 2>/dev/null | grep -v "${VER}" | xargs -r rm -f; } || true

echo
echo "Built: $BUNDLE"
echo "Install: flatpak install --user $BUNDLE"
echo "Run:     flatpak run $APPID"
