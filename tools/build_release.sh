#!/usr/bin/env bash
# Build a KAOS release zip in Phrozen's USB-update layout.
#
# Tag / version format:
#   <firmware>-k<kaos>     e.g. 1.9.9-k0.9.5, 1.9.9-k1.0.0-rc1
#
# Order mirrors the output zip filename Arco_FW_V<fw>_KAOS_<kaos>.zip —
# firmware first, then KAOS. The combined tag bakes the firmware version
# into the release: a release is an explicit promise that this KAOS build
# targets and requires the named firmware. CI rejects tags that don't
# match this format.
#
# Usage:
#   tools/build_release.sh                                # auto from `git describe --tags`
#   tools/build_release.sh <tag>                          # parse <firmware>-k<kaos>
#   tools/build_release.sh <kaos> <fw>                    # explicit (manual override)
#
# Examples:
#   tools/build_release.sh                                # uses latest tag
#   tools/build_release.sh 1.9.9-k0.9.5                   # → KAOS=0.9.5, FW=1.9.9
#   tools/build_release.sh 0.9.5 1.9.9                    # explicit, skips tag-format check
#
# Output: dist/Arco_FW_V<fw_no_dots>_KAOS_<kaos>.zip
#
# Layout (nested zip — required by the Phrozen updater):
#   <PACKAGE>.zip                       outer (distribution wrapper)
#   └── phrozen_dev/
#       └── phrozen_dev.zip             inner (what the updater looks for)
#           └── phrozen_dev/             (folder inside the inner zip)
#               └── <flat install layout>   (dev.py, kaos.cfg, kaos/*.cfg, etc.)
#
# The user unzips the outer, copies the resulting phrozen_dev/ folder
# (which contains phrozen_dev.zip) to a USB stick root, plugs it in,
# and the Phrozen updater finds phrozen_dev/phrozen_dev.zip and applies it.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
    REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
cd "$REPO_ROOT"

OUTPUT_DIR="${OUTPUT_DIR:-dist}"

# parse_release_tag <tag>
# Strict format: <firmware>-k<kaos>, where firmware is dotted-numeric.
# Sets PARSED_FW_VERSION + PARSED_KAOS_VERSION on success, returns 1 on
# failure (with no side effect).
#
# v/V prefixes are explicitly rejected on both portions. Use plain numeric
# versions: 0.9.5 not v0.9.5, 1.9.9 not V1.9.9.
parse_release_tag() {
    local tag="$1"
    if [[ ! "$tag" =~ ^([0-9]+(\.[0-9]+)*)-k(.+)$ ]]; then
        return 1
    fi
    local fw="${BASH_REMATCH[1]}"
    local kaos="${BASH_REMATCH[3]}"
    if [[ "$kaos" =~ ^[vV] ]]; then
        return 1
    fi
    PARSED_FW_VERSION="$fw"
    PARSED_KAOS_VERSION="$kaos"
    return 0
}

fail_tag_format() {
    cat >&2 <<EOF
ERROR: release tag '$1' does not match the required format.

Required format:  <firmware>-k<kaos>
Examples:         1.9.9-k0.9.5      1.9.9-k1.0.0-rc1      2.0.0-k0.10

Rules:
  - firmware portion (before '-k') must be a dotted numeric string
  - KAOS portion may contain dots, letters, hyphens
  - NO 'v' or 'V' prefix on either portion (use 0.9.5, NOT v0.9.5)

Tag the release like:
    git tag 1.9.9-k0.9.5
    git push origin 1.9.9-k0.9.5
EOF
    exit 2
}

case "$#" in
    0)
        # Auto-derive from git. Must match the tag format.
        DESC="$(git describe --tags --always --dirty 2>/dev/null || echo "")"
        [ -n "$DESC" ] || { echo "ERROR: no git tag found and no version arg passed" >&2; exit 2; }
        if ! parse_release_tag "$DESC"; then
            fail_tag_format "$DESC"
        fi
        KAOS_VERSION="$PARSED_KAOS_VERSION"
        FW_VERSION="$PARSED_FW_VERSION"
        ;;
    1)
        # Single arg: must match the tag format.
        if ! parse_release_tag "$1"; then
            fail_tag_format "$1"
        fi
        KAOS_VERSION="$PARSED_KAOS_VERSION"
        FW_VERSION="$PARSED_FW_VERSION"
        ;;
    2)
        # Two args: explicit manual override (skips tag-format validation).
        # Useful for local builds where the user is iterating without tagging.
        KAOS_VERSION="$1"
        FW_VERSION="$2"
        ;;
    *)
        echo "ERROR: too many arguments. Pass either <tag> or <kaos> <fw>." >&2
        exit 2
        ;;
esac

