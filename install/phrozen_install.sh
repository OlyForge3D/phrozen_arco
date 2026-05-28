#!/bin/sh
# KAOS_VERSION: v0.96

# KAOS / Phrozen Arco installer (universal — auto-detects board variant)
# POSIX sh compatible.
#
# Deployment model (v0.96+):
#   Symlinks connect Klipper to files in ~/kaos (this git repo).
#   Moonraker's update_manager does `git pull` then `systemctl restart klipper`.
#   Because Python extras and configs are symlinked, the new code is live immediately
#   after the service restart — no file copying needed for updates.
#
#   Only printer.cfg is a real file (Klipper's SAVE_CONFIG modifies it at runtime).
#
# What this script does:
#   First run:  Create symlinks, one-time printer.cfg copy + preservation, legacy cleanup.
#   Re-run:     Verify/repair symlinks, re-apply preservation, enforce klipper pin.

set -u

KLIPPER_DIR="/home/mks/klipper"
TARGET_DIR="$KLIPPER_DIR/klippy/extras/phrozen_dev"
CONFIG_DIR="/home/mks/printer_data/config"
INSTALL_LOG="$CONFIG_DIR/kaos_install.log"

# Pinned commits — tested versions for the Phrozen Arco.
# Moonraker's update_manager will refuse to update beyond these.
KLIPPER_PIN="0d67d9c4"   # v0.12.0 (protocol-compatible with v0.11.0-122 MCU firmware)
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

    # Section exists — check if pinned_commit matches
    if grep -q "^\[update_manager $_section_name\]$" "$MOONRAKER_CONF" 2>/dev/null; then
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

# Ensure ~/klipper is checked out at the pinned commit.
# Moonraker's pinned_commit prevents forward drift, but if the pin was
# bumped in a new KAOS release the installer must move Klipper to match.
enforce_klipper_pin() {
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

# --- Locate KAOS repository root ---------------------------------------------

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2> /dev/null && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd)

# Validate repo structure — these paths are what symlinks will point to.
[ -f "$REPO_ROOT/phrozen_dev/dev.py" ] || fail "Missing: $REPO_ROOT/phrozen_dev/dev.py — is this the KAOS repo?"
[ -f "$REPO_ROOT/phrozen_dev/__init__.py" ] || fail "Missing: $REPO_ROOT/phrozen_dev/__init__.py"
[ -f "$REPO_ROOT/phrozen_dev/kaos_logging.py" ] || fail "Missing: $REPO_ROOT/phrozen_dev/kaos_logging.py"
[ -f "$REPO_ROOT/phrozen_dev/cmds.py" ] || fail "Missing: $REPO_ROOT/phrozen_dev/cmds.py"
[ -f "$REPO_ROOT/phrozen_dev/base.py" ] || fail "Missing: $REPO_ROOT/phrozen_dev/base.py"
[ -f "$REPO_ROOT/phrozen_dev/cwebsocketapis.py" ] || fail "Missing: $REPO_ROOT/phrozen_dev/cwebsocketapis.py"
[ -d "$REPO_ROOT/phrozen_dev/pyusb-master" ] || fail "Missing: $REPO_ROOT/phrozen_dev/pyusb-master"
[ -f "$REPO_ROOT/config/kaos.cfg" ] || fail "Missing: $REPO_ROOT/config/kaos.cfg"
[ -d "$REPO_ROOT/config/kaos" ] || fail "Missing: $REPO_ROOT/config/kaos/"
[ -f "$REPO_ROOT/config/printer.cfg" ] || fail "Missing: $REPO_ROOT/config/printer.cfg"
[ -f "$REPO_ROOT/config/printer_gcode_macro.cfg" ] || fail "Missing: $REPO_ROOT/config/printer_gcode_macro.cfg"

