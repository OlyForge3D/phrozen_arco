#!/bin/sh
# KAOS_VERSION: v0.95

# KAOS / Phrozen Arco installer (universal — auto-detects board variant)
# POSIX sh compatible.
# Purpose: install KAOS Python files and top-level cfg files,
# and split /config/kaos/*.cfg files with loud diagnostics and verification.

set -u

KLIPPER_DIR="/home/mks/klipper"
TARGET_DIR="$KLIPPER_DIR/klippy/extras/phrozen_dev"
CONFIG_DIR="/home/mks/printer_data/config"
INSTALL_LOG="$CONFIG_DIR/kaos_install.log"

# Pinned commits — tested versions for the Phrozen Arco.
# Moonraker's update_manager will refuse to update beyond these.
KLIPPER_PIN="e6ef48cd"   # v0.11.0-122 (matches MCU firmware; max_accel_to_decel era)
MOONRAKER_PIN="71517b255dc43c7e99fbc269d34deba9b30dd9f6"  # v0.8.0-306
SAVE_CONFIG_TMP="/tmp/kaos_save_config_$$.log"
timestamp=$(date +%Y%m%d_%H%M%S)

# --- WhatIf mode -------------------------------------------------------------
# When --whatif is passed, no files are modified. The script runs all validation
# and reports what it WOULD do.

WHATIF=false
for _arg in "$@"; do
    case "$_arg" in
        --whatif) WHATIF=true ;;
    esac
done

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

UPDATE_MGR_LOG_TMP="/tmp/kaos_update_mgr_$$.log"
MOONRAKER_CONF="$CONFIG_DIR/moonraker.conf"

# --- Manage Moonraker update_manager sections ---------------------------------
# Ensures pinned_commit sections exist for Klipper and Moonraker to prevent
# uncontrolled updates, and adds web UI update managers.

um_log() {
    log "$*"
    echo "$*" >> "$UPDATE_MGR_LOG_TMP" 2> /dev/null || true
}

