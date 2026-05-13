#!/bin/sh
# KAOS_VERSION: v0.95

# KAOS / Phrozen installer for ARCO300-MKS-RK3328-STM32F407VET6-I16
# POSIX sh compatible.
# Purpose: install KAOS Python files, language files, top-level cfg files,
# and split /config/kaos/*.cfg files with loud diagnostics and verification.

set -u

TARGET_DIR="/home/mks/klipper/klippy/extras/phrozen_dev"
CONFIG_DIR="/home/mks/printer_data/config"
INSTALL_LOG="$CONFIG_DIR/kaos_install.log"
SAVE_CONFIG_TMP="/tmp/kaos_save_config_$$.log"
SOFT_SHUTDOWN_LOG_TMP="/tmp/kaos_soft_shutdown_$$.log"
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


soft_log() {
    log "$*"
    echo "$*" >> "$SOFT_SHUTDOWN_LOG_TMP" 2>/dev/null || true
}

disable_soft_shutdown() {
    soft_log "soft_shutdown_disable_begin"
    soft_log "soft_shutdown_target=/root/soft_shutdown.sh"

    # Stop any currently running soft shutdown script.
    if pkill -f '/root/soft_shutdown.sh' 2>/dev/null; then
        soft_log "soft_shutdown_process_status=killed"
    else
        soft_log "soft_shutdown_process_status=not_running_or_not_found"
    fi

    # Disable startup references from rc.local if present, but leave the line visible for recovery.
    if [ -f /etc/rc.local ]; then
        if grep -q '/root/soft_shutdown.sh' /etc/rc.local 2>/dev/null; then
            sed -i '\|/root/soft_shutdown.sh| { /^[[:space:]]*#/! s|^|# KAOS disabled: |; }' /etc/rc.local 2>/dev/null || true
            soft_log "soft_shutdown_rc_local_status=reference_commented"
        else
            soft_log "soft_shutdown_rc_local_status=no_reference"
        fi
    else
        soft_log "soft_shutdown_rc_local_status=not_present"
    fi

    # Disable and mask any systemd unit that directly references soft_shutdown.sh.
    soft_shutdown_systemd_units=0
    if command -v systemctl >/dev/null 2>&1; then
        grep -rl '/root/soft_shutdown.sh' /etc/systemd/system /lib/systemd/system 2>/dev/null | while IFS= read -r unitfile; do
            unit=$(basename "$unitfile")
            soft_shutdown_systemd_units=1
            soft_log "soft_shutdown_systemd_unit_found=$unit"
            systemctl stop "$unit" 2>/dev/null || true
            systemctl disable "$unit" 2>/dev/null || true
            systemctl mask "$unit" 2>/dev/null || true
            soft_log "soft_shutdown_systemd_unit_status=$unit stopped_disabled_masked"
        done
        #systemctl daemon-reload 2>/dev/null || true
        soft_log "soft_shutdown_systemd_status=checked"
    else
        soft_log "soft_shutdown_systemd_status=systemctl_not_found"
    fi

    # Leave the script in place for possible recovery, but remove execute permission.
    if [ -f /root/soft_shutdown.sh ]; then
        if chmod a-x /root/soft_shutdown.sh 2>/dev/null; then
            soft_log "soft_shutdown_script_status=present_execute_permission_removed"
        else
            soft_log "soft_shutdown_script_status=present_chmod_failed"
        fi
    else
        soft_log "soft_shutdown_script_status=not_present"
    fi

    soft_log "soft_shutdown_disable_end"
}

# Use the directory containing this installer as the source package directory.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)
SOURCE_DIR="$SCRIPT_DIR"

[ -f "$SOURCE_DIR/dev.py" ] || fail "Could not find source package directory containing dev.py: $SOURCE_DIR"

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

# Install log so we can prove this script actually ran and preserve live values before replacement.
existing_fila_cut_x_pos="NOT_FOUND"
rm -f "$SAVE_CONFIG_TMP"
if [ -f "$CONFIG_DIR/printer.cfg" ]; then
    # Use the same grep pattern proven over SSH, then strip the key/comments/whitespace.
    existing_fila_cut_x_pos=$(grep -m 1 -E '^[[:space:]]*fila_cut_x_pos[[:space:]]*:' "$CONFIG_DIR/printer.cfg" \
        | sed -E 's/^[[:space:]]*fila_cut_x_pos[[:space:]]*:[[:space:]]*//; s/[[:space:]]*[#;].*$//; s/^[[:space:]]+//; s/[[:space:]]+$//')
    [ -n "$existing_fila_cut_x_pos" ] || existing_fila_cut_x_pos="NOT_FOUND"

    # Preserve the existing Klipper SAVE_CONFIG block before printer.cfg is replaced.
    awk '
        found { print; next }
        /^#\*#.*SAVE_CONFIG/ { found=1; print }
    ' "$CONFIG_DIR/printer.cfg" > "$SAVE_CONFIG_TMP"