FW_VERSION_NODOTS="${FW_VERSION//./}"
PACKAGE_NAME="Arco_FW_V${FW_VERSION_NODOTS}_KAOS_${KAOS_VERSION}"
STAGE_DIR="$(mktemp -d -t kaos-build.XXXXXX)"
trap 'rm -rf "$STAGE_DIR"' EXIT

# Stage layout: phrozen_dev/ at the zip root with all install files flattened
# inside. No outer wrapper folder — the user puts this phrozen_dev/ folder
# directly on a USB stick root and the printer runs the install from there.
PHROZEN_DEV="$STAGE_DIR/phrozen_dev"
mkdir -p "$PHROZEN_DEV/kaos" "$PHROZEN_DEV/lang"

echo ">> KAOS version:    $KAOS_VERSION"
echo ">> Target firmware: $FW_VERSION"
echo ">> Package:         $PACKAGE_NAME"

# Python module + language files
cp phrozen_dev/dev.py phrozen_dev/kaos_logging.py phrozen_dev/kaos_translations.py "$PHROZEN_DEV/"
cp phrozen_dev/lang/*.py "$PHROZEN_DEV/lang/"

# Top-level klipper config files
cp config/kaos.cfg config/printer.cfg config/printer_gcode_macro.cfg "$PHROZEN_DEV/"

# Split kaos/ cfg files
cp config/kaos/*.cfg "$PHROZEN_DEV/kaos/"

# Install scripts (default + per-board variants), executable
cp install/phrozen_install*.sh "$PHROZEN_DEV/"
chmod +x "$PHROZEN_DEV"/phrozen_install*.sh

# Version stamp file. Recorded both as the parsed parts and the original tag
# form so anyone reading it on the printer can see exactly what shipped.
cat > "$PHROZEN_DEV/KAOS_VERSION.txt" <<EOF
KAOS version:        ${KAOS_VERSION}
Target firmware:     ${FW_VERSION}
Release tag:         ${FW_VERSION}-k${KAOS_VERSION}
Built (UTC):         $(date -u +%Y-%m-%dT%H:%M:%SZ)
Git revision:        $(git describe --tags --always --dirty 2>/dev/null || echo "unknown")
Git branch:          $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
EOF

# Step 1: build the INNER zip (phrozen_dev.zip).
# Contains phrozen_dev/<flat install layout>. This is the zip the Phrozen
# updater unpacks on the printer to apply the update.
INNER_ZIP="$STAGE_DIR/phrozen_dev.zip"
python3 - "$STAGE_DIR" "$INNER_ZIP" <<'PY'
import os, sys, zipfile
stage_dir, out_path = sys.argv[1], sys.argv[2]
src_root = os.path.join(stage_dir, "phrozen_dev")
with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
    for dirpath, dirnames, filenames in os.walk(src_root):
        # Explicit directory entries (mirrors what the reference sample has).
        rel = os.path.relpath(dirpath, stage_dir)
        z.writestr(rel.replace(os.sep, "/") + "/", "")
        for f in sorted(filenames):
            full = os.path.join(dirpath, f)
            arc = os.path.relpath(full, stage_dir).replace(os.sep, "/")
            z.write(full, arc)
PY

# Step 2: build the OUTER zip — the distribution wrapper.
# Contains phrozen_dev/phrozen_dev.zip (the inner zip from step 1, inside a
# phrozen_dev/ folder). When the user unzips this they get a phrozen_dev/
# folder ready to drop on a USB stick.
OUTER_STAGE="$STAGE_DIR/_outer"
mkdir -p "$OUTER_STAGE/phrozen_dev"
mv "$INNER_ZIP" "$OUTER_STAGE/phrozen_dev/phrozen_dev.zip"

mkdir -p "$OUTPUT_DIR"
ZIP_PATH="$REPO_ROOT/$OUTPUT_DIR/${PACKAGE_NAME}.zip"
python3 - "$OUTER_STAGE" "$ZIP_PATH" <<'PY'
import os, sys, zipfile
stage_dir, out_path = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("phrozen_dev/", "")
    z.write(os.path.join(stage_dir, "phrozen_dev", "phrozen_dev.zip"),
            "phrozen_dev/phrozen_dev.zip")
PY

echo ">> Built: $ZIP_PATH"
ls -la "$ZIP_PATH"
echo
echo ">> Outer contents:"
python3 -m zipfile -l "$ZIP_PATH"
echo
echo ">> Inner contents (phrozen_dev/phrozen_dev.zip):"
python3 - "$ZIP_PATH" <<'PY'
import sys, zipfile, io
with zipfile.ZipFile(sys.argv[1]) as outer:
    with outer.open("phrozen_dev/phrozen_dev.zip") as f:
        data = f.read()
with zipfile.ZipFile(io.BytesIO(data)) as inner:
    for i in inner.infolist():
        print(f"  {i.file_size:>8}  {i.filename}")
PY
