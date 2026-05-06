#!/usr/bin/env bash
# Build a KAOS release zip in Phrozen's USB-update layout.
#
# Usage:
#   tools/build_release.sh                          # auto-version from git
#   tools/build_release.sh <kaos_version>           # explicit KAOS version
#   tools/build_release.sh <kaos_version> <fw_ver>  # override firmware target
#
# Examples:
#   tools/build_release.sh                          # → Arco_FW_V199_KAOS_<git-describe>.zip
#   tools/build_release.sh 0.95                     # → Arco_FW_V199_KAOS_0.95.zip
#   tools/build_release.sh v1.0 1.9.9               # → Arco_FW_V199_KAOS_1.0.zip
#
# Output: dist/Arco_FW_V<fw_no_dots>_KAOS_<kaos>.zip
#
# Layout inside the zip:
#   Arco_FW_V<fw>_KAOS_<kaos>/
#   └── phrozen_dev/
#       ├── dev.py, kaos_logging.py, kaos_translations.py
#       ├── lang/*.py
#       ├── kaos.cfg, printer.cfg, printer_gcode_macro.cfg
#       ├── kaos/*.cfg
#       └── phrozen_install*.sh
#
# To install: unzip on a PC, copy the inner phrozen_dev/ folder to a USB stick
# root, plug into the printer, run the Phrozen update flow.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
    REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
cd "$REPO_ROOT"

KAOS_VERSION_RAW="${1:-$(git describe --tags --always --dirty 2>/dev/null || echo "dev")}"
FW_VERSION_RAW="${2:-1.9.9}"
OUTPUT_DIR="${OUTPUT_DIR:-dist}"

# Normalize: strip leading 'v', strip dots from firmware version (1.9.9 → 199).
KAOS_VERSION="${KAOS_VERSION_RAW#v}"
FW_VERSION="${FW_VERSION_RAW#v}"
FW_VERSION_NODOTS="${FW_VERSION//./}"

PACKAGE_NAME="Arco_FW_V${FW_VERSION_NODOTS}_KAOS_${KAOS_VERSION}"
STAGE_DIR="$(mktemp -d -t kaos-build.XXXXXX)"
trap 'rm -rf "$STAGE_DIR"' EXIT

PKG_ROOT="$STAGE_DIR/$PACKAGE_NAME"
PHROZEN_DEV="$PKG_ROOT/phrozen_dev"
mkdir -p "$PHROZEN_DEV/kaos" "$PHROZEN_DEV/lang"

echo ">> Staging package: $PACKAGE_NAME"

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

# Version stamp file (sits next to the install scripts; readable on the printer
# after install via cat /tmp/phrozen_dev/KAOS_VERSION.txt or similar).
cat > "$PHROZEN_DEV/KAOS_VERSION.txt" <<EOF
KAOS version:        ${KAOS_VERSION}
Target firmware:     ${FW_VERSION}
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
