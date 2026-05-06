#!/usr/bin/env bash
# Build a KAOS release zip in Phrozen's USB-update layout.
#
# Tag / version format:
#   <kaos>-f<firmware>     e.g. 0.9.5-f1.9.9, 1.0.0-rc1-f1.9.9
#
# The combined tag bakes the firmware version into the release: a release
# is an explicit promise that this KAOS build targets and requires the
# named firmware. CI rejects tags that don't match this format.
#
# Usage:
#   tools/build_release.sh                                # auto from `git describe --tags`
#   tools/build_release.sh <tag>                          # parse <kaos>-f<firmware>
#   tools/build_release.sh <kaos> <fw>                    # explicit (manual override)
#
# Examples:
#   tools/build_release.sh                                # uses latest tag
#   tools/build_release.sh 0.9.5-f1.9.9                   # → KAOS=0.9.5, FW=1.9.9
#   tools/build_release.sh 0.9.5 1.9.9                    # explicit, skips tag-format check
#
# Output: dist/Arco_FW_V<fw_no_dots>_KAOS_<kaos>.zip
# Inside: Arco_FW_V<fw_no_dots>_KAOS_<kaos>/phrozen_dev/<flat install layout>

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
    REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
cd "$REPO_ROOT"

OUTPUT_DIR="${OUTPUT_DIR:-dist}"

# parse_release_tag <tag>
# Strict format: <kaos>-f<firmware>, where firmware is dotted-numeric.
# Sets PARSED_KAOS_VERSION + PARSED_FW_VERSION on success, returns 1 on
# failure (with no side effect).
parse_release_tag() {
    local tag="$1"
    if [[ ! "$tag" =~ ^(.+)-f([0-9]+(\.[0-9]+)*)$ ]]; then
        return 1
    fi
    PARSED_KAOS_VERSION="${BASH_REMATCH[1]}"
    PARSED_FW_VERSION="${BASH_REMATCH[2]}"
    return 0
}

fail_tag_format() {
    cat >&2 <<EOF
ERROR: release tag '$1' does not match the required format.

Required format:  <kaos>-f<firmware>
Examples:         0.9.5-f1.9.9      1.0.0-rc1-f1.9.9      0.10-f2.0.0

The firmware portion (after '-f') must be a dotted numeric string.
The KAOS portion may contain dots, letters, and hyphens.

Tag the release like:
    git tag 0.9.5-f1.9.9
    git push origin 0.9.5-f1.9.9
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

PKG_ROOT="$STAGE_DIR/$PACKAGE_NAME"
PHROZEN_DEV="$PKG_ROOT/phrozen_dev"
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
Release tag:         ${KAOS_VERSION}-f${FW_VERSION}
Built (UTC):         $(date -u +%Y-%m-%dT%H:%M:%SZ)
Git revision:        $(git describe --tags --always --dirty 2>/dev/null || echo "unknown")
Git branch:          $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
EOF

# Build the zip via Python's zipfile module (avoids the `zip` binary
# dependency on minimal CI images).
mkdir -p "$OUTPUT_DIR"
ZIP_PATH="$REPO_ROOT/$OUTPUT_DIR/${PACKAGE_NAME}.zip"
python3 - "$STAGE_DIR" "$PACKAGE_NAME" "$ZIP_PATH" <<'PY'
import os, sys, zipfile
stage_dir, pkg_name, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
src_root = os.path.join(stage_dir, pkg_name)
with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
    for dirpath, _, filenames in os.walk(src_root):
        for f in sorted(filenames):
            full = os.path.join(dirpath, f)
            arc = os.path.relpath(full, stage_dir)
            z.write(full, arc)
PY

echo ">> Built: $ZIP_PATH"
ls -la "$ZIP_PATH"
echo
echo ">> Contents:"
python3 -m zipfile -l "$ZIP_PATH"
