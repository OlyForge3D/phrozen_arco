#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# ARCO System Prep helper: clean up known stock networking service failures.
# This helper only handles the specific stock Arco issues documented below.
#
# Usage:
#   sudo ./fix-stock-network-services.sh
#   sudo ./fix-stock-network-services.sh --dry-run

set -u

DRY_RUN=0
# 1 = restart networking.service immediately after removing stale active
#     interface config. Default 0 for touchscreen-safe USB installs; the
#     final installer reboot applies the networking change without bouncing
#     voronFDM/Makerbase communication mid-install.
: "${Restart_Networking_After_Stock_Network_Fix:=0}"

case "${1:-}" in
    "")
        ;;
    --dry-run)
        DRY_RUN=1
        ;;
    *)
        echo "Usage: $0 [--dry-run]" >&2
        exit 2
        ;;
esac

log() { echo "STOCK_NETWORK_FIX: $*"; }

run() {
    if [ "$DRY_RUN" = "1" ]; then
        printf 'STOCK_NETWORK_FIX: dry_run_command='
        printf ' %s' "$@"
        printf '\n'
        return 0
    fi
    "$@"
}

unit_exists() {
    unit="$1"
    systemctl list-unit-files "$unit" --no-legend 2>/dev/null |
        awk '{print $1}' |
        grep -Fxq "$unit"
}

unit_enabled_state() {
    state="$(systemctl is-enabled "$1" 2>/dev/null || true)"
    [ -n "$state" ] || state="unknown"
    printf '%s' "$state"
}

unit_active_state() {
    state="$(systemctl is-active "$1" 2>/dev/null || true)"
    [ -n "$state" ] || state="unknown"
    printf '%s' "$state"
}

disable_unit() {
    unit="$1"
    label="$2"

    if ! unit_exists "$unit"; then
        log "${label}_status=not_installed"
        return 0
    fi

    before_enabled="$(unit_enabled_state "$unit")"
    before_active="$(unit_active_state "$unit")"
    log "${label}_before_enabled=$before_enabled"
    log "${label}_before_active=$before_active"

    if [ "$before_enabled" = "disabled" ] && [ "$before_active" = "inactive" ]; then
        log "${label}_disable_status=already_disabled"
        if [ "$DRY_RUN" = "0" ]; then
            systemctl reset-failed "$unit" >/dev/null 2>&1 || true
        fi
        return 0
    fi

    if [ "$DRY_RUN" = "1" ]; then
        run systemctl disable --now "$unit"
        run systemctl reset-failed "$unit"
        log "${label}_disable_status=would_disable"
        return 0
    fi

    if systemctl disable --now "$unit" >/dev/null 2>&1; then
        log "${label}_disable_status=completed"
    else
        log "${label}_disable_status=failed_nonfatal"
    fi

    systemctl reset-failed "$unit" >/dev/null 2>&1 || true

    log "${label}_after_enabled=$(unit_enabled_state "$unit")"
    log "${label}_after_active=$(unit_active_state "$unit")"
}

log "script_started_at=$(date)"
if [ "$DRY_RUN" = "1" ]; then
    log "mode=dry_run"
else
    log "mode=apply"
fi
log "Restart_Networking_After_Stock_Network_Fix=$Restart_Networking_After_Stock_Network_Fix"

# Stock USB Wi-Fi import service.
# It cannot succeed when its expected source file is absent. Preserve it when
# the file exists so users can still use the stock USB Wi-Fi import workflow.
NET_MODS_SERVICE="makerbase-net-mods.service"
NET_MODS_SOURCE="/home/mks/printer_data/gcodes/USB/wpa_supplicant-wlan0.conf"

if unit_exists "$NET_MODS_SERVICE"; then
    if [ -f "$NET_MODS_SOURCE" ]; then
        log "makerbase_net_mods_source=present"
        log "makerbase_net_mods_status=left_enabled"
        if [ "$DRY_RUN" = "1" ]; then
            run systemctl reset-failed "$NET_MODS_SERVICE"
        else
            systemctl reset-failed "$NET_MODS_SERVICE" >/dev/null 2>&1 || true
        fi
    else
        log "makerbase_net_mods_source=missing"
        disable_unit "$NET_MODS_SERVICE" "makerbase_net_mods"
    fi
