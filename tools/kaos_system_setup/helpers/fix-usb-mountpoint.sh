#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# ARCO System Prep helper: repair the hidden USB gcodes mountpoint safely.
#
# Problem:
#   /home/*/printer_data/gcodes/USB may be owned by root:root on stock systems.
#   When the USB stick is not mounted, this can prevent the UI/user from using
#   the directory correctly. During a USB firmware/System Prep install, however,
#   the USB path is usually mounted. Changing it then would modify the mounted
#   USB filesystem root, not the underlying eMMC mountpoint directory.
#
# Policy:
#   - If USB is not mounted: repair immediately.
#   - If USB is mounted: install a deferred systemd timer that retries until the
#     USB stick is removed, then repairs the underlying directory and disables
#     itself. Ownership/mode repair is never applied to a mounted USB filesystem.
#   - If enabled, remove only the exact stock vendor marker file ip.txt from the
#     USB folder, even when a real USB stick is mounted. This prevents Moonraker
#     from repeatedly logging invalid file write events for that vendor marker.
#   - Never unmount USB from the installer.

set -u

DRY_RUN=0
case "${1:-}" in
    "") ;;
    --dry-run) DRY_RUN=1 ;;
    *)
        echo "Usage: $0 [--dry-run]" >&2
        exit 2
        ;;
esac

: "${USB_MOUNTPOINT_MODE:=775}"
: "${USB_MOUNTPOINT_GROUP:=netdev}"
: "${USB_MOUNTPOINT_DEFER_TIMER_SECONDS:=300}"
: "${USB_ARTIFACT_BOOT_CLEANUP:=1}"
: "${USB_ARTIFACT_CLEANUP_ONBOOT_SECONDS:=120}"
: "${USB_ARTIFACT_CLEANUP_TIMER_SECONDS:=300}"

SERVICE_NAME="arco-fix-usb-mountpoint-deferred.service"
TIMER_NAME="arco-fix-usb-mountpoint-deferred.timer"
DEFERRED_SCRIPT="/usr/local/sbin/arco-fix-usb-mountpoint-deferred.sh"
CLEANUP_SERVICE_NAME="arco-clean-usb-ip-marker.service"
CLEANUP_TIMER_NAME="arco-clean-usb-ip-marker.timer"
CLEANUP_SCRIPT="/usr/local/sbin/arco-clean-usb-ip-marker.sh"
SYSTEMD_DIR="/etc/systemd/system"

log() { echo "USB_MOUNTPOINT_FIX: $*"; }

run() {
    if [ "$DRY_RUN" = "1" ]; then
        printf 'USB_MOUNTPOINT_FIX: dry_run_command='
        printf ' %s' "$@"
        printf '\n'
        return 0
    fi
    "$@"
}

candidate_homes() {
    [ -d /home/mks/printer_data/gcodes ] && echo /home/mks
    [ -d /home/prz/printer_data/gcodes ] && echo /home/prz
}

is_mounted() {
    path="$1"
    if command -v mountpoint >/dev/null 2>&1; then
        mountpoint -q "$path"
        return $?
    fi
    awk -v p="$path" '$2 == p { found=1 } END { exit found ? 0 : 1 }' /proc/mounts 2>/dev/null
}

owner_for_home() {
    home="$1"
    base_owner=$(basename "$home")
    if id "$base_owner" >/dev/null 2>&1; then
        printf '%s' "$base_owner"
    else
        stat -c '%U' "$home" 2>/dev/null || printf '%s' "$base_owner"
    fi
}

group_for_owner() {
    owner="$1"
    if getent group "$USB_MOUNTPOINT_GROUP" >/dev/null 2>&1; then
        printf '%s' "$USB_MOUNTPOINT_GROUP"
    else
        id -gn "$owner" 2>/dev/null || printf '%s' "$owner"
    fi
}