# upsert_update_manager: ensures a section exists with the correct pinned_commit.
# If the section exists but has wrong/missing pinned_commit, replace it.
# If the section doesn't exist, append it.
# Usage: upsert_update_manager "section_name" "channel" "pinned_commit_sha"
upsert_update_manager() {
    _section_name="$1"
    _channel="$2"
    _pin="$3"
    _section_header="[update_manager $_section_name]"

    if grep -q "^\[update_manager $_section_name\]$" "$MOONRAKER_CONF" 2>/dev/null; then
        # Section exists — check if pinned_commit matches
        if grep -A5 "^\[update_manager $_section_name\]$" "$MOONRAKER_CONF" | grep -q "pinned_commit: $_pin"; then
            um_log "update_manager_${_section_name}=already_correct"
        else
            # Remove old section and re-add with correct pin
            um_log "update_manager_${_section_name}=updating_pin"
            tmp_conf="${MOONRAKER_CONF}.tmp.$$"
            awk -v sect="$_section_header" '
                BEGIN { in_section=0 }
                $0 == sect { in_section=1; next }
                in_section && /^\[/ { in_section=0 }
                !in_section { print }
            ' "$MOONRAKER_CONF" > "$tmp_conf" && mv "$tmp_conf" "$MOONRAKER_CONF"
            cat >> "$MOONRAKER_CONF" << UPSERT_EOF

$_section_header
channel: $_channel
pinned_commit: $_pin
UPSERT_EOF
            um_log "update_manager_${_section_name}=updated"
        fi
    else
        # Section does not exist — add it
        um_log "update_manager_${_section_name}=adding"
        cat >> "$MOONRAKER_CONF" << UPSERT_EOF

$_section_header
channel: $_channel
pinned_commit: $_pin
UPSERT_EOF
        um_log "update_manager_${_section_name}=added"
    fi
}

enforce_klipper_pin() {
    # Ensure ~/klipper is checked out at the pinned commit.
    # Moonraker's pinned_commit prevents forward drift, but if the pin was
    # bumped in a new KAOS release the installer must move Klipper to match.
    if [ ! -d "$KLIPPER_DIR/.git" ]; then
        log "enforce_klipper_pin: $KLIPPER_DIR is not a git repo — skipping"
        return
    fi

    current_sha=$(git -C "$KLIPPER_DIR" rev-parse HEAD 2>/dev/null || echo "")
    if [ "$current_sha" = "$KLIPPER_PIN" ]; then
        log "enforce_klipper_pin: already at $KLIPPER_PIN — OK"
        return
    fi

    log "enforce_klipper_pin: current=$current_sha expected=$KLIPPER_PIN — updating"
    if ! git -C "$KLIPPER_DIR" fetch origin 2>/dev/null; then
        log "enforce_klipper_pin: fetch failed (offline?) — skipping"
        return
    fi

    if git -C "$KLIPPER_DIR" cat-file -t "$KLIPPER_PIN" >/dev/null 2>&1; then
        git -C "$KLIPPER_DIR" reset --hard "$KLIPPER_PIN"
        log "enforce_klipper_pin: checked out $KLIPPER_PIN — OK"
    else
        log "enforce_klipper_pin: pinned commit not in history (shallow clone?) — skipping"
    fi
}

enable_update_managers() {
    um_log "update_manager_begin"

    if [ ! -f "$MOONRAKER_CONF" ]; then
        um_log "update_manager_moonraker_conf=not_found"
        um_log "update_manager_status=skipped"
        um_log "update_manager_end"
        return
    fi

    # Back up moonraker.conf before modifying.
    backup_file "$MOONRAKER_CONF"

    # Ensure Klipper and Moonraker are pinned to tested versions.
    upsert_update_manager "klipper" "dev" "$KLIPPER_PIN"
    upsert_update_manager "moonraker" "dev" "$MOONRAKER_PIN"

    # Mainsail update manager
    if grep -q '\[update_manager mainsail\]' "$MOONRAKER_CONF" 2> /dev/null; then
        um_log "update_manager_mainsail=already_present"
    else
        um_log "update_manager_mainsail=adding"
        cat >> "$MOONRAKER_CONF" << 'MAINSAIL_EOF'

[update_manager mainsail]
type: web
channel: stable
repo: mainsail-crew/mainsail
path: ~/mainsail
MAINSAIL_EOF
        if grep -q '\[update_manager mainsail\]' "$MOONRAKER_CONF" 2> /dev/null; then
            um_log "update_manager_mainsail=added"
        else
            um_log "update_manager_mainsail=add_failed"
        fi
    fi

    # Fluidd update manager
    if grep -q '\[update_manager fluidd\]' "$MOONRAKER_CONF" 2> /dev/null; then
        um_log "update_manager_fluidd=already_present"
    else
        um_log "update_manager_fluidd=adding"
        cat >> "$MOONRAKER_CONF" << 'FLUIDD_EOF'

[update_manager fluidd]
type: web
channel: stable
repo: fluidd-core/fluidd
path: ~/fluidd
FLUIDD_EOF
        if grep -q '\[update_manager fluidd\]' "$MOONRAKER_CONF" 2> /dev/null; then
            um_log "update_manager_fluidd=added"
        else
            um_log "update_manager_fluidd=add_failed"
        fi
    fi

    um_log "update_manager_end"
}

# Use the directory containing this installer as the source package directory.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2> /dev/null && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd)

# Detect repo layout: structured (install/ + phrozen_dev/ + config/) vs flat (all-in-one).
if [ -f "$REPO_ROOT/phrozen_dev/dev.py" ] && [ -d "$REPO_ROOT/config/kaos" ]; then
    # Structured repo — assemble flat staging dir from phrozen_dev/ + config/
    SOURCE_DIR=$(mktemp -d "/tmp/kaos_stage_XXXXXX")
    _cleanup_stage() { rm -rf "$SOURCE_DIR"; }
    trap '_cleanup_stage' EXIT
    cp -a "$REPO_ROOT/phrozen_dev/"* "$SOURCE_DIR/" 2>/dev/null || true
    cp -a "$REPO_ROOT/config/"* "$SOURCE_DIR/" 2>/dev/null || true
else
    SOURCE_DIR="$SCRIPT_DIR"
fi

[ -f "$SOURCE_DIR/dev.py" ] || fail "Could not find source package directory containing dev.py: $SOURCE_DIR"

log "script started"
if $WHATIF; then
    log "*** --whatif mode: validation only, no files will be modified ***"
fi
log "running as user: $(whoami 2> /dev/null || echo unknown)"
log "SOURCE_DIR=$SOURCE_DIR"
log "TARGET_DIR=$TARGET_DIR"
log "CONFIG_DIR=$CONFIG_DIR"

# Validate source package before changing live files.
[ -f "$SOURCE_DIR/__init__.py" ] || fail "Missing source file: $SOURCE_DIR/__init__.py"
[ -f "$SOURCE_DIR/dev.py" ] || fail "Missing source file: $SOURCE_DIR/dev.py"
[ -f "$SOURCE_DIR/kaos_logging.py" ] || fail "Missing source file: $SOURCE_DIR/kaos_logging.py"
[ -f "$SOURCE_DIR/cmds.py" ] || fail "Missing source file: $SOURCE_DIR/cmds.py"
[ -f "$SOURCE_DIR/base.py" ] || fail "Missing source file: $SOURCE_DIR/base.py"
[ -f "$SOURCE_DIR/cwebsocketapis.py" ] || fail "Missing source file: $SOURCE_DIR/cwebsocketapis.py"
[ -f "$SOURCE_DIR/KlipperScreen-start.sh" ] || fail "Missing source file: $SOURCE_DIR/KlipperScreen-start.sh"
[ -d "$SOURCE_DIR/pyusb-master" ] || fail "Missing source directory: $SOURCE_DIR/pyusb-master"
[ -f "$SOURCE_DIR/kaos.cfg" ] || fail "Missing source file: $SOURCE_DIR/kaos.cfg"
[ -d "$SOURCE_DIR/kaos" ] || fail "Missing source directory: $SOURCE_DIR/kaos"
[ -f "$SOURCE_DIR/printer.cfg" ] || fail "Missing source file: $SOURCE_DIR/printer.cfg"
[ -f "$SOURCE_DIR/printer_gcode_macro.cfg" ] || fail "Missing source file: $SOURCE_DIR/printer_gcode_macro.cfg"

# Make wildcard failures explicit. Without this, cp may fail later with less useful context.
set -- "$SOURCE_DIR"/kaos/*.cfg
[ -f "$1" ] || fail "No .cfg files found in source directory: $SOURCE_DIR/kaos"

# Ensure destination paths exist and are writable.
if ! $WHATIF; then
    mkdir -p "$TARGET_DIR" || fail "Cannot create target directory: $TARGET_DIR"
fi
[ -d "$CONFIG_DIR" ] || fail "Config directory does not exist: $CONFIG_DIR"

log "checking write access to $TARGET_DIR"
if ! $WHATIF; then
    touch "$TARGET_DIR/.kaos_write_test" || fail "Cannot write to target directory: $TARGET_DIR"
    rm -f "$TARGET_DIR/.kaos_write_test" || fail "Cannot remove write-test file from: $TARGET_DIR"
fi

log "checking write/create access to $CONFIG_DIR"
if ! $WHATIF; then
    touch "$CONFIG_DIR/.kaos_write_test" || fail "Cannot write to config directory: $CONFIG_DIR"
    rm -f "$CONFIG_DIR/.kaos_write_test" || fail "Cannot remove write-test file from: $CONFIG_DIR"
    mkdir -p "$CONFIG_DIR/.kaos_mkdir_test" || fail "Cannot create directories in config directory: $CONFIG_DIR"
    rmdir "$CONFIG_DIR/.kaos_mkdir_test" || fail "Cannot remove mkdir-test directory from: $CONFIG_DIR"
fi

# --- Migration preflight check ------------------------------------------------
# Verify that migrate_to_kaos.sh has been run. The installer requires Klipper to
# be pointing at mainline (Klipper3d/klipper), not the old Phrozen fork.
if [ -d "$KLIPPER_DIR/.git" ]; then
    klipper_origin=$(git -C "$KLIPPER_DIR" remote get-url origin 2>/dev/null || echo "")
    case "$klipper_origin" in
        *Klipper3d/klipper*) ;;  # Good — mainline
        *)
            fail "Klipper origin is '$klipper_origin' (not mainline Klipper3d/klipper). Run migrate_to_kaos.sh first."
            ;;
    esac
fi

# Install log so we can prove this script actually ran and preserve live values before replacement.
existing_fila_cut_x_pos="NOT_FOUND"
rm -f "$SAVE_CONFIG_TMP"
if [ -f "$CONFIG_DIR/printer.cfg" ]; then
    # Use the same grep pattern proven over SSH, then strip the key/comments/whitespace.
    existing_fila_cut_x_pos=$(grep -m 1 -E '^[[:space:]]*fila_cut_x_pos[[:space:]]*:' "$CONFIG_DIR/printer.cfg" |
        sed -E 's/^[[:space:]]*fila_cut_x_pos[[:space:]]*:[[:space:]]*//; s/[[:space:]]*[#;].*$//; s/^[[:space:]]+//; s/[[:space:]]+$//')
    [ -n "$existing_fila_cut_x_pos" ] || existing_fila_cut_x_pos="NOT_FOUND"

    # Preserve the existing Klipper SAVE_CONFIG block before printer.cfg is replaced.
    awk '
        found { print; next }
        /^#\*#.*SAVE_CONFIG/ { found=1; print }
    ' "$CONFIG_DIR/printer.cfg" > "$SAVE_CONFIG_TMP"
fi

# --- WhatIf summary and early exit -------------------------------------------
if $WHATIF; then
    log ""
    log "============================================================"
    log "  --whatif: showing what WOULD happen (no changes made)"
    log "============================================================"
    log ""
    log "Python files to install -> $TARGET_DIR:"
    for f in __init__.py dev.py kaos_logging.py cmds.py base.py cwebsocketapis.py; do
        if [ -f "$SOURCE_DIR/$f" ]; then
            log "  [COPY] $SOURCE_DIR/$f -> $TARGET_DIR/$f"
        fi
    done
    log "  [COPY] $SOURCE_DIR/pyusb-master/ -> $TARGET_DIR/pyusb-master/"
    log ""
    log "Legacy files to remove:"
    log "  [REMOVE] $TARGET_DIR/kaos_translations.py (if exists)"
    log "  [REMOVE] $TARGET_DIR/lang/ (if exists)"
    log ""
    log "Config files to install -> $CONFIG_DIR:"
    log "  [COPY] $SOURCE_DIR/kaos.cfg -> $CONFIG_DIR/kaos.cfg"
    log "  [COPY] $SOURCE_DIR/printer.cfg -> $CONFIG_DIR/printer.cfg"
    log "  [COPY] $SOURCE_DIR/printer_gcode_macro.cfg -> $CONFIG_DIR/printer_gcode_macro.cfg"
    log ""
    log "Split KAOS configs to install -> $CONFIG_DIR/kaos/:"
    for f in "$SOURCE_DIR"/kaos/*.cfg; do
        log "  [COPY] $f -> $CONFIG_DIR/kaos/$(basename "$f")"
    done
    log ""
    log "Preservation:"
    if [ "$existing_fila_cut_x_pos" != "NOT_FOUND" ]; then
        log "  [PRESERVE] fila_cut_x_pos=$existing_fila_cut_x_pos"
    else
        log "  [SKIP] fila_cut_x_pos not found in live printer.cfg"
    fi
    if [ -s "$SAVE_CONFIG_TMP" ]; then
        log "  [PRESERVE] SAVE_CONFIG block ($(wc -l < "$SAVE_CONFIG_TMP") lines)"
    else
        log "  [SKIP] No SAVE_CONFIG block in live printer.cfg"
    fi
    log ""
    log "Legacy files to remove:"
    log "  [REMOVE] $TARGET_DIR/kaos_translations.py (if exists)"
    log "  [REMOVE] $TARGET_DIR/lang/ (if exists)"
    log "  [REMOVE] $SOURCE_DIR/phrozen_install-ARCO300-MKS-RK3328-STM32F407VET6-I16.sh (if exists)"
    log "  [REMOVE] $SOURCE_DIR/phrozen_install-ARCO300-phrozen-RK3308-STM32F407VET6-I31.sh (if exists)"
    log "  [REMOVE] $TARGET_DIR/phrozen_install-ARCO300-MKS-RK3328-STM32F407VET6-I16.sh (if exists)"
    log "  [REMOVE] $TARGET_DIR/phrozen_install-ARCO300-phrozen-RK3308-STM32F407VET6-I31.sh (if exists)"
    log "  [REMOVE] $TARGET_DIR/start-ARCO300-MKS-RK3328-STM32F407VET6-I16.sh (if exists)"
    log "  [REMOVE] $TARGET_DIR/start-ARCO300-phrozen-RK3308-STM32F407VET6-I31.sh (if exists)"
    log "  [REMOVE] $TARGET_DIR/KlipperScreen-start-ARCO300-MKS-RK3328-STM32F407VET6-I16.sh (if exists)"
    log "  [REMOVE] $TARGET_DIR/KlipperScreen-start-ARCO300-phrozen-RK3308-STM32F407VET6-I31.sh (if exists)"
    log ""
    log "Pre-install:"
    log "  [BACKUP] $CONFIG_DIR/printer.cfg -> $CONFIG_DIR/printer.cfg.$timestamp.bak"
    log ""
    log "Post-install:"
    log "  [CHMOD] Set 644 on all installed files, 755 on $CONFIG_DIR/kaos/"
    log "  [REMOVE] soft_shutdown.sh"
    log "  [REMOVE] Phrozen phone-home (frp-oms):"
    log "    - Kill: phrozen_slave_ota, phrozen_master, frpc, frpc_script"
    log "    - Mask: frpc.service (systemd)"
    log "    - Remove: $TARGET_DIR/frp-oms/ (all phone-home binaries)"
    log "    - Remove: /etc/frp/ (if exists)"
    log "    - Patch: $TARGET_DIR/start.sh (comment out phone-home lines)"
    log "    - Patch: /home/mks/KlipperScreen/scripts/KlipperScreen-start.sh"
    log "  [UPDATE_MANAGER] Enable Moonraker update managers for Mainsail and Fluidd:"
    log "    - Core update managers (moonraker/klipper) are handled by Moonraker itself"
    log "    - Remove legacy [update_manager moonraker]/[update_manager klipper] sections if present"
    if [ -f "$MOONRAKER_CONF" ]; then
        if grep -q '^\[update_manager moonraker\]$' "$MOONRAKER_CONF" 2> /dev/null; then
            log "    - Moonraker core: [REMOVE] legacy [update_manager moonraker] section"
        fi
        if grep -q '^\[update_manager klipper\]$' "$MOONRAKER_CONF" 2> /dev/null; then
            log "    - Klipper core: [REMOVE] legacy [update_manager klipper] section"
        fi
        if grep -q '\[update_manager mainsail\]' "$MOONRAKER_CONF" 2> /dev/null; then
            log "    - Mainsail: already present"
        else
            log "    - Mainsail: [APPEND] [update_manager mainsail] to moonraker.conf"
        fi
        if grep -q '\[update_manager fluidd\]' "$MOONRAKER_CONF" 2> /dev/null; then
            log "    - Fluidd: already present"
        else
            log "    - Fluidd: [APPEND] [update_manager fluidd] to moonraker.conf"
        fi
    else
        log "    - moonraker.conf not found at $MOONRAKER_CONF — skipped"
    fi
    log "  [REBOOT] System reboot"
    log ""
    log "============================================================"
    log "  --whatif complete. No files were modified."
    log "============================================================"
    rm -f "$SAVE_CONFIG_TMP"
    exit 0
fi
# --- End WhatIf --------------------------------------------------------------

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
cp -f "$SOURCE_DIR/__init__.py" "$TARGET_DIR/__init__.py" || fail "Failed to copy __init__.py"
cp -f "$SOURCE_DIR/dev.py" "$TARGET_DIR/dev.py" || fail "Failed to copy dev.py"
cp -f "$SOURCE_DIR/kaos_logging.py" "$TARGET_DIR/kaos_logging.py" || fail "Failed to copy kaos_logging.py"
cp -f "$SOURCE_DIR/cmds.py" "$TARGET_DIR/cmds.py" || fail "Failed to copy cmds.py"
cp -f "$SOURCE_DIR/base.py" "$TARGET_DIR/base.py" || fail "Failed to copy base.py"
cp -f "$SOURCE_DIR/cwebsocketapis.py" "$TARGET_DIR/cwebsocketapis.py" || fail "Failed to copy cwebsocketapis.py"

# Deploy vendored pyusb library (USB communication dependency).
log "copying pyusb-master"
rm -rf "$TARGET_DIR/pyusb-master"
cp -rf "$SOURCE_DIR/pyusb-master" "$TARGET_DIR/pyusb-master" || fail "Failed to copy pyusb-master"

# Deploy KAOS-patched KlipperScreen-start.sh (phone-home removed, English comments).
log "copying KlipperScreen-start.sh"
cp -f "$SOURCE_DIR/KlipperScreen-start.sh" "$TARGET_DIR/KlipperScreen-start.sh" || fail "Failed to copy KlipperScreen-start.sh"
chmod 755 "$TARGET_DIR/KlipperScreen-start.sh"

# Remove legacy translation artifacts from previous installs.
rm -f "$TARGET_DIR/kaos_translations.py"
rm -rf "$TARGET_DIR/lang"

# Remove legacy translation artifacts from previous installs.
rm -f "$TARGET_DIR/kaos_translations.py"
rm -rf "$TARGET_DIR/lang"

# Remove deprecated board-specific scripts left by previous installs.
# These are dead files on production MKS boards — nothing calls them.
log "cleaning up deprecated board-specific scripts"
for old_script in \
    "$SOURCE_DIR/phrozen_install-ARCO300-MKS-RK3328-STM32F407VET6-I16.sh" \
    "$SOURCE_DIR/phrozen_install-ARCO300-phrozen-RK3308-STM32F407VET6-I31.sh" \
    "$TARGET_DIR/phrozen_install-ARCO300-MKS-RK3328-STM32F407VET6-I16.sh" \
    "$TARGET_DIR/phrozen_install-ARCO300-phrozen-RK3308-STM32F407VET6-I31.sh" \
    "$TARGET_DIR/start-ARCO300-MKS-RK3328-STM32F407VET6-I16.sh" \
    "$TARGET_DIR/start-ARCO300-phrozen-RK3308-STM32F407VET6-I31.sh" \
    "$TARGET_DIR/KlipperScreen-start-ARCO300-MKS-RK3328-STM32F407VET6-I16.sh" \
    "$TARGET_DIR/KlipperScreen-start-ARCO300-phrozen-RK3308-STM32F407VET6-I31.sh"; do
    if [ -f "$old_script" ]; then
        rm -f "$old_script" && log "  removed: $old_script" || log "  WARNING: failed to remove $old_script"
    fi
done

# Update klipperscreen.service to reference the generic KlipperScreen-start.sh.
KS_SERVICE_SRC="$SOURCE_DIR/serial-screen/klipperscreen.service"
KS_SERVICE_DST="/etc/systemd/system/klipperscreen.service"
if [ -f "$KS_SERVICE_SRC" ]; then
    if [ -f "$KS_SERVICE_DST" ]; then
        if grep -q 'KlipperScreen-start-ARCO300' "$KS_SERVICE_DST" 2> /dev/null; then
            cp -f "$KS_SERVICE_SRC" "$KS_SERVICE_DST" || log "WARNING: failed to update klipperscreen.service"
            systemctl daemon-reload 2> /dev/null || true
            log "klipperscreen.service updated to use KlipperScreen-start.sh"
        else
            log "klipperscreen.service already points to generic start script"
        fi
    else
        log "klipperscreen.service not found at $KS_SERVICE_DST — skipping"
    fi
else
    log "WARNING: klipperscreen.service source not found: $KS_SERVICE_SRC"
fi

# Remove stale serial-screen/printer.cfg — hardware config is managed via config/printer.cfg.
if [ -f "$TARGET_DIR/serial-screen/printer.cfg" ]; then
    rm -f "$TARGET_DIR/serial-screen/printer.cfg"
    log "removed stale serial-screen/printer.cfg"
fi

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
        sed -E "s|^[[:space:]]*fila_cut_x_pos[[:space:]]*:.*|fila_cut_x_pos: $existing_fila_cut_x_pos|" "$CONFIG_DIR/printer.cfg" > "$PRINTER_CFG_TMP" || fail "Failed to prepare preserved fila_cut_x_pos update"
        mv -f "$PRINTER_CFG_TMP" "$CONFIG_DIR/printer.cfg" || fail "Failed to apply preserved fila_cut_x_pos to printer.cfg"

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
chmod 644 "$TARGET_DIR/cmds.py" || fail "chmod failed for cmds.py"
chmod 644 "$TARGET_DIR/base.py" || fail "chmod failed for base.py"
chmod 644 "$TARGET_DIR/cwebsocketapis.py" || fail "chmod failed for cwebsocketapis.py"
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
[ -f "$TARGET_DIR/cmds.py" ] || fail "Verify failed: missing $TARGET_DIR/cmds.py"
[ -f "$TARGET_DIR/base.py" ] || fail "Verify failed: missing $TARGET_DIR/base.py"
[ -f "$TARGET_DIR/cwebsocketapis.py" ] || fail "Verify failed: missing $TARGET_DIR/cwebsocketapis.py"
[ -d "$CONFIG_DIR/kaos" ] || fail "Verify failed: missing $CONFIG_DIR/kaos"
[ -f "$CONFIG_DIR/kaos.cfg" ] || fail "Verify failed: missing $CONFIG_DIR/kaos.cfg"
[ -f "$CONFIG_DIR/printer.cfg" ] || fail "Verify failed: missing $CONFIG_DIR/printer.cfg"
[ -f "$CONFIG_DIR/printer_gcode_macro.cfg" ] || fail "Verify failed: missing $CONFIG_DIR/printer_gcode_macro.cfg"

cfg_count=$(find "$CONFIG_DIR/kaos" -maxdepth 1 -type f -name '*.cfg' | wc -l)

log "installed $cfg_count split KAOS cfg files"

[ "$cfg_count" -gt 0 ] || fail "Verify failed: no split KAOS cfg files installed in $CONFIG_DIR/kaos"

enable_update_managers
enforce_klipper_pin

{
    echo "KAOS install completed at $(date)"
    echo "cfg_count=$cfg_count"
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
    echo "update_manager_log_begin"
    if [ -s "$UPDATE_MGR_LOG_TMP" ]; then
        cat "$UPDATE_MGR_LOG_TMP"
    else
        echo "NOT_RUN"
    fi
    echo "update_manager_log_end"
    echo ""
    echo "KAOS_INSTALL_SUCCESS: KAOS install completed"
    echo ""
    echo "Rebooting printer after KAOS install at $(date)"
} >> "$INSTALL_LOG"

rm -f "$SAVE_CONFIG_TMP"
rm -f "$UPDATE_MGR_LOG_TMP"

sync
sleep 2

# reboot may live in /sbin which isn't in non-root PATH
if command -v reboot > /dev/null 2>&1; then
    reboot
elif [ -x /sbin/reboot ]; then
    /sbin/reboot
else
    /sbin/shutdown -r now
fi