else
    log "makerbase_net_mods_status=not_installed"
fi

# Stock Makerbase UDP server.
# The vendor unit is Type=oneshot even though /root/udp_server remains in the
# foreground, leaving the service stuck in activating until systemd kills it.
# It is not required by Klipper, Moonraker, Fluidd, Mainsail, nginx, or Crowsnest.
disable_unit "makerbase-udp.service" "makerbase_udp"

# Remove the stale CAN definition only when no can0 device exists.
# Move it fully outside interfaces.d because broad source globs may parse files
# regardless of their extension.
CAN_FILE="/etc/network/interfaces.d/can0"
CAN_CHANGED=0

if [ -f "$CAN_FILE" ]; then
    if ip link show can0 >/dev/null 2>&1; then
        log "can0_device=present"
        log "can0_config_status=left_unchanged"
    else
        timestamp="$(date +%Y%m%d_%H%M%S)"
        backup_dir="/root/arco-system-prep-backups/stock-network-services-$timestamp"

        log "can0_device=missing"
        if [ "$DRY_RUN" = "1" ]; then
            run mkdir -p "$backup_dir"
            run cp -a "$CAN_FILE" "$backup_dir/can0.original"
            run mv "$CAN_FILE" "$backup_dir/can0.disabled"
            log "can0_config_status=would_remove_from_interfaces_d"
            log "can0_backup_would_be=$backup_dir/can0.original"
            CAN_CHANGED=1
        else
            mkdir -p "$backup_dir"
            if cp -a "$CAN_FILE" "$backup_dir/can0.original" &&
               mv "$CAN_FILE" "$backup_dir/can0.disabled"; then
                log "can0_config_status=removed_from_interfaces_d"
                log "can0_backup=$backup_dir/can0.original"
                CAN_CHANGED=1
            else
                log "can0_config_status=backup_or_move_failed_nonfatal"
            fi
        fi
    fi
else
    log "can0_config_status=not_present"
fi

# Restarting networking can briefly disturb the stock Phrozen/voronFDM
# touchscreen update path. For USB-driven System Prep installs, defer this to
# the final reboot by default. The immediate restart remains available for
# manual/SSH repair runs by setting Restart_Networking_After_Stock_Network_Fix=1.
if [ "$CAN_CHANGED" = "1" ]; then
    if [ "$Restart_Networking_After_Stock_Network_Fix" != "1" ]; then
        log "networking_restart_status=skipped_deferred_until_reboot"
    elif unit_exists "networking.service"; then
        if [ "$DRY_RUN" = "1" ]; then
            run systemctl restart networking.service
            run systemctl reset-failed networking.service
            log "networking_restart_status=would_restart"
        else
            if systemctl restart networking.service >/dev/null 2>&1; then
                log "networking_restart_status=completed"
            else
                log "networking_restart_status=failed_nonfatal"
                systemctl status networking.service --no-pager -l 2>/dev/null |
                    sed 's/^/STOCK_NETWORK_FIX: /' || true
            fi
            systemctl reset-failed networking.service >/dev/null 2>&1 || true
        fi
    else
        log "networking_restart_status=skipped_service_not_installed"
    fi
else
    log "networking_restart_status=skipped_no_active_interface_change"
fi

if [ "$DRY_RUN" = "1" ]; then
    log "verification_status=skipped_in_dry_run"
else
    systemctl reset-failed makerbase-net-mods.service makerbase-udp.service networking.service \
        >/dev/null 2>&1 || true

    log "remaining_failed_units_begin"
    (systemctl --failed --no-legend --no-pager 2>/dev/null || true) |
        sed 's/^/STOCK_NETWORK_FIX: /'
    log "remaining_failed_units_end"
fi

log "script_finished_at=$(date)"

# Known cleanup failures are nonfatal to the wider System Prep workflow.
exit 0