repair_path_now() {
    usb_path="$1"
    home="$2"
    owner=$(owner_for_home "$home")
    group=$(group_for_owner "$owner")

    if [ ! -d "$usb_path" ]; then
        run mkdir -p "$usb_path" || { log "path_status=failed_mkdir_nonfatal path=$usb_path"; return 1; }
        log "path_status=created path=$usb_path"
    fi

    run chown "$owner:$group" "$usb_path" || { log "owner_status=failed_nonfatal path=$usb_path owner=$owner:$group"; return 1; }
    run chmod "$USB_MOUNTPOINT_MODE" "$usb_path" || { log "mode_status=failed_nonfatal path=$usb_path mode=$USB_MOUNTPOINT_MODE"; return 1; }

    actual_owner=$(stat -c '%U:%G' "$usb_path" 2>/dev/null || echo UNKNOWN)
    actual_mode=$(stat -c '%a' "$usb_path" 2>/dev/null || echo UNKNOWN)
    log "path_status=repaired path=$usb_path owner=$actual_owner mode=$actual_mode"
    return 0
}


cleanup_usb_ip_marker_now() {
    usb_path="$1"

    [ -d "$usb_path" ] || return 0

    # Intentional exception to the mounted-USB safety rule:
    # ownership and mode repair must not touch a mounted USB filesystem, but the
    # tested fix for Moonraker spam is removing this one exact stock marker file.
    # No wildcard or recursive deletion is performed.
    # Only log when something actually happens (deletion or failure) -- the
    # not-present case is the expected steady-state after first run.
    artifact="$usb_path/ip.txt"
    if [ -e "$artifact" ] || [ -L "$artifact" ]; then
        run rm -f "$artifact" || { log "ip_marker_cleanup_status=failed_nonfatal path=$artifact"; return 1; }
        log "ip_marker_cleanup_status=removed path=$artifact"
    fi

    return 0
}

install_ip_marker_cleanup() {
    if [ "$USB_ARTIFACT_BOOT_CLEANUP" != "1" ]; then
        log "ip_marker_boot_cleanup_status=skipped_disabled_by_setting"
        return 0
    fi

    [ "$DRY_RUN" = "0" ] || {
        log "ip_marker_boot_cleanup_status=would_install service=$CLEANUP_SERVICE_NAME timer=$CLEANUP_TIMER_NAME script=$CLEANUP_SCRIPT"
        return 0
    }

    command -v systemctl >/dev/null 2>&1 || {
        log "ip_marker_boot_cleanup_status=skipped_systemctl_not_found"
        return 0
    }

    mkdir -p /usr/local/sbin "$SYSTEMD_DIR" 2>/dev/null || {
        log "ip_marker_boot_cleanup_status=failed_mkdir_nonfatal"
        return 0
    }

    cat > "$CLEANUP_SCRIPT" <<'EOF_CLEANUP'
#!/bin/sh
set -u

log_file="/tmp/arco_usb_ip_marker_cleanup.log"
if [ -d /home/mks/printer_data/logs ]; then
    log_file="/home/mks/printer_data/logs/arco_usb_ip_marker_cleanup.log"
elif [ -d /home/prz/printer_data/logs ]; then
    log_file="/home/prz/printer_data/logs/arco_usb_ip_marker_cleanup.log"
fi

log() {
    line="USB_IP_MARKER_CLEANUP: $*"
    echo "$line"
    echo "$line" >> "$log_file" 2>/dev/null || true
}

candidate_homes() {
    [ -d /home/mks/printer_data/gcodes ] && echo /home/mks
    [ -d /home/prz/printer_data/gcodes ] && echo /home/prz
}

cleanup_usb_ip_marker_now() {
    usb_path="$1"

    [ -d "$usb_path" ] || return 0

    artifact="$usb_path/ip.txt"
    if [ -e "$artifact" ] || [ -L "$artifact" ]; then
        rm -f "$artifact" 2>/dev/null || { log "ip_marker_cleanup_status=failed_nonfatal path=$artifact"; return 1; }
        log "ip_marker_cleanup_status=removed path=$artifact"
    fi

    return 0
}

candidate_count=0
cleanup_failed=0

for home in $(candidate_homes); do
    candidate_count=$((candidate_count + 1))
    cleanup_usb_ip_marker_now "$home/printer_data/gcodes/USB" || cleanup_failed=1
done

if [ "$candidate_count" -eq 0 ]; then
    log "status=skipped_no_candidate_paths"
elif [ "$cleanup_failed" -ne 0 ]; then
    log "status=completed_with_nonfatal_errors"
fi

exit 0
EOF_CLEANUP

    chmod 755 "$CLEANUP_SCRIPT" 2>/dev/null || log "ip_marker_cleanup_script_chmod_status=failed_nonfatal"

    cat > "$SYSTEMD_DIR/$CLEANUP_SERVICE_NAME" <<EOF_CLEANUP_SERVICE
[Unit]
Description=ARCO remove stock USB ip.txt marker
After=local-fs.target moonraker.service

[Service]
Type=oneshot
ExecStart=$CLEANUP_SCRIPT
EOF_CLEANUP_SERVICE

    cat > "$SYSTEMD_DIR/$CLEANUP_TIMER_NAME" <<EOF_CLEANUP_TIMER
[Unit]
Description=Run ARCO USB ip.txt marker cleanup after boot

[Timer]
OnBootSec=${USB_ARTIFACT_CLEANUP_ONBOOT_SECONDS}
OnUnitActiveSec=${USB_ARTIFACT_CLEANUP_TIMER_SECONDS}
Persistent=true
Unit=$CLEANUP_SERVICE_NAME

[Install]
WantedBy=timers.target
EOF_CLEANUP_TIMER

    log "ip_marker_boot_cleanup_status=unit_files_installed service=$CLEANUP_SERVICE_NAME timer=$CLEANUP_TIMER_NAME script=$CLEANUP_SCRIPT"
    systemctl daemon-reload >/dev/null 2>&1 || log "ip_marker_systemd_daemon_reload_status=failed_nonfatal"
    if systemctl enable --now "$CLEANUP_TIMER_NAME" >/dev/null 2>&1; then
        log "ip_marker_boot_cleanup_status=enabled timer=$CLEANUP_TIMER_NAME onboot_seconds=$USB_ARTIFACT_CLEANUP_ONBOOT_SECONDS retry_seconds=$USB_ARTIFACT_CLEANUP_TIMER_SECONDS"
    else
        log "ip_marker_boot_cleanup_status=failed_enable_nonfatal timer=$CLEANUP_TIMER_NAME"
    fi
}


