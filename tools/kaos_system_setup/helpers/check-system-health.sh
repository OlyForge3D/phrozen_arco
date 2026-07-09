#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# ARCO System Prep helper: read-only preflight/system health snapshot.

set -u
log() { echo "ARCO_SYSTEM_HEALTH: $*"; }

section() { log "$1_begin"; }
endsection() { log "$1_end"; }

log "script_started_at=$(date)"
log "readonly=1"
log "hostname=$(hostname 2>/dev/null || echo unknown)"
log "user=$(whoami 2>/dev/null || echo unknown)"
log "kernel=$(uname -a 2>/dev/null || echo unknown)"

section disk
(df -h / /home /var/log 2>/dev/null || df -h 2>/dev/null || true) | sed 's/^/ARCO_SYSTEM_HEALTH: /'
endsection disk

section memory
(free -h 2>/dev/null || cat /proc/meminfo 2>/dev/null || true) | sed 's/^/ARCO_SYSTEM_HEALTH: /'
endsection memory

section swap
(cat /proc/swaps 2>/dev/null || true) | sed 's/^/ARCO_SYSTEM_HEALTH: /'
(swapon --show 2>/dev/null || true) | sed 's/^/ARCO_SYSTEM_HEALTH: /'
endsection swap

section zram
(ls -l /dev/zram* 2>/dev/null || true) | sed 's/^/ARCO_SYSTEM_HEALTH: /'
(zramctl 2>/dev/null || true) | sed 's/^/ARCO_SYSTEM_HEALTH: /'
endsection zram


section timezone
if command -v timedatectl >/dev/null 2>&1; then
    timedatectl 2>/dev/null | sed 's/^/ARCO_SYSTEM_HEALTH: /'
else
    log "timedatectl=not_found"
fi

if [ -e /etc/localtime ]; then
    log "localtime_target=$(readlink -f /etc/localtime 2>/dev/null || echo unknown)"
else
    log "localtime_target=missing"
fi

if [ -f /etc/timezone ]; then
    log "etc_timezone=$(cat /etc/timezone 2>/dev/null || echo unreadable)"
else
    log "etc_timezone=missing"
fi

if command -v systemctl >/dev/null 2>&1; then
    for svc in ntp chrony systemd-timesyncd; do
        enabled=$(systemctl is-enabled "$svc" 2>/dev/null || echo unknown)
        active=$(systemctl is-active "$svc" 2>/dev/null || echo inactive_or_unknown)
        log "time_service=$svc enabled=$enabled active=$active"
    done
else
    log "systemctl=not_found_for_time_services"
fi
endsection timezone

section journal_persistence
if command -v journalctl >/dev/null 2>&1; then
    journalctl --disk-usage 2>/dev/null | sed 's/^/ARCO_SYSTEM_HEALTH: /'
    journalctl --list-boots 2>/dev/null | tail -n 10 | sed 's/^/ARCO_SYSTEM_HEALTH: journal_boot /'
else
    log "journalctl=not_found"
fi

if [ -d /var/log/journal ]; then
    log "persistent_journal_dir=present path=/var/log/journal"
else
    log "persistent_journal_dir=missing path=/var/log/journal"
fi

for f in /etc/systemd/journald.conf /etc/systemd/journald.conf.d/*.conf; do
    [ -f "$f" ] || continue
    grep -E '^[[:space:]]*Storage=' "$f" 2>/dev/null | sed "s|^|ARCO_SYSTEM_HEALTH: journald_config=$f |"
done
endsection journal_persistence

section logs
for p in /var/log /home/mks/printer_data/logs /home/prz/printer_data/logs; do
    [ -e "$p" ] && du -sh "$p" 2>/dev/null | sed 's/^/ARCO_SYSTEM_HEALTH: du /'
done
endsection logs

section services
if command -v systemctl >/dev/null 2>&1; then
    systemctl --failed --no-pager 2>/dev/null | sed 's/^/ARCO_SYSTEM_HEALTH: /'
    for svc in klipper moonraker nginx crowsnest KlipperScreen octoeverywhere obico rsyslog systemd-journald; do
        systemctl is-enabled "$svc" >/dev/null 2>&1 && enabled=$(systemctl is-enabled "$svc" 2>/dev/null) || enabled=unknown
        systemctl is-active "$svc" >/dev/null 2>&1 && active=$(systemctl is-active "$svc" 2>/dev/null) || active=inactive_or_unknown
        log "service=$svc enabled=$enabled active=$active"
    done
else
    log "systemctl=not_found"
fi
endsection services

section kiauh
for home in /home/mks /home/prz; do
    if [ -d "$home/kiauh/.git" ]; then
        log "kiauh_path=$home/kiauh"
        (cd "$home/kiauh" && echo "branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)" && echo "describe=$(git describe --tags --always 2>/dev/null || echo unknown)" && git remote -v 2>/dev/null) | sed 's/^/ARCO_SYSTEM_HEALTH: /'
    fi
done
endsection kiauh

section repo_locks
for repo in /home/mks/klipper /home/mks/KlipperScreen /home/prz/klipper /home/prz/KlipperScreen; do
    if [ -d "$repo/.git" ]; then
        origin=$(git -C "$repo" remote get-url origin 2>/dev/null || echo unknown)
        log "repo=$repo origin=$origin"
    fi
done
endsection repo_locks

section webui_pins
for ui in /home/mks/fluidd /home/mks/mainsail /home/prz/fluidd /home/prz/mainsail; do
    if [ -d "$ui" ]; then
        if [ -f "$ui/.kaos_pinned_version" ]; then
            log "webui=$ui pinned_version=$(cat "$ui/.kaos_pinned_version" 2>/dev/null)"
        else
            log "webui=$ui pinned_version=UNKNOWN"
        fi
    fi
done
endsection webui_pins


section kaos_system_prep_log
KAOS_LOG="/home/mks/printer_data/logs/kaos_system_prep.log"
if [ -f "$KAOS_LOG" ]; then
    log "kaos_system_prep_log=present path=$KAOS_LOG"
    tail -n 25 "$KAOS_LOG" 2>/dev/null | sed 's/^/ARCO_SYSTEM_HEALTH: kaos_system_prep_log_tail /'
else
    log "kaos_system_prep_log=missing path=$KAOS_LOG"
fi
endsection kaos_system_prep_log

log "script_finished_at=$(date)"
exit 0
