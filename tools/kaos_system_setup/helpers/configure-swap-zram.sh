#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# ARCO System Prep helper: optional guarded swap/ZRAM setup.
# Default policy: disabled by installer unless Configure_Swap_ZRAM=1.
# Safety policy:
# - Report current memory, swap, ZRAM, and disk state first.
# - If root free space is below Minimum_Free_MB_For_Swap, make no modifications at all.
# - If non-ZRAM swap already exists, do not create or repair a swapfile and do not modify ZRAM.
# - If only ZRAM swap exists and root is a large eMMC/root volume, still create a disk swapfile at lower priority than stock ZRAM.
# - Disk swapfile creation also requires enough free space to preserve Minimum_Free_MB_For_Swap after creation.
# - ZRAM is only modified if Manage_ZRAM=1, no active swap exists, and all safety guards pass.

set -u

Minimum_Free_MB_For_Swap="${Minimum_Free_MB_For_Swap:-5120}"
Minimum_Root_Total_MB_For_Disk_Swap="${Minimum_Root_Total_MB_For_Disk_Swap:-16384}"
Disk_Swap_Size_MB="${Disk_Swap_Size_MB:-2048}"
Swapfile_Path="${Swapfile_Path:-/swapfile}"
Swapfile_Priority="${Swapfile_Priority:-1}"
# Swappiness tuning is intentionally separate from swapfile creation.
# It is harmless if no new swapfile is created and useful when stock ZRAM/swap already exists.
Tune_Swappiness="${Tune_Swappiness:-1}"
Swappiness_Value="${Swappiness_Value:-10}"
Manage_ZRAM="${Manage_ZRAM:-0}"
ZRAM_PERCENTAGE="${ZRAM_PERCENTAGE:-25}"
ZRAM_CORES="${ZRAM_CORES:-1}"
ZRAM_ALGO="${ZRAM_ALGO:-lz4}"
ZRAM_DEFAULT_FILE="${ZRAM_DEFAULT_FILE:-/etc/default/zramswap}"

timestamp=$(date +%Y%m%d_%H%M%S)

log() {
    echo "ARCO_SWAP_ZRAM: $*"
}

warn() {
    echo "ARCO_SWAP_ZRAM_WARNING: $*"
}

root_free_mb() {
    df -Pm / 2>/dev/null | awk 'NR==2 { print $4 }'
}

root_total_mb() {
    df -Pm / 2>/dev/null | awk 'NR==2 { print $2 }'
}

active_swap_count() {
    awk 'NR>1 { c++ } END { print c+0 }' /proc/swaps 2>/dev/null
}

active_zram_swap_count() {
    awk 'NR>1 && $1 ~ /^\/dev\/zram/ { c++ } END { print c+0 }' /proc/swaps 2>/dev/null
}

active_non_zram_swap_count() {
    awk 'NR>1 && $1 !~ /^\/dev\/zram/ { c++ } END { print c+0 }' /proc/swaps 2>/dev/null
}

swapfile_active() {
    awk -v p="$Swapfile_Path" 'NR>1 && $1 == p { found=1 } END { exit found ? 0 : 1 }' /proc/swaps 2>/dev/null
}

active_swapfile_priority() {
    awk -v p="$Swapfile_Path" 'NR>1 && $1 == p { print $5; found=1 } END { exit found ? 0 : 1 }' /proc/swaps 2>/dev/null
}

repair_active_swapfile_priority() {
    current_priority=$(active_swapfile_priority 2>/dev/null || true)

    if [ "$current_priority" = "$Swapfile_Priority" ]; then
        log "swapfile_priority_status=already_correct priority=$Swapfile_Priority"
        return 0
    fi

    log "swapfile_priority_status=repairing current=${current_priority:-unknown} desired=$Swapfile_Priority"

    if swapoff "$Swapfile_Path" 2>/dev/null && swapon -p "$Swapfile_Priority" "$Swapfile_Path" 2>/dev/null; then
        log "swapfile_priority_status=repaired priority=$Swapfile_Priority"
        return 0
    fi

    log "swapfile_priority_status=repair_failed_nonfatal current=${current_priority:-unknown} desired=$Swapfile_Priority"
    return 1
}

