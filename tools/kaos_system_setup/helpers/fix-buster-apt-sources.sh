#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# ARCO System Prep helper: replace broken Debian Buster sources with archived repos.
# Non-fatal by design: logs failures and exits 0 so the orchestrator can continue.

set -u

SRC="/etc/apt/sources.list"
APT_CONF="/etc/apt/apt.conf.d/99no-check-valid-until"
BACKUP="/etc/apt/sources.list.backup.$(date +%Y%m%d-%H%M%S)"

log() { echo "APT_SOURCE_FIX: $*"; }

add_line_if_missing() {
    line="$1"
    if grep -Fxq "$line" "$SRC" 2>/dev/null; then
        log "source_line_status=already_present line=$line"
    else
        printf '%s\n' "$line" >> "$SRC" 2>/dev/null && log "source_line_status=added line=$line" || log "source_line_status=add_failed_nonfatal line=$line"
    fi
}

log "script_started_at=$(date)"

if [ ! -f "$SRC" ]; then
    log "sources_list_status=missing path=$SRC"
    exit 0
fi

if cp "$SRC" "$BACKUP" 2>/dev/null; then
    log "backup_status=created path=$BACKUP"
else
    log "backup_status=failed_nonfatal path=$BACKUP"
fi

if sed -i -E 's/^([[:space:]]*)(deb|deb-src)([[:space:]]+)/#\1\2\3/' "$SRC" 2>/dev/null; then
    log "comment_existing_sources_status=completed"
else
    log "comment_existing_sources_status=failed_nonfatal"
fi

printf '\n# Debian Buster archive sources added by ARCO System Prep\n' >> "$SRC" 2>/dev/null || true
add_line_if_missing "deb http://archive.debian.org/debian buster main contrib non-free"
add_line_if_missing "deb http://archive.debian.org/debian buster-updates main contrib non-free"
add_line_if_missing "deb http://archive.debian.org/debian-security buster/updates main contrib non-free"

if mkdir -p /etc/apt/apt.conf.d 2>/dev/null && printf '%s\n' 'Acquire::Check-Valid-Until "false";' > "$APT_CONF" 2>/dev/null; then
    log "valid_until_status=disabled path=$APT_CONF"
else
    log "valid_until_status=failed_nonfatal path=$APT_CONF"
fi

if command -v apt-get >/dev/null 2>&1; then
    apt-get clean >/dev/null 2>&1 || log "apt_clean_status=failed_nonfatal"
    if apt-get update -o Acquire::Check-Valid-Until=false; then
        log "apt_update_status=completed"
    else
        log "apt_update_status=failed_nonfatal"
    fi
else
    log "apt_get_status=not_found"
fi

log "script_finished_at=$(date)"
exit 0