archive_stale_firmware() {
    usb_path="$1"
    archive_dir="$(dirname "$usb_path")/_kaos_archived_firmware"
    found=0

    for pattern in '*_H1I1_*' '*_H7I7_*' '*_H11I11_*'; do
        for f in "$usb_path"/$pattern; do
            [ -e "$f" ] || continue
            base=$(basename "$f")
            run mkdir -p "$archive_dir" || { log "firmware_archive_status=failed_mkdir_nonfatal path=$archive_dir"; continue; }
            dest="$archive_dir/$base"
            if [ -e "$dest" ]; then
                dest="$archive_dir/${base}.$(date +%Y%m%d%H%M%S).$$"
            fi
            if run mv "$f" "$dest"; then
                log "firmware_archive_status=moved file=$base dest=$dest"
                found=1
            else
                log "firmware_archive_status=failed_move_nonfatal file=$base dest=$dest"
            fi
        done
    done

    if [ "$found" -eq 0 ]; then
        log "firmware_archive_status=none_found path=$usb_path"
    fi
}

install_deferred_repair() {
    STAMP_FILE="/var/lib/arco-system-prep/usb-mountpoint-fixed-v2.stamp"

    if [ -f "$STAMP_FILE" ]; then
        log "deferred_service_status=skipped_already_completed stamp=$STAMP_FILE"
        return 0
    fi

    [ "$DRY_RUN" = "0" ] || {
        log "deferred_service_status=would_install service=$SERVICE_NAME timer=$TIMER_NAME script=$DEFERRED_SCRIPT"
        return 0
    }

    command -v systemctl >/dev/null 2>&1 || {
        log "deferred_service_status=skipped_systemctl_not_found"
        return 0
    }

    mkdir -p /usr/local/sbin "$SYSTEMD_DIR" 2>/dev/null || {
        log "deferred_service_status=failed_mkdir_nonfatal"
        return 0
    }

    cat > "$DEFERRED_SCRIPT" <<'EOF_DEFERRED'
#!/bin/sh
set -u

USB_MOUNTPOINT_MODE="${USB_MOUNTPOINT_MODE:-775}"
USB_MOUNTPOINT_GROUP="${USB_MOUNTPOINT_GROUP:-netdev}"
SERVICE_NAME="arco-fix-usb-mountpoint-deferred.service"
TIMER_NAME="arco-fix-usb-mountpoint-deferred.timer"
STAMP_FILE="/var/lib/arco-system-prep/usb-mountpoint-fixed-v2.stamp"

log_file="/tmp/arco_usb_mountpoint_fix_deferred.log"
if [ -d /home/mks/printer_data/logs ]; then
    log_file="/home/mks/printer_data/logs/arco_usb_mountpoint_fix_deferred.log"
elif [ -d /home/prz/printer_data/logs ]; then
    log_file="/home/prz/printer_data/logs/arco_usb_mountpoint_fix_deferred.log"
fi

log() {
    line="USB_MOUNTPOINT_FIX_DEFERRED: $*"
    echo "$line"
    echo "$line" >> "$log_file" 2>/dev/null || true
}

candidate_homes() {
    [ -d /home/mks/printer_data/gcodes ] && echo /home/mks
    [ -d /home/prz/printer_data/gcodes ] && echo /home/prz
}

is_mounted() {
    path="$1"
    if command -v mountpoint >/dev/null 2>&1; then
        mountpoint -q "$path"
        return $?
    fi
    awk -v p="$path" '$2 == p { found=1 } END { exit found ? 0 : 1 }' /proc/mounts 2>/dev/null
}

owner_for_home() {
    home="$1"
    base_owner=$(basename "$home")
    if id "$base_owner" >/dev/null 2>&1; then
        printf '%s' "$base_owner"
    else
        stat -c '%U' "$home" 2>/dev/null || printf '%s' "$base_owner"
    fi
}

group_for_owner() {
    owner="$1"
    if getent group "$USB_MOUNTPOINT_GROUP" >/dev/null 2>&1; then
        printf '%s' "$USB_MOUNTPOINT_GROUP"
    else
        id -gn "$owner" 2>/dev/null || printf '%s' "$owner"
    fi
}

repair_path_now() {
    usb_path="$1"
    home="$2"
    owner=$(owner_for_home "$home")
    group=$(group_for_owner "$owner")

    mkdir -p "$usb_path" 2>/dev/null || { log "path_status=failed_mkdir_nonfatal path=$usb_path"; return 1; }
    chown "$owner:$group" "$usb_path" 2>/dev/null || { log "owner_status=failed_nonfatal path=$usb_path owner=$owner:$group"; return 1; }
    chmod "$USB_MOUNTPOINT_MODE" "$usb_path" 2>/dev/null || { log "mode_status=failed_nonfatal path=$usb_path mode=$USB_MOUNTPOINT_MODE"; return 1; }

    actual_owner=$(stat -c '%U:%G' "$usb_path" 2>/dev/null || echo UNKNOWN)
    actual_mode=$(stat -c '%a' "$usb_path" 2>/dev/null || echo UNKNOWN)
    log "path_status=repaired path=$usb_path owner=$actual_owner mode=$actual_mode"
    return 0
}

disable_self() {
    if command -v systemctl >/dev/null 2>&1; then
        systemctl --no-block disable --now "$TIMER_NAME" >/dev/null 2>&1 || true
        systemctl --no-block disable "$SERVICE_NAME" >/dev/null 2>&1 || true
        log "deferred_timer_status=disabled_after_success"
    fi
}

log "script_started_at=$(date)"
mounted_count=0
candidate_count=0
repair_failed=0

for home in $(candidate_homes); do
    candidate_count=$((candidate_count + 1))
    usb_path="$home/printer_data/gcodes/USB"
    if [ -d "$usb_path" ] && is_mounted "$usb_path"; then
        mounted_count=$((mounted_count + 1))
        log "status=still_mounted_retry_later path=$usb_path"
        continue
    fi

    repair_path_now "$usb_path" "$home" || repair_failed=1
done

if [ "$candidate_count" -eq 0 ]; then
    log "status=skipped_no_candidate_paths"
    exit 0
fi

if [ "$mounted_count" -gt 0 ]; then
    log "status=deferred_waiting_for_unmount mounted_count=$mounted_count"
    exit 0
fi

if [ "$repair_failed" -eq 0 ]; then
    mkdir -p "$(dirname "$STAMP_FILE")" 2>/dev/null || true
    echo "completed_at=$(date)" > "$STAMP_FILE" 2>/dev/null || true
    log "status=completed"
    disable_self
else
    log "status=completed_with_nonfatal_errors"
fi

log "script_finished_at=$(date)"
exit 0
EOF_DEFERRED

    chmod 755 "$DEFERRED_SCRIPT" 2>/dev/null || log "deferred_script_chmod_status=failed_nonfatal"

    cat > "$SYSTEMD_DIR/$SERVICE_NAME" <<EOF_SERVICE
[Unit]
Description=ARCO deferred USB mountpoint ownership repair
After=local-fs.target

[Service]
Type=oneshot
ExecStart=$DEFERRED_SCRIPT
EOF_SERVICE

    cat > "$SYSTEMD_DIR/$TIMER_NAME" <<EOF_TIMER
[Unit]
Description=Retry ARCO USB mountpoint ownership repair until USB is removed

[Timer]
OnBootSec=60
OnUnitActiveSec=${USB_MOUNTPOINT_DEFER_TIMER_SECONDS}
Persistent=true
Unit=$SERVICE_NAME

[Install]
WantedBy=timers.target
EOF_TIMER

    systemctl daemon-reload >/dev/null 2>&1 || log "deferred_systemd_daemon_reload_status=failed_nonfatal"
    if systemctl enable --now "$TIMER_NAME" >/dev/null 2>&1; then
        log "deferred_timer_status=enabled timer=$TIMER_NAME retry_seconds=$USB_MOUNTPOINT_DEFER_TIMER_SECONDS"
    else
        log "deferred_timer_status=failed_enable_nonfatal timer=$TIMER_NAME"
    fi
    log "deferred_service_status=installed service=$SERVICE_NAME script=$DEFERRED_SCRIPT"
}