fi

{
    echo "KAOS install started at $(date)"
    echo "SOURCE_DIR=$SOURCE_DIR"
    echo "TARGET_DIR=$TARGET_DIR"
    echo "CONFIG_DIR=$CONFIG_DIR"
} > "$INSTALL_LOG" || fail "Could not write install log"

# Backup only printer.cfg. Other KAOS files are overwritten directly.
backup_file "$CONFIG_DIR/printer.cfg"

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

# Preserve live printer.cfg values in the freshly deployed printer.cfg.
fila_cut_x_pos_update_status="skipped_NOT_FOUND"
save_config_update_status="skipped_NOT_FOUND"

if [ "$existing_fila_cut_x_pos" != "NOT_FOUND" ]; then
    if grep -qE '^[[:space:]]*fila_cut_x_pos[[:space:]]*:' "$CONFIG_DIR/printer.cfg"; then
        PRINTER_CFG_TMP="/tmp/kaos_printer_cfg_$$.tmp"
        sed -E "s|^[[:space:]]*fila_cut_x_pos[[:space:]]*:.*|fila_cut_x_pos: $existing_fila_cut_x_pos|"             "$CONFIG_DIR/printer.cfg" > "$PRINTER_CFG_TMP"             || fail "Failed to prepare preserved fila_cut_x_pos update"
        mv -f "$PRINTER_CFG_TMP" "$CONFIG_DIR/printer.cfg"             || fail "Failed to apply preserved fila_cut_x_pos to printer.cfg"

        if grep -qE "^[[:space:]]*fila_cut_x_pos[[:space:]]*:[[:space:]]*$existing_fila_cut_x_pos([[:space:]]*([#;].*)?)?$" "$CONFIG_DIR/printer.cfg"; then
            fila_cut_x_pos_update_status="updated"
            log "preserved fila_cut_x_pos=$existing_fila_cut_x_pos in deployed printer.cfg"
        else
            fila_cut_x_pos_update_status="update_verify_failed"
            log "WARNING: fila_cut_x_pos update attempted but verify failed"
        fi
    else
        fila_cut_x_pos_update_status="target_key_not_found"
        log "WARNING: could not preserve fila_cut_x_pos because deployed printer.cfg has no fila_cut_x_pos key"
    fi
else
    fila_cut_x_pos_update_status="source_value_not_found"
    log "WARNING: could not preserve fila_cut_x_pos because source value was not found"
fi

if [ -s "$SAVE_CONFIG_TMP" ]; then
    PRINTER_CFG_TMP="/tmp/kaos_printer_cfg_save_config_$$.tmp"
    awk '
        /^#\*#.*SAVE_CONFIG/ { skip=1; next }
        skip == 0 { print }
    ' "$CONFIG_DIR/printer.cfg" > "$PRINTER_CFG_TMP" || fail "Failed to prepare printer.cfg for SAVE_CONFIG preservation"
    {
        echo ""
        cat "$SAVE_CONFIG_TMP"
    } >> "$PRINTER_CFG_TMP" || fail "Failed to append existing SAVE_CONFIG block to printer.cfg"
    mv -f "$PRINTER_CFG_TMP" "$CONFIG_DIR/printer.cfg" || fail "Failed to preserve existing SAVE_CONFIG block in printer.cfg"
    save_config_update_status="updated"
    log "preserved existing SAVE_CONFIG block in deployed printer.cfg"
fi


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
chmod 644 "$INSTALL_LOG" || fail "chmod failed for install log"

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

disable_soft_shutdown

{
    echo "KAOS install completed at $(date)"
    echo "cfg_count=$cfg_count"
    echo "lang_count=$lang_count"
    echo ""
    echo "existing_fila_cut_x_pos=$existing_fila_cut_x_pos"
    echo "fila_cut_x_pos_update_status=$fila_cut_x_pos_update_status"
    echo "save_config_update_status=$save_config_update_status"
    echo ""
    echo "existing_save_config_block_begin"
    if [ -s "$SAVE_CONFIG_TMP" ]; then
        cat "$SAVE_CONFIG_TMP"
    else
        echo "NOT_FOUND"
    fi
    echo "existing_save_config_block_end"
    echo ""
    echo "soft_shutdown_disable_log_begin"
    if [ -s "$SOFT_SHUTDOWN_LOG_TMP" ]; then
        cat "$SOFT_SHUTDOWN_LOG_TMP"
    else
        echo "NOT_RUN"
    fi
    echo "soft_shutdown_disable_log_end"
    echo ""
    echo "KAOS_INSTALL_SUCCESS: KAOS install completed"
    echo ""
    echo "Rebooting printer after KAOS install at $(date)"
} >> "$INSTALL_LOG"

rm -f "$SAVE_CONFIG_TMP"
rm -f "$SOFT_SHUTDOWN_LOG_TMP"

sync
sleep 2
reboot
