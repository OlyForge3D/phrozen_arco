#!/bin/sh

# KAOS / Phrozen installer for ARCO300-MKS-RK3328-STM32F407VET6-I16
# POSIX sh compatible.
# Purpose: install KAOS Python files, language files, top-level cfg files,
# and split /config/kaos/*.cfg files with loud diagnostics and verification.

set -u

TARGET_DIR="/home/mks/klipper/klippy/extras/phrozen_dev"
CONFIG_DIR="/home/mks/printer_data/config"
timestamp=$(date +%Y%m%d_%H%M%S)

log() {
    echo "KAOS_INSTALL: $*"
}

fail() {
    echo "KAOS_INSTALL_ERROR: $*" >&2
    exit 1
}

backup_file() {
    file="$1"
    if [ -f "$file" ]; then
        if [ ! -f "$file.bak" ]; then
            log "Backing up $file -> $file.bak"
            cp -f "$file" "$file.bak" || fail "Failed to backup $file"
        else
            log "Backing up $file -> $file.$timestamp.bak"
            cp -f "$file" "$file.$timestamp.bak" || fail "Failed to backup $file"
        fi
    fi
}

# Work out where the update package actually landed.
# The Phrozen updater may stage the package differently depending on firmware/model.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)
SOURCE_DIR=""

for candidate in \
    "$SCRIPT_DIR" \
    "/tmp/phrozen_dev" \
    "/tmp/update/phrozen_dev" \
    "/tmp/update" \
    "/home/mks/phrozen_dev" \
    "/home/mks/update/phrozen_dev" \
    "/home/mks/update"
do
    if [ -n "$candidate" ] && [ -f "$candidate/dev.py" ]; then
        SOURCE_DIR="$candidate"
        break
    fi
done

[ -n "$SOURCE_DIR" ] || fail "Could not find source package directory containing dev.py"

log "script started"
log "running as user: $(whoami 2>/dev/null || echo unknown)"
log "SOURCE_DIR=$SOURCE_DIR"
log "TARGET_DIR=$TARGET_DIR"
log "CONFIG_DIR=$CONFIG_DIR"

# Validate source package before changing live files.
[ -f "$SOURCE_DIR/dev.py" ] || fail "Missing source file: $SOURCE_DIR/dev.py"
[ -f "$SOURCE_DIR/kaos_logging.py" ] || fail "Missing source file: $SOURCE_DIR/kaos_logging.py"
[ -f "$SOURCE_DIR/kaos_translations.py" ] || fail "Missing source file: $SOURCE_DIR/kaos_translations.py"
[ -d "$SOURCE_DIR/lang" ] || fail "Missing source directory: $SOURCE_DIR/lang"
[ -f "$SOURCE_DIR/kaos.cfg" ] || fail "Missing source file: $SOURCE_DIR/kaos.cfg"
[ -d "$SOURCE_DIR/kaos" ] || fail "Missing source directory: $SOURCE_DIR/kaos"
[ -f "$SOURCE_DIR/printer.cfg" ] || fail "Missing source file: $SOURCE_DIR/printer.cfg"
[ -f "$SOURCE_DIR/printer_gcode_macro.cfg" ] || fail "Missing source file: $SOURCE_DIR/printer_gcode_macro.cfg"