comment_conflicting_swappiness() {
    # sysctl --system applies /etc/sysctl.d/*.conf and then /etc/sysctl.conf.
    # Stock Arco images can define vm.swappiness=100 in later files, which
    # overrides the KAOS value even when /etc/sysctl.d/99-arco-system-prep.conf
    # is present. Comment active duplicate swappiness assignments outside the
    # KAOS-owned file so the runtime value remains stable after reload/reboot.
    kaos_sysctl_file="$1"

    for candidate in /etc/sysctl.d/*.conf /etc/sysctl.conf; do
        [ -f "$candidate" ] || continue
        [ "$candidate" = "$kaos_sysctl_file" ] && continue

        if grep -Eq '^[[:space:]]*vm\.swappiness[[:space:]]*=' "$candidate" 2>/dev/null; then
            cp -f "$candidate" "$candidate.kaos_backup_${timestamp}_$$" 2>/dev/null || true
            if sed -i 's/^[[:space:]]*vm\.swappiness[[:space:]]*=.*/# vm.swappiness overridden by ARCO System Prep/' "$candidate" 2>/dev/null; then
                log "swappiness_conflict_status=commented path=$candidate"
            else
                log "swappiness_conflict_status=failed_nonfatal path=$candidate"
            fi
        fi
    done
}

configure_swappiness() {
    [ "$Tune_Swappiness" = "1" ] || { log "swappiness_status=skipped_by_setting"; return 0; }

    sysctl_file="/etc/sysctl.d/99-arco-system-prep.conf"
    if [ -f "$sysctl_file" ]; then
        cp -f "$sysctl_file" "$sysctl_file.kaos_backup_${timestamp}_$$" 2>/dev/null || true
    fi

    mkdir -p /etc/sysctl.d 2>/dev/null || true
    if [ -f "$sysctl_file" ] && grep -Eq '^[[:space:]]*vm\.swappiness[[:space:]]*=' "$sysctl_file" 2>/dev/null; then
        sed -i "s/^[[:space:]]*vm\.swappiness[[:space:]]*=.*/vm.swappiness=$Swappiness_Value/" "$sysctl_file" 2>/dev/null || true
    else
        echo "vm.swappiness=$Swappiness_Value" >> "$sysctl_file" 2>/dev/null || {
            log "swappiness_status=failed_nonfatal"
            return 0
        }
    fi

    comment_conflicting_swappiness "$sysctl_file"

    sysctl -w "vm.swappiness=$Swappiness_Value" >/dev/null 2>&1 || true
    log "swappiness_status=configured value=$Swappiness_Value"
}

configure_zram_if_enabled() {
    [ "$Manage_ZRAM" = "1" ] || { log "zram_config_status=skipped_disabled"; return 0; }

    if [ -f "$ZRAM_DEFAULT_FILE" ]; then
        cp -f "$ZRAM_DEFAULT_FILE" "$ZRAM_DEFAULT_FILE.kaos_backup_${timestamp}_$$" 2>/dev/null || true

        if grep -q '^CORES=' "$ZRAM_DEFAULT_FILE" 2>/dev/null; then
            sed -i "s/^CORES=.*/CORES=$ZRAM_CORES/" "$ZRAM_DEFAULT_FILE" 2>/dev/null || true
        else
            echo "CORES=$ZRAM_CORES" >> "$ZRAM_DEFAULT_FILE" 2>/dev/null || true
        fi

        if grep -q '^PERCENTAGE=' "$ZRAM_DEFAULT_FILE" 2>/dev/null; then
            sed -i "s/^PERCENTAGE=.*/PERCENTAGE=$ZRAM_PERCENTAGE/" "$ZRAM_DEFAULT_FILE" 2>/dev/null || true
        else
            echo "PERCENTAGE=$ZRAM_PERCENTAGE" >> "$ZRAM_DEFAULT_FILE" 2>/dev/null || true
        fi

        if grep -q '^ALGO=' "$ZRAM_DEFAULT_FILE" 2>/dev/null; then
            sed -i "s/^ALGO=.*/ALGO=$ZRAM_ALGO/" "$ZRAM_DEFAULT_FILE" 2>/dev/null || true
        else
            echo "ALGO=$ZRAM_ALGO" >> "$ZRAM_DEFAULT_FILE" 2>/dev/null || true
        fi

        log "zram_config_status=updated path=$ZRAM_DEFAULT_FILE"
        log "zram_config_note=reboot_required_for_zram_changes"
    else
        log "zram_config_status=skipped_default_file_missing path=$ZRAM_DEFAULT_FILE"
    fi
}

