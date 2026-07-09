#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# ARCO System Prep helper: fully remove vnStat and its corrupt database.
# The Armbian MOTD already skips traffic output when vnstat is absent, so this
# helper deliberately does not modify executable login/MOTD scripts.
# It can also repair files damaged by older System Prep builds that commented
# individual vnstat lines inside shell blocks.

set -u

: "${Remove_VNStat_Package:=1}"
: "${Remove_VNStat_Database:=1}"
: "${Restore_Previous_VNStat_MOTD_Backups:=1}"

log() { echo "VNSTAT_REMOVE: $*"; }

unit_exists() {
    unit="$1"
    systemctl list-unit-files "$unit" 2>/dev/null | awk '{print $1}' | grep -Fxq "$unit"
}

restore_previously_modified_file() {
    file="$1"
    [ -f "$file" ] || return 0

    if ! grep -q "^# ARCO System Prep disabled vnStat login hook:" "$file" 2>/dev/null; then
        return 0
    fi

    backup=$(ls -1t "${file}.arco_vnstat_backup_"* 2>/dev/null | head -n 1 || true)
    if [ -z "$backup" ] || [ ! -f "$backup" ]; then
        log "motd_restore_status=backup_not_found file=$file"
        return 0
    fi

    ts=$(date +%Y%m%d_%H%M%S)
    current_backup="${file}.before_arco_vnstat_restore_${ts}"
    cp -a "$file" "$current_backup" 2>/dev/null || true

    if cp -a "$backup" "$file" 2>/dev/null; then
        log "motd_restore_status=restored file=$file backup=$backup"
    else
        log "motd_restore_status=failed_nonfatal file=$file backup=$backup"
    fi
}

log "script_started_at=$(date)"
log "Remove_VNStat_Package=$Remove_VNStat_Package"
log "Remove_VNStat_Database=$Remove_VNStat_Database"
log "Restore_Previous_VNStat_MOTD_Backups=$Restore_Previous_VNStat_MOTD_Backups"

if [ "$(id -u)" -ne 0 ]; then
    log "status=failed_requires_root"
    exit 1
fi

for unit in vnstat.service vnstatd.service; do
    if unit_exists "$unit"; then
        systemctl stop "$unit" >/dev/null 2>&1 || true
        systemctl disable "$unit" >/dev/null 2>&1 || true
        systemctl mask "$unit" >/dev/null 2>&1 || true
        log "unit_status=stopped_disabled_masked unit=$unit"
    else
        log "unit_status=not_installed unit=$unit"
    fi
done

if [ "$Restore_Previous_VNStat_MOTD_Backups" = "1" ]; then
    for file in \
        /etc/update-motd.d/* \
        /etc/profile \
        /etc/bash.bashrc \
        /etc/profile.d/*.sh \
        /root/.profile \
        /home/mks/.profile \
        /home/prz/.profile
    do
        [ -e "$file" ] || continue
        restore_previously_modified_file "$file"
    done
else
    log "motd_restore_status=skipped_disabled_by_setting"
fi

if [ "$Remove_VNStat_Database" = "1" ]; then
    if [ -d /var/lib/vnstat ]; then
        rm -rf /var/lib/vnstat
        log "database_status=removed path=/var/lib/vnstat"
    else
        log "database_status=not_present"
    fi
else
    log "database_status=skipped_disabled_by_setting"
fi

if [ "$Remove_VNStat_Package" = "1" ]; then
    if dpkg-query -W -f='${Status}' vnstat 2>/dev/null | grep -q 'install ok installed'; then
        if DEBIAN_FRONTEND=noninteractive apt-get purge -y vnstat >/dev/null 2>&1; then
            log "package_status=purged package=vnstat"
        else
            log "package_status=purge_failed_nonfatal package=vnstat"
        fi
    else
        log "package_status=not_installed package=vnstat"
    fi
else
    log "package_status=skipped_disabled_by_setting"
fi

systemctl daemon-reload >/dev/null 2>&1 || true
systemctl reset-failed vnstat.service vnstatd.service >/dev/null 2>&1 || true

log "status=completed"
log "script_finished_at=$(date)"
exit 0