# Make wildcard failures explicit. Without this, cp may fail later with less useful context.
set -- "$SOURCE_DIR"/kaos/*.cfg
[ -f "$1" ] || fail "No .cfg files found in source directory: $SOURCE_DIR/kaos"
set -- "$SOURCE_DIR"/lang/*.py
[ -f "$1" ] || fail "No .py files found in source directory: $SOURCE_DIR/lang"

# Validate destination paths and permissions before copying.
[ -d "$TARGET_DIR" ] || fail "Target directory does not exist: $TARGET_DIR"
[ -d "$CONFIG_DIR" ] || fail "Config directory does not exist: $CONFIG_DIR"

log "checking write access to $TARGET_DIR"
touch "$TARGET_DIR/.kaos_write_test" || fail "Cannot write to target directory: $TARGET_DIR"
rm -f "$TARGET_DIR/.kaos_write_test" || fail "Cannot remove write-test file from: $TARGET_DIR"

log "checking write/create access to $CONFIG_DIR"
touch "$CONFIG_DIR/.kaos_write_test" || fail "Cannot write to config directory: $CONFIG_DIR"
rm -f "$CONFIG_DIR/.kaos_write_test" || fail "Cannot remove write-test file from: $CONFIG_DIR"
mkdir -p "$CONFIG_DIR/.kaos_mkdir_test" || fail "Cannot create directories in config directory: $CONFIG_DIR"
rmdir "$CONFIG_DIR/.kaos_mkdir_test" || fail "Cannot remove mkdir-test directory from: $CONFIG_DIR"

# Breadcrumb file so we can prove this script actually ran.
echo "KAOS install started at $(date)" > "$CONFIG_DIR/kaos_install_ran.txt" || fail "Could not write breadcrumb file"
echo "SOURCE_DIR=$SOURCE_DIR" >> "$CONFIG_DIR/kaos_install_ran.txt"
echo "TARGET_DIR=$TARGET_DIR" >> "$CONFIG_DIR/kaos_install_ran.txt"
echo "CONFIG_DIR=$CONFIG_DIR" >> "$CONFIG_DIR/kaos_install_ran.txt"

# Backup existing files without removing working copies first.
backup_file "$TARGET_DIR/dev.py"
backup_file "$TARGET_DIR/kaos_logging.py"
backup_file "$TARGET_DIR/kaos_translations.py"
backup_file "$CONFIG_DIR/printer.cfg"
backup_file "$CONFIG_DIR/printer_gcode_macro.cfg"
backup_file "$CONFIG_DIR/kaos.cfg"

# Copy patched Python files.
log "copying Python files"
cp -f "$SOURCE_DIR/dev.py" "$TARGET_DIR/dev.py" || fail "Failed to copy dev.py"
cp -f "$SOURCE_DIR/kaos_logging.py" "$TARGET_DIR/kaos_logging.py" || fail "Failed to copy kaos_logging.py"
cp -f "$SOURCE_DIR/kaos_translations.py" "$TARGET_DIR/kaos_translations.py" || fail "Failed to copy kaos_translations.py"

# Copy language files.
log "creating/copying language directory"
mkdir -p "$TARGET_DIR/lang" || fail "Failed to create $TARGET_DIR/lang"
cp -a "$SOURCE_DIR/lang/." "$TARGET_DIR/lang/" || fail "Failed to copy language files"

# Copy KAOS split cfg files BEFORE printer.cfg.
# This prevents printer.cfg from being installed while its [include kaos/*.cfg] target is missing.
log "creating split KAOS config directory: $CONFIG_DIR/kaos"
mkdir -p "$CONFIG_DIR/kaos" || fail "Failed to create $CONFIG_DIR/kaos"
[ -d "$CONFIG_DIR/kaos" ] || fail "Directory was not created: $CONFIG_DIR/kaos"

log "copying kaos.cfg"
cp -f "$SOURCE_DIR/kaos.cfg" "$CONFIG_DIR/kaos.cfg" || fail "Failed to copy kaos.cfg"

log "copying split KAOS cfg files"
cp -f "$SOURCE_DIR"/kaos/*.cfg "$CONFIG_DIR/kaos/" || fail "Failed to copy split KAOS cfg files"

# Copy main config files last.
log "copying main printer config files"
cp -f "$SOURCE_DIR/printer.cfg" "$CONFIG_DIR/printer.cfg" || fail "Failed to copy printer.cfg"
cp -f "$SOURCE_DIR/printer_gcode_macro.cfg" "$CONFIG_DIR/printer_gcode_macro.cfg" || fail "Failed to copy printer_gcode_macro.cfg"

# Apply permissions.
log "applying permissions"
chmod 644 "$TARGET_DIR/dev.py" || fail "chmod failed for dev.py"
chmod 644 "$TARGET_DIR/kaos_logging.py" || fail "chmod failed for kaos_logging.py"
chmod 644 "$TARGET_DIR/kaos_translations.py" || fail "chmod failed for kaos_translations.py"
chmod 755 "$TARGET_DIR/lang" || fail "chmod failed for lang directory"
chmod 644 "$TARGET_DIR"/lang/*.py || fail "chmod failed for language py files"
chmod 755 "$CONFIG_DIR/kaos" || fail "chmod failed for KAOS config directory"
chmod 644 "$CONFIG_DIR"/kaos/*.cfg || fail "chmod failed for split KAOS cfg files"
chmod 644 "$CONFIG_DIR/kaos.cfg" || fail "chmod failed for kaos.cfg"
chmod 644 "$CONFIG_DIR/printer.cfg" || fail "chmod failed for printer.cfg"
chmod 644 "$CONFIG_DIR/printer_gcode_macro.cfg" || fail "chmod failed for printer_gcode_macro.cfg"
chmod 644 "$CONFIG_DIR/kaos_install_ran.txt" || fail "chmod failed for breadcrumb file"

# Verify installed result.
log "verifying install"
[ -f "$TARGET_DIR/dev.py" ] || fail "Verify failed: missing $TARGET_DIR/dev.py"
[ -f "$TARGET_DIR/kaos_logging.py" ] || fail "Verify failed: missing $TARGET_DIR/kaos_logging.py"
[ -f "$TARGET_DIR/kaos_translations.py" ] || fail "Verify failed: missing $TARGET_DIR/kaos_translations.py"
[ -d "$TARGET_DIR/lang" ] || fail "Verify failed: missing $TARGET_DIR/lang"
[ -d "$CONFIG_DIR/kaos" ] || fail "Verify failed: missing $CONFIG_DIR/kaos"
[ -f "$CONFIG_DIR/kaos.cfg" ] || fail "Verify failed: missing $CONFIG_DIR/kaos.cfg"
[ -f "$CONFIG_DIR/printer.cfg" ] || fail "Verify failed: missing $CONFIG_DIR/printer.cfg"
[ -f "$CONFIG_DIR/printer_gcode_macro.cfg" ] || fail "Verify failed: missing $CONFIG_DIR/printer_gcode_macro.cfg"

cfg_count=$(find "$CONFIG_DIR/kaos" -maxdepth 1 -type f -name '*.cfg' | wc -l)
lang_count=$(find "$TARGET_DIR/lang" -maxdepth 1 -type f -name '*.py' | wc -l)

log "installed $cfg_count split KAOS cfg files"
log "installed $lang_count language py files"

[ "$cfg_count" -gt 0 ] || fail "Verify failed: no split KAOS cfg files installed in $CONFIG_DIR/kaos"
[ "$lang_count" -gt 0 ] || fail "Verify failed: no language py files installed in $TARGET_DIR/lang"

{
    echo "KAOS install completed at $(date)"
    echo "cfg_count=$cfg_count"
    echo "lang_count=$lang_count"
} >> "$CONFIG_DIR/kaos_install_ran.txt"

log "KAOS_INSTALL_SUCCESS: KAOS install completed"
exit 0
