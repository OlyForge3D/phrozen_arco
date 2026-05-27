#!/bin/sh
# KAOS Dev Installer — runs ON the Phrozen Arco printer.
#
# Downloads the latest dev branch as a tarball from GitHub, stages the files
# in the flat layout that phrozen_install.sh expects, then invokes it.
# This keeps phrozen_install.sh as the single source of truth for installation.
#
# One-liner to run from the printer's SSH session:
#   wget -qO- https://raw.githubusercontent.com/OlyForge3D/phrozen_arco/dev/tools/dev_deploy.sh | sh
#
# Or with a specific branch:
#   wget -qO- https://raw.githubusercontent.com/OlyForge3D/phrozen_arco/dev/tools/dev_deploy.sh | sh -s -- --branch dev
#
# Usage (if downloaded first):
#   sh dev_deploy.sh                    # download + install + reboot
#   sh dev_deploy.sh --branch <name>    # use a specific branch
#   sh dev_deploy.sh --download-only    # stage files but don't run installer
#   sh dev_deploy.sh --whatif           # show what would be installed, no changes
#
# Notes:
#   - The installer (phrozen_install.sh) handles all file placement, backups,
#     SAVE_CONFIG preservation, fila_cut_x_pos, permissions, and reboot.
#   - Python changes require a full power-cycle (handled by the installer).
#   - Downloads the entire phrozen_dev/, config/, and install/ directories
#     so new files are picked up automatically without script changes.
#
# POSIX sh compatible (no bash required on the printer).

set -eu

# --- Configuration -----------------------------------------------------------

GITHUB_REPO="OlyForge3D/phrozen_arco"
BRANCH="dev"

# --- Parse arguments ---------------------------------------------------------

DOWNLOAD_ONLY=false
WHATIF=false

while [ $# -gt 0 ]; do
    case "$1" in
        --branch)         shift; BRANCH="$1" ;;
        --download-only)  DOWNLOAD_ONLY=true ;;
        --whatif)         WHATIF=true ;;
        -h|--help)
            sed -n '2,/^$/{ s/^# //; s/^#$//; p }' "$0" 2>/dev/null || echo "Usage: $0 [--branch <name>] [--download-only]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
    shift
done

# --- Helpers -----------------------------------------------------------------

TARBALL_URL="https://github.com/${GITHUB_REPO}/archive/${BRANCH}.tar.gz"
WORK_DIR="/tmp/kaos_dev_deploy_$$"
STAGE_DIR="/tmp/kaos_dev_stage_$$"

info()  { echo "KAOS_DEV: $*"; }
warn()  { echo "KAOS_DEV [WARN]: $*" >&2; }
fatal() { echo "KAOS_DEV [ERROR]: $*" >&2; cleanup; exit 1; }

cleanup() {
    rm -rf "$WORK_DIR" "$STAGE_DIR" 2>/dev/null || true
}
trap cleanup EXIT

# --- Preflight ---------------------------------------------------------------

info "=== KAOS Dev Installer ==="
info "Repo:   ${GITHUB_REPO}"
info "Branch: ${BRANCH}"
if $WHATIF; then
    info "Mode:   --whatif (no changes will be made)"
fi
echo ""

# --- Download and extract tarball --------------------------------------------

mkdir -p "$WORK_DIR" "$STAGE_DIR/kaos"

info "Downloading branch tarball..."
TARBALL="$WORK_DIR/repo.tar.gz"

if command -v wget >/dev/null 2>&1; then
    wget -q -O "$TARBALL" "$TARBALL_URL" || fatal "Failed to download tarball. Check branch name and network."
elif command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$TARBALL" "$TARBALL_URL" || fatal "Failed to download tarball. Check branch name and network."
else
    fatal "Neither wget nor curl found. Cannot download files."
fi

info "Extracting..."
tar -xzf "$TARBALL" -C "$WORK_DIR" || fatal "Failed to extract tarball."

# Find the extracted repo root (GitHub names it <repo>-<branch-with-slashes-as-dashes>/)
REPO_DIR=$(find "$WORK_DIR" -maxdepth 1 -type d ! -path "$WORK_DIR" | head -1)
[ -d "$REPO_DIR" ] || fatal "Could not find extracted repo directory."
info "Extracted to: $REPO_DIR"

# Validate expected directories exist
[ -d "$REPO_DIR/phrozen_dev" ] || fatal "Missing phrozen_dev/ in downloaded repo."
[ -d "$REPO_DIR/config" ]      || fatal "Missing config/ in downloaded repo."
[ -d "$REPO_DIR/install" ]     || fatal "Missing install/ in downloaded repo."

# --- Stage files in flat installer layout ------------------------------------
#
# phrozen_install.sh expects SOURCE_DIR (its own directory) to contain:
#   *.py                     (Python extras, flat)
#   kaos.cfg, printer.cfg, printer_gcode_macro.cfg  (top-level configs, flat)
#   kaos/*.cfg               (split KAOS configs)
#   phrozen_install.sh       (universal installer)

info "Staging files..."

# All top-level files from phrozen_dev/ → stage root
# serial-screen/ subdirectory is excluded (deployed separately by installer)
find "$REPO_DIR/phrozen_dev" -maxdepth 1 -type f ! -name '.DS_Store' -exec cp -f {} "$STAGE_DIR/" \;

# Top-level config files → stage root
cp -f "$REPO_DIR"/config/*.cfg "$STAGE_DIR/" 2>/dev/null || warn "No .cfg files in config/"

# Split kaos config files → stage kaos/
if [ -d "$REPO_DIR/config/kaos" ]; then
    cp -f "$REPO_DIR"/config/kaos/*.cfg "$STAGE_DIR/kaos/" 2>/dev/null || warn "No .cfg files in config/kaos/"
fi

# Install scripts → stage root
cp -f "$REPO_DIR"/install/phrozen_install*.sh "$STAGE_DIR/" 2>/dev/null || fatal "No installer scripts in install/"
chmod +x "$STAGE_DIR"/phrozen_install*.sh

info "Files staged in $STAGE_DIR"
echo ""

# Show what was staged
info "Staged contents:"
ls -la "$STAGE_DIR"/ 2>/dev/null | while read -r line; do info "  $line"; done
if [ -d "$STAGE_DIR/kaos" ]; then
    info "  kaos/:"
    ls "$STAGE_DIR/kaos/" 2>/dev/null | while read -r f; do info "    $f"; done
fi
echo ""

# --- Invoke the installer ----------------------------------------------------

if $DOWNLOAD_ONLY; then
    info "Download-only mode. Files staged at: $STAGE_DIR"
    info "To install manually:  sh $STAGE_DIR/phrozen_install.sh"
    # Don't cleanup — leave files in place
    trap - EXIT
    exit 0
fi

info "Running phrozen_install.sh..."
echo ""
if $WHATIF; then
    exec "$STAGE_DIR/phrozen_install.sh" --whatif
else
    exec "$STAGE_DIR/phrozen_install.sh"
fi
