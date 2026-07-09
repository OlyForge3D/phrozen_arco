#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# ARCO System Prep helper: trim non-essential background services.
# Purpose: reduce automatic package churn, idle daemons, and low-value monitoring on constrained Arco systems.
# This script deliberately does NOT disable OctoEverywhere, Klipper, Moonraker, nginx, crowsnest, KlipperScreen, Wi-Fi, SSH, rng-tools, or Makerbase services.

set -u

# Section switches. 1 = disable/mask, 0 = report only/skip.
Disable_APT_Timers="${Disable_APT_Timers:-1}"
Disable_Unattended_Upgrades="${Disable_Unattended_Upgrades:-1}"
Disable_PackageKit="${Disable_PackageKit:-1}"
Disable_RPCBind="${Disable_RPCBind:-1}"
Disable_Sysstat="${Disable_Sysstat:-1}"
Disable_SMART_Monitoring="${Disable_SMART_Monitoring:-1}"
Disable_RSync="${Disable_RSync:-1}"
Disable_HAVEGED="${Disable_HAVEGED:-1}"

# Safer default: mask services after disabling so package updates do not silently re-enable them.
Mask_Disabled_Units="${Mask_Disabled_Units:-1}"

log() { echo "SERVICE_TRIM: $*"; }

unit_exists() {
    unit="$1"
    systemctl list-unit-files "$unit" 2>/dev/null | awk '{ print $1 }' | grep -Fxq "$unit"
}

unit_state() {
    state=$(systemctl is-enabled "$1" 2>/dev/null || true)
    if [ -n "$state" ]; then
        echo "$state"
    else
        echo "unknown"
    fi
}

unit_active() {
    state=$(systemctl is-active "$1" 2>/dev/null || true)
    if [ -n "$state" ]; then
        echo "$state"
    else
        echo "unknown"
    fi
}

log_unit_before() {
    unit="$1"
    if unit_exists "$unit"; then
        log "${unit}_before_enabled=$(unit_state "$unit")"
        log "${unit}_before_active=$(unit_active "$unit")"
    else
        log "${unit}_status=not_installed"
    fi
}

log_unit_after() {
    unit="$1"
    if unit_exists "$unit"; then
        log "${unit}_after_enabled=$(unit_state "$unit")"
        log "${unit}_after_active=$(unit_active "$unit")"
    else
        log "${unit}_after_status=not_installed"
    fi
}

disable_unit() {
    unit="$1"
    label="$2"
    enable_switch="$3"

    log "${label}_begin"
    log "${label}_target=$unit"
    log "${label}_enabled_setting=$enable_switch"
    log_unit_before "$unit"

    if [ "$enable_switch" != "1" ]; then
        log "${label}_status=skipped_disabled_by_setting"
        log "${label}_end"
        return 0
    fi

    if ! unit_exists "$unit"; then
        log "${label}_status=skipped_unit_not_found"
        log "${label}_end"
        return 0
    fi

    # Stop first so currently running helpers go away immediately.
    if systemctl stop "$unit" >/dev/null 2>&1; then
        log "${label}_stop_status=stopped_or_already_inactive"
    else
        log "${label}_stop_status=failed_nonfatal"
    fi

    if systemctl disable "$unit" >/dev/null 2>&1; then
        log "${label}_disable_status=disabled"
    else
        log "${label}_disable_status=failed_nonfatal"
    fi

    if [ "$Mask_Disabled_Units" = "1" ]; then
        if systemctl mask "$unit" >/dev/null 2>&1; then
            log "${label}_mask_status=masked"
        else
            log "${label}_mask_status=failed_nonfatal"
        fi
    else
        log "${label}_mask_status=skipped_by_setting"
    fi

    log_unit_after "$unit"
    log "${label}_status=completed"
    log "${label}_end"
    return 0
}

disable_units_group() {
    label="$1"
    enable_switch="$2"
    shift 2

    log "${label}_group_begin"
    log "${label}_group_enabled_setting=$enable_switch"

    for unit in "$@"; do
        safe_label=$(echo "$unit" | tr '.@-' '___')
        disable_unit "$unit" "${label}_${safe_label}" "$enable_switch"
    done

    log "${label}_group_end"
}

log "script_started_at=$(date)"
log "Disable_APT_Timers=$Disable_APT_Timers"
log "Disable_Unattended_Upgrades=$Disable_Unattended_Upgrades"
log "Disable_PackageKit=$Disable_PackageKit"
log "Disable_RPCBind=$Disable_RPCBind"
log "Disable_Sysstat=$Disable_Sysstat"
log "Disable_SMART_Monitoring=$Disable_SMART_Monitoring"
log "Disable_RSync=$Disable_RSync"
log "Disable_HAVEGED=$Disable_HAVEGED"
log "Mask_Disabled_Units=$Mask_Disabled_Units"
log "octoeverywhere_status=left_unchanged_by_design"
log "core_printer_services_status=left_unchanged_by_design"

# Automatic apt maintenance: avoid surprise package work on a vendor-customized legacy Buster printer.
disable_units_group "apt_timers" "$Disable_APT_Timers" \
    apt-daily.timer \
    apt-daily-upgrade.timer

# Unattended upgrades shutdown helper: can sit resident and consume memory.
disable_units_group "unattended_upgrades" "$Disable_Unattended_Upgrades" \
    unattended-upgrades.service

# PackageKit daemon/timer: desktop-style package management is unnecessary on a printer appliance.
# Updates are managed deliberately through System Prep/KIAUH/apt instead.
disable_units_group "packagekit" "$Disable_PackageKit" \
    packagekit.service \
    packagekit-offline-update.service \
    packagekit.timer

# RPC/NFS-related services. Usually unnecessary on a printer.
disable_units_group "rpcbind" "$Disable_RPCBind" \
    rpcbind.service \
    portmap.service

# Performance statistics collector. Useful for diagnostics, not required for printing.
disable_units_group "sysstat" "$Disable_Sysstat" \
    sysstat.service

# SMART monitoring. Often low value/failed on eMMC-based systems.
disable_units_group "smart_monitoring" "$Disable_SMART_Monitoring" \
    smartd.service \
    smartmontools.service

# rsync daemon. Not needed unless the printer is intentionally acting as an rsync server.
disable_units_group "rsync" "$Disable_RSync" \
    rsync.service

# HAVEGE entropy daemon. Often redundant on modern kernels and was observed failed on stock Arco audits.
# Leave rng-tools alone; this only disables the failed/low-value haveged service.
disable_units_group "haveged" "$Disable_HAVEGED" \
    haveged.service

# Reset failed state so old failures do not keep showing after disabled/masked units are handled.
if systemctl reset-failed >/dev/null 2>&1; then
    log "reset_failed_status=completed"
else
    log "reset_failed_status=failed_nonfatal"
fi

log "script_finished_at=$(date)"
exit 0