# Make wildcard failures explicit.
set -- "$REPO_ROOT"/config/kaos/*.cfg
[ -f "$1" ] || fail "No .cfg files found in: $REPO_ROOT/config/kaos/"

log "script started"
if $WHATIF; then
    log "*** --whatif mode: validation only, no files will be modified ***"
fi
log "running as user: $(whoami 2> /dev/null || echo unknown)"
log "REPO_ROOT=$REPO_ROOT"
log "TARGET_DIR=$TARGET_DIR"
log "CONFIG_DIR=$CONFIG_DIR"

# Ensure destination paths exist and are writable.
if ! $WHATIF; then
    mkdir -p "$(dirname "$TARGET_DIR")" || fail "Cannot create parent of target directory: $(dirname "$TARGET_DIR")"
fi
[ -d "$CONFIG_DIR" ] || fail "Config directory does not exist: $CONFIG_DIR"

log "checking write access to $(dirname "$TARGET_DIR")"
if ! $WHATIF; then
    touch "$(dirname "$TARGET_DIR")/.kaos_write_test" || fail "Cannot write to: $(dirname "$TARGET_DIR")"
    rm -f "$(dirname "$TARGET_DIR")/.kaos_write_test"
fi

log "checking write/create access to $CONFIG_DIR"
if ! $WHATIF; then
    touch "$CONFIG_DIR/.kaos_write_test" || fail "Cannot write to config directory: $CONFIG_DIR"
    rm -f "$CONFIG_DIR/.kaos_write_test"
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

# --- Preservation capture -----------------------------------------------------
# Install log so we can prove this script ran and preserve live values before replacement.
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
    log "Symlinks to create/verify:"
    if [ -L "$TARGET_DIR" ] && [ "$(readlink "$TARGET_DIR")" = "$REPO_ROOT/phrozen_dev" ]; then
        log "  [OK] $TARGET_DIR -> $REPO_ROOT/phrozen_dev"
    elif [ -d "$TARGET_DIR" ] && [ ! -L "$TARGET_DIR" ]; then
        log "  [UPGRADE] $TARGET_DIR (dir->symlink) -> $REPO_ROOT/phrozen_dev"
    else
        log "  [CREATE] $TARGET_DIR -> $REPO_ROOT/phrozen_dev"
    fi
    if [ -L "$CONFIG_DIR/kaos" ] && [ "$(readlink "$CONFIG_DIR/kaos")" = "$REPO_ROOT/config/kaos" ]; then
        log "  [OK] $CONFIG_DIR/kaos -> $REPO_ROOT/config/kaos"
    elif [ -d "$CONFIG_DIR/kaos" ] && [ ! -L "$CONFIG_DIR/kaos" ]; then
        log "  [UPGRADE] $CONFIG_DIR/kaos (dir->symlink) -> $REPO_ROOT/config/kaos"
    else
        log "  [CREATE] $CONFIG_DIR/kaos -> $REPO_ROOT/config/kaos"
    fi
    if [ -L "$CONFIG_DIR/kaos.cfg" ] && [ "$(readlink "$CONFIG_DIR/kaos.cfg")" = "$REPO_ROOT/config/kaos.cfg" ]; then
        log "  [OK] $CONFIG_DIR/kaos.cfg -> $REPO_ROOT/config/kaos.cfg"
    else
        log "  [CREATE] $CONFIG_DIR/kaos.cfg -> $REPO_ROOT/config/kaos.cfg"
    fi
    log ""
    log "File copies to deploy:"
    log "  printer_gcode_macro.cfg -> $CONFIG_DIR/printer_gcode_macro.cfg"
    log "printer.cfg (real file — SAVE_CONFIG modifies it at runtime):"
    if [ -f "$CONFIG_DIR/printer.cfg" ]; then
        log "  [UPDATE] Re-deploy from template + patch preserved values"
    else
        log "  [COPY] $REPO_ROOT/config/printer.cfg -> $CONFIG_DIR/printer.cfg"
    fi
    log ""
    log "Preservation:"
    if [ "$existing_fila_cut_x_pos" != "NOT_FOUND" ]; then
        log "  [PRESERVE] fila_cut_x_pos=$existing_fila_cut_x_pos"
    else
        log "  [SKIP] fila_cut_x_pos not found"
    fi
    if [ -s "$SAVE_CONFIG_TMP" ]; then
        log "  [PRESERVE] SAVE_CONFIG block ($(wc -l < "$SAVE_CONFIG_TMP") lines)"
    else
        log "  [SKIP] No SAVE_CONFIG block"
    fi
    log ""
    log "Post-install: legacy cleanup, update_manager pins, reboot"
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
    echo "REPO_ROOT=$REPO_ROOT"
    echo "TARGET_DIR=$TARGET_DIR"
    echo "CONFIG_DIR=$CONFIG_DIR"
    echo "MODE=symlink"
} > "$INSTALL_LOG" || fail "Could not write install log"

# --- Deploy Python extras via symlink -----------------------------------------

log "deploying Python extras (symlink)"

if [ -L "$TARGET_DIR" ]; then
    current_link=$(readlink "$TARGET_DIR")
    if [ "$current_link" = "$REPO_ROOT/phrozen_dev" ]; then
        log "  phrozen_dev symlink already correct"
    else
        log "  phrozen_dev symlink wrong target ($current_link), fixing"
        rm -f "$TARGET_DIR"
        ln -sfn "$REPO_ROOT/phrozen_dev" "$TARGET_DIR" || fail "Failed to create phrozen_dev symlink"
        log "  phrozen_dev symlink updated"
    fi
elif [ -d "$TARGET_DIR" ]; then
    log "  upgrading: moving old phrozen_dev directory aside"
    backup_dir="$TARGET_DIR.pre_symlink_$timestamp"
    mv "$TARGET_DIR" "$backup_dir" || fail "Failed to move old $TARGET_DIR"
    log "  old directory preserved at: $backup_dir"
    ln -sfn "$REPO_ROOT/phrozen_dev" "$TARGET_DIR" || fail "Failed to create phrozen_dev symlink"
    log "  phrozen_dev symlink created (upgrade)"
else
    ln -sfn "$REPO_ROOT/phrozen_dev" "$TARGET_DIR" || fail "Failed to create phrozen_dev symlink"
    log "  phrozen_dev symlink created"
fi

# --- Deploy KAOS config directory via symlink ---------------------------------

log "deploying KAOS config directory (symlink)"

if [ -L "$CONFIG_DIR/kaos" ]; then
    current_link=$(readlink "$CONFIG_DIR/kaos")
    if [ "$current_link" = "$REPO_ROOT/config/kaos" ]; then
        log "  kaos/ symlink already correct"
    else
        log "  kaos/ symlink wrong target ($current_link), fixing"
        rm -f "$CONFIG_DIR/kaos"
        ln -sfn "$REPO_ROOT/config/kaos" "$CONFIG_DIR/kaos" || fail "Failed to create kaos config symlink"
        log "  kaos/ symlink updated"
    fi
elif [ -d "$CONFIG_DIR/kaos" ]; then
    log "  upgrading: moving old kaos/ config directory aside"
    backup_dir="$CONFIG_DIR/kaos.pre_symlink_$timestamp"
    mv "$CONFIG_DIR/kaos" "$backup_dir" || fail "Failed to move old $CONFIG_DIR/kaos"
    log "  old directory preserved at: $backup_dir"
    ln -sfn "$REPO_ROOT/config/kaos" "$CONFIG_DIR/kaos" || fail "Failed to create kaos config symlink"
    log "  kaos/ symlink created (upgrade)"
else
    ln -sfn "$REPO_ROOT/config/kaos" "$CONFIG_DIR/kaos" || fail "Failed to create kaos config symlink"
    log "  kaos/ symlink created"
fi

# --- Deploy kaos.cfg via symlink ----------------------------------------------

log "deploying kaos.cfg (symlink)"

if [ -L "$CONFIG_DIR/kaos.cfg" ]; then
    current_link=$(readlink "$CONFIG_DIR/kaos.cfg")
    if [ "$current_link" = "$REPO_ROOT/config/kaos.cfg" ]; then
        log "  kaos.cfg symlink already correct"
    else
        rm -f "$CONFIG_DIR/kaos.cfg"
        ln -sf "$REPO_ROOT/config/kaos.cfg" "$CONFIG_DIR/kaos.cfg" || fail "Failed to create kaos.cfg symlink"
        log "  kaos.cfg symlink updated"
    fi
else
    rm -f "$CONFIG_DIR/kaos.cfg" 2>/dev/null || true
    ln -sf "$REPO_ROOT/config/kaos.cfg" "$CONFIG_DIR/kaos.cfg" || fail "Failed to create kaos.cfg symlink"
    log "  kaos.cfg symlink created"
fi

# --- Deploy printer_gcode_macro.cfg (file copy) ------------------------------
# Copied rather than symlinked so user edits don't accidentally modify the repo.

log "deploying printer_gcode_macro.cfg (file copy)"

# If a previous install left a symlink, replace it with a real file.
if [ -L "$CONFIG_DIR/printer_gcode_macro.cfg" ]; then
    rm -f "$CONFIG_DIR/printer_gcode_macro.cfg"
    log "  removed stale symlink"
fi

cp -f "$REPO_ROOT/config/printer_gcode_macro.cfg" "$CONFIG_DIR/printer_gcode_macro.cfg" || fail "Failed to copy printer_gcode_macro.cfg"
log "  printer_gcode_macro.cfg deployed"

# --- Deploy printer.cfg (real file + preservation) ----------------------------
# printer.cfg is the ONLY file that remains a real copy, because Klipper's
# SAVE_CONFIG appends calibration data to it at runtime.

log "deploying printer.cfg"

if [ ! -f "$CONFIG_DIR/printer.cfg" ]; then
    cp -f "$REPO_ROOT/config/printer.cfg" "$CONFIG_DIR/printer.cfg" || fail "Failed to copy printer.cfg"
    log "  printer.cfg copied (first install)"
else
    backup_file "$CONFIG_DIR/printer.cfg"
    cp -f "$REPO_ROOT/config/printer.cfg" "$CONFIG_DIR/printer.cfg" || fail "Failed to copy printer.cfg"
    log "  printer.cfg updated from template"
fi

# --- Preservation: fila_cut_x_pos and SAVE_CONFIG -----------------------------

fila_cut_x_pos_update_status="skipped_NOT_FOUND"
save_config_update_status="skipped_NOT_FOUND"

if [ "$existing_fila_cut_x_pos" != "NOT_FOUND" ]; then
    if grep -qE '^[[:space:]]*fila_cut_x_pos[[:space:]]*:' "$CONFIG_DIR/printer.cfg"; then
        PRINTER_CFG_TMP="/tmp/kaos_printer_cfg_$$.tmp"
        sed -E "s|^[[:space:]]*fila_cut_x_pos[[:space:]]*:.*|fila_cut_x_pos: $existing_fila_cut_x_pos|" "$CONFIG_DIR/printer.cfg" > "$PRINTER_CFG_TMP" || fail "Failed to prepare preserved fila_cut_x_pos update"
        mv -f "$PRINTER_CFG_TMP" "$CONFIG_DIR/printer.cfg" || fail "Failed to apply preserved fila_cut_x_pos to printer.cfg"

        if grep -qE "^[[:space:]]*fila_cut_x_pos[[:space:]]*:[[:space:]]*$existing_fila_cut_x_pos([[:space:]]*([#;].*)?)?$" "$CONFIG_DIR/printer.cfg"; then
            fila_cut_x_pos_update_status="updated"
            log "preserved fila_cut_x_pos=$existing_fila_cut_x_pos"
        else
            fila_cut_x_pos_update_status="update_verify_failed"
            log "WARNING: fila_cut_x_pos update attempted but verify failed"
        fi
    else
        fila_cut_x_pos_update_status="target_key_not_found"
        log "WARNING: deployed printer.cfg has no fila_cut_x_pos key"
    fi
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
    } >> "$PRINTER_CFG_TMP" || fail "Failed to append existing SAVE_CONFIG block"
    mv -f "$PRINTER_CFG_TMP" "$CONFIG_DIR/printer.cfg" || fail "Failed to preserve SAVE_CONFIG block"
    save_config_update_status="updated"
    log "preserved existing SAVE_CONFIG block"
fi

chmod 644 "$CONFIG_DIR/printer.cfg" || fail "chmod failed for printer.cfg"

# --- Ensure [include kaos.cfg] is in printer.cfg -----------------------------

if grep -q '^[[:space:]]*\[include kaos.cfg\]' "$CONFIG_DIR/printer.cfg"; then
    log "[include kaos.cfg] already present in printer.cfg"
else
    log "adding [include kaos.cfg] to printer.cfg"
    # Insert after the first [include ...] block, or at line 2 if none exist.
    PRINTER_CFG_TMP="/tmp/kaos_printer_cfg_include_$$.tmp"
    if grep -qn '^[[:space:]]*\[include ' "$CONFIG_DIR/printer.cfg"; then
        # Find last [include ...] line and insert after it.
        last_include_line=$(grep -n '^[[:space:]]*\[include ' "$CONFIG_DIR/printer.cfg" | tail -1 | cut -d: -f1)
        awk -v line="$last_include_line" '
            NR == line { print; print "[include kaos.cfg]"; next }
            { print }
        ' "$CONFIG_DIR/printer.cfg" > "$PRINTER_CFG_TMP"
    else
        # No includes found — insert at line 2 (after shebang/comment).
        awk '
            NR == 1 { print; print "[include kaos.cfg]"; next }
            { print }
        ' "$CONFIG_DIR/printer.cfg" > "$PRINTER_CFG_TMP"
    fi
    mv -f "$PRINTER_CFG_TMP" "$CONFIG_DIR/printer.cfg" || fail "Failed to add [include kaos.cfg]"
    log "  [include kaos.cfg] inserted"
fi

# --- Legacy cleanup -----------------------------------------------------------
# Remove deprecated board-specific scripts left by previous installs.
# These are dead files on production MKS boards — nothing calls them.

log "cleaning up legacy artifacts"

for old_script in \
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
KS_SERVICE_SRC="$REPO_ROOT/phrozen_dev/serial-screen/klipperscreen.service"
KS_SERVICE_DST="/etc/systemd/system/klipperscreen.service"
if [ -f "$KS_SERVICE_SRC" ] && [ -f "$KS_SERVICE_DST" ]; then
    if grep -q 'KlipperScreen-start-ARCO300' "$KS_SERVICE_DST" 2> /dev/null; then
        cp -f "$KS_SERVICE_SRC" "$KS_SERVICE_DST" || log "WARNING: failed to update klipperscreen.service"
        systemctl daemon-reload 2> /dev/null || true
        log "klipperscreen.service updated"
    fi
fi

# Remove stale serial-screen/printer.cfg — hardware config is managed via config/printer.cfg.
if [ -f "$TARGET_DIR/serial-screen/printer.cfg" ]; then
    rm -f "$TARGET_DIR/serial-screen/printer.cfg"
    log "removed stale serial-screen/printer.cfg"
fi

# --- Verify -------------------------------------------------------------------
# Verify installed result.

log "verifying install"
[ -L "$TARGET_DIR" ] || [ -d "$TARGET_DIR" ] || fail "Verify: $TARGET_DIR missing"
[ -e "$TARGET_DIR/dev.py" ] || fail "Verify: $TARGET_DIR/dev.py missing"
[ -e "$TARGET_DIR/kaos_logging.py" ] || fail "Verify: $TARGET_DIR/kaos_logging.py missing"
[ -e "$TARGET_DIR/cmds.py" ] || fail "Verify: $TARGET_DIR/cmds.py missing"
[ -e "$TARGET_DIR/base.py" ] || fail "Verify: $TARGET_DIR/base.py missing"
[ -e "$TARGET_DIR/cwebsocketapis.py" ] || fail "Verify: $TARGET_DIR/cwebsocketapis.py missing"
[ -L "$CONFIG_DIR/kaos" ] || [ -d "$CONFIG_DIR/kaos" ] || fail "Verify: $CONFIG_DIR/kaos missing"
[ -e "$CONFIG_DIR/kaos.cfg" ] || fail "Verify: $CONFIG_DIR/kaos.cfg missing"
[ -f "$CONFIG_DIR/printer.cfg" ] || fail "Verify: $CONFIG_DIR/printer.cfg missing"
[ -e "$CONFIG_DIR/printer_gcode_macro.cfg" ] || fail "Verify: $CONFIG_DIR/printer_gcode_macro.cfg missing"

cfg_count=$(find -L "$CONFIG_DIR/kaos" -maxdepth 1 -name '*.cfg' | wc -l)
log "verified $cfg_count split KAOS cfg files"
[ "$cfg_count" -gt 0 ] || fail "Verify: no .cfg files in $CONFIG_DIR/kaos"

log "symlink status:"
[ -L "$TARGET_DIR" ] && log "  phrozen_dev -> $(readlink "$TARGET_DIR")"
[ -L "$CONFIG_DIR/kaos" ] && log "  kaos/ -> $(readlink "$CONFIG_DIR/kaos")"
[ -L "$CONFIG_DIR/kaos.cfg" ] && log "  kaos.cfg -> $(readlink "$CONFIG_DIR/kaos.cfg")"
log "file copies:"
[ -f "$CONFIG_DIR/printer_gcode_macro.cfg" ] && log "  printer_gcode_macro.cfg: present"

enable_update_managers
enforce_klipper_pin

{
    echo "KAOS install completed at $(date)"
    echo "mode=symlink"
    echo "cfg_count=$cfg_count"
    echo ""
    echo "symlinks:"
    echo "  phrozen_dev -> $(readlink "$TARGET_DIR" 2>/dev/null || echo N/A)"
    echo "  kaos/ -> $(readlink "$CONFIG_DIR/kaos" 2>/dev/null || echo N/A)"
    echo "  kaos.cfg -> $(readlink "$CONFIG_DIR/kaos.cfg" 2>/dev/null || echo N/A)"
    echo "file copies:"
    echo "  printer_gcode_macro.cfg: present"
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
    echo "Rebooting at $(date)"
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