log "script_started_at=$(date)"
if [ "$DRY_RUN" = "1" ]; then
    log "mode=dry_run"
else
    log "mode=apply"
fi
log "USB_MOUNTPOINT_MODE=$USB_MOUNTPOINT_MODE"
log "USB_MOUNTPOINT_GROUP=$USB_MOUNTPOINT_GROUP"
log "USB_MOUNTPOINT_DEFER_TIMER_SECONDS=$USB_MOUNTPOINT_DEFER_TIMER_SECONDS"
log "USB_ARTIFACT_BOOT_CLEANUP=$USB_ARTIFACT_BOOT_CLEANUP"
log "USB_ARTIFACT_CLEANUP_ONBOOT_SECONDS=$USB_ARTIFACT_CLEANUP_ONBOOT_SECONDS"
log "USB_ARTIFACT_CLEANUP_TIMER_SECONDS=$USB_ARTIFACT_CLEANUP_TIMER_SECONDS"

if [ "$(id -u)" != "0" ]; then
    log "status=failed_requires_root"
    exit 1
fi

candidate_count=0
mounted_count=0
repair_failed=0

for home in $(candidate_homes); do
    candidate_count=$((candidate_count + 1))
    usb_path="$home/printer_data/gcodes/USB"
    log "candidate_path=$usb_path"

    if [ -d "$usb_path" ] && is_mounted "$usb_path"; then
        mounted_count=$((mounted_count + 1))
        log "path_status=mounted_defer_ownership_repair path=$usb_path"
        if [ "$USB_ARTIFACT_BOOT_CLEANUP" = "1" ]; then
            cleanup_usb_ip_marker_now "$usb_path" || repair_failed=1
        fi
        continue
    fi

    repair_path_now "$usb_path" "$home" || repair_failed=1
    archive_stale_firmware "$usb_path"
    if [ "$USB_ARTIFACT_BOOT_CLEANUP" = "1" ]; then
        cleanup_usb_ip_marker_now "$usb_path" || repair_failed=1
    fi
done

if [ "$candidate_count" -eq 0 ]; then
    log "status=skipped_no_candidate_paths"
    log "script_finished_at=$(date)"
    exit 0
fi

install_ip_marker_cleanup

if [ "$mounted_count" -gt 0 ]; then
    install_deferred_repair
    if [ "$repair_failed" -eq 0 ]; then
        log "status=deferred_usb_currently_mounted mounted_count=$mounted_count"
    else
        log "status=deferred_usb_currently_mounted_with_nonfatal_errors mounted_count=$mounted_count"
    fi
elif [ "$repair_failed" -eq 0 ]; then
    log "status=completed"
else
    log "status=completed_with_nonfatal_errors"
fi

log "script_finished_at=$(date)"
exit 0