ensure_fstab_swap() {
    desired_line="$Swapfile_Path none swap sw,pri=$Swapfile_Priority 0 0"

    cp -f /etc/fstab "/etc/fstab.kaos_swap_backup.${timestamp}_$$" 2>/dev/null || true

    tmp_fstab="/tmp/arco_fstab_swap.$$"

    # Always rewrite active /swapfile swap entries to exactly one canonical line.
    # This prevents repeated prep runs from accumulating duplicate fstab entries.
    if awk -v p="$Swapfile_Path" -v repl="$desired_line" '
        BEGIN { wrote=0; removed=0 }
        $0 !~ /^[[:space:]]*#/ && $1 == p && $2 == "none" && $3 == "swap" {
            if (!wrote) {
                print repl
                wrote=1
            }
            removed++
            next
        }
        { print }
        END {
            if (!wrote) {
                print repl
            }
        }
    ' /etc/fstab > "$tmp_fstab" 2>/dev/null && cat "$tmp_fstab" > /etc/fstab 2>/dev/null; then
        if grep -Eq "^[^#][[:space:]]*$Swapfile_Path[[:space:]]+none[[:space:]]+swap[[:space:]]+[^[:space:]]*pri=$Swapfile_Priority" /etc/fstab 2>/dev/null; then
            log "fstab_swap_status=canonical priority=$Swapfile_Priority"
        else
            log "fstab_swap_status=canonicalize_warning_nonfatal priority=$Swapfile_Priority"
        fi
    else
        log "fstab_swap_status=canonicalize_failed_nonfatal"
    fi

    rm -f "$tmp_fstab" 2>/dev/null || true
}

create_swapfile() {
    required_after_create_mb=$((Minimum_Free_MB_For_Swap + Disk_Swap_Size_MB))
    current_root_free_mb=$(root_free_mb)
    [ -n "$current_root_free_mb" ] || current_root_free_mb=0
    current_root_total_mb=$(root_total_mb)
    [ -n "$current_root_total_mb" ] || current_root_total_mb=0

    if [ "$current_root_total_mb" -lt "$Minimum_Root_Total_MB_For_Disk_Swap" ]; then
        log "swap_setup_status=skipped_root_total_below_large_emmc_threshold"
        log "root_total_mb=$current_root_total_mb"
        log "minimum_root_total_mb_for_disk_swap=$Minimum_Root_Total_MB_For_Disk_Swap"
        return 0
    fi

    if swapfile_active; then
        log "swapfile_status=already_active path=$Swapfile_Path"
        repair_active_swapfile_priority || true
        ensure_fstab_swap
        log "swap_setup_status=already_active"
        return 0
    fi

    if [ "$current_root_free_mb" -lt "$required_after_create_mb" ]; then
        warn "free space passed threshold but not enough to create requested swapfile while preserving threshold"
        log "swap_setup_status=skipped_not_enough_headroom_for_requested_swapfile"
        log "required_free_mb_for_create=$required_after_create_mb"
        return 0
    fi

    if [ -f "$Swapfile_Path" ]; then
        log "swapfile_file_status=already_exists path=$Swapfile_Path"
    else
        log "swapfile_file_status=creating path=$Swapfile_Path size_mb=$Disk_Swap_Size_MB"
        if command -v fallocate >/dev/null 2>&1 && fallocate -l "${Disk_Swap_Size_MB}M" "$Swapfile_Path" 2>/dev/null; then
            log "swapfile_allocate_method=fallocate"
        else
            log "swapfile_allocate_method=dd"
            dd if=/dev/zero of="$Swapfile_Path" bs=1M count="$Disk_Swap_Size_MB" 2>/dev/null || {
                log "swapfile_status=create_failed_nonfatal"
                return 1
            }
        fi
    fi

    chmod 600 "$Swapfile_Path" 2>/dev/null || log "swapfile_chmod_status=failed_nonfatal"

    if mkswap "$Swapfile_Path" >/dev/null 2>&1; then
        log "mkswap_status=completed"
    else
        log "mkswap_status=failed_nonfatal"
        return 1
    fi

    if swapon -p "$Swapfile_Priority" "$Swapfile_Path" 2>/dev/null; then
        log "swapon_status=completed priority=$Swapfile_Priority"
    else
        log "swapon_status=failed_nonfatal"
        return 1
    fi

    ensure_fstab_swap
    log "swap_setup_status=completed priority=$Swapfile_Priority"
    return 0
}

log "script_started_at=$(date)"
log "Minimum_Free_MB_For_Swap=$Minimum_Free_MB_For_Swap"
log "Minimum_Root_Total_MB_For_Disk_Swap=$Minimum_Root_Total_MB_For_Disk_Swap"
log "Disk_Swap_Size_MB=$Disk_Swap_Size_MB"
log "Swapfile_Path=$Swapfile_Path"
log "Swapfile_Priority=$Swapfile_Priority"
log "Tune_Swappiness=$Tune_Swappiness"
log "Swappiness_Value=$Swappiness_Value"
log "Manage_ZRAM=$Manage_ZRAM"

if [ "$(id -u 2>/dev/null || echo 1)" != "0" ]; then
    warn "not running as root; reporting only and making no changes"
    READ_ONLY=1
else
    READ_ONLY=0
fi
log "read_only=$READ_ONLY"

log "memory_status_begin"
free -h 2>/dev/null || true
log "memory_status_end"

log "proc_swaps_begin"
cat /proc/swaps 2>/dev/null || true
log "proc_swaps_end"

if grep -q '/dev/zram' /proc/swaps 2>/dev/null; then
    log "zram_status=present"
    grep '/dev/zram' /proc/swaps 2>/dev/null || true
else
    log "zram_status=not_present"
fi

ROOT_FREE_MB=$(root_free_mb)
[ -n "$ROOT_FREE_MB" ] || ROOT_FREE_MB=0
ROOT_TOTAL_MB=$(root_total_mb)
[ -n "$ROOT_TOTAL_MB" ] || ROOT_TOTAL_MB=0
log "root_total_mb=$ROOT_TOTAL_MB"
log "root_free_mb=$ROOT_FREE_MB"

ACTIVE_SWAP_COUNT=$(active_swap_count)
ACTIVE_ZRAM_SWAP_COUNT=$(active_zram_swap_count)
ACTIVE_NON_ZRAM_SWAP_COUNT=$(active_non_zram_swap_count)
log "active_swap_count=$ACTIVE_SWAP_COUNT"
log "active_zram_swap_count=$ACTIVE_ZRAM_SWAP_COUNT"
log "active_non_zram_swap_count=$ACTIVE_NON_ZRAM_SWAP_COUNT"

# Hard guard: below the free-space threshold means this helper makes no changes at all.
# This includes ZRAM changes, disk swap changes, fstab changes, and swappiness changes.
if [ "$ROOT_FREE_MB" -lt "$Minimum_Free_MB_For_Swap" ]; then
    warn "root free space below threshold; no swap, ZRAM, fstab, or swappiness changes will be made"
    log "free_space_guard_status=below_threshold_no_changes"
    log "swap_setup_status=skipped_low_free_space"
    log "zram_config_status=skipped_low_free_space"
    log "swappiness_status=skipped_low_free_space"
    log "script_finished_at=$(date)"
    exit 0
fi
log "free_space_guard_status=passed"

if [ "$READ_ONLY" = "1" ]; then
    log "swap_setup_status=skipped_not_root"
    log "zram_config_status=skipped_not_root"
    log "swappiness_status=skipped_not_root"
    log "script_finished_at=$(date)"
    exit 0
fi

# Existing non-ZRAM swap means the system already has disk-backed swap or another
# non-ZRAM swap device. Do not create/repair disk swap and do not modify ZRAM.
# Swappiness tuning is allowed because it does not consume disk space or add swap devices.
if [ "$ACTIVE_NON_ZRAM_SWAP_COUNT" -gt 0 ]; then
    log "active_swap_status=non_zram_present"
    if swapfile_active; then
        log "swapfile_status=already_active path=$Swapfile_Path"
        repair_active_swapfile_priority || true
        ensure_fstab_swap
        log "swap_setup_status=already_active"
    else
        log "swapfile_status=skipped_non_zram_swap_already_present"
        log "swap_setup_status=skipped_non_zram_swap_already_present"
    fi
    log "zram_config_status=skipped_non_zram_swap_already_present"
    configure_swappiness
    log "script_finished_at=$(date)"
    exit 0
fi

if [ "$ACTIVE_ZRAM_SWAP_COUNT" -gt 0 ]; then
    log "active_swap_status=zram_only_present"
    log "zram_config_status=skipped_active_zram_present"
    create_swapfile || true
    configure_swappiness
else
    log "active_swap_status=none"
    # All guards passed and no active swap exists. Only now may the helper modify ZRAM.
    configure_zram_if_enabled
    create_swapfile || true
    configure_swappiness
fi

log "proc_swaps_after_begin"
cat /proc/swaps 2>/dev/null || true
log "proc_swaps_after_end"

log "disk_status_after_begin"
df -h / 2>/dev/null || true
log "disk_status_after_end"

log "script_finished_at=$(date)"
exit 0
