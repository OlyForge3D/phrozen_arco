#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# KAOS System Prep Helper — truncate-active-logs.sh
#
# Zeroes out known live log files that have ballooned in size.
# Does NOT delete files, does NOT restart services, does NOT touch
# the Moonraker database or any config.
#
# Uses `: > file` truncation which is safe for append-style logs —
# the file inode stays intact so any service with an open fd continues
# writing correctly without needing a restart.
#
# Default candidate logs (printer logs only):
#   /home/mks/printer_data/logs/klippy.log
#   /home/mks/printer_data/logs/moonraker.log
#   /home/mks/printer_data/logs/crowsnest.log
#   /home/mks/printer_data/logs/webcamd.log
#   /home/mks/printer_data/logs/kaos_installer_deploy.log
#
# System logs (added only when INCLUDE_SYSTEM_LOGS=1):
#   /var/log/syslog
#   /var/log/messages
#
# kaos_system_prep.log is written to by this helper and is left intact.
# It gets a marker entry after all other logs are truncated.
#
# Optional parameters (environment variable or positional arg):
#   LOG_MIN_MB=10          Only truncate logs at or above this size. Default: 0 (all).
#   INCLUDE_SYSTEM_LOGS=1  Also truncate /var/log/syslog and /var/log/messages.
#                          Requires root. Failures are non-fatal.
#
# Usage:
#   truncate-active-logs.sh
#   truncate-active-logs.sh LOG_MIN_MB=10
#   truncate-active-logs.sh LOG_MIN_MB=10 INCLUDE_SYSTEM_LOGS=1
#   KAOS_SYSTEM_PREP TRUNCATE_ACTIVE_LOGS=1
#   KAOS_SYSTEM_PREP TRUNCATE_ACTIVE_LOGS=1 LOG_MIN_MB=10
#   KAOS_SYSTEM_PREP TRUNCATE_ACTIVE_LOGS=1 LOG_MIN_MB=10 INCLUDE_SYSTEM_LOGS=1
#
# Not included in Light or Full presets — on-demand only.
# Safe to re-run; idempotent.

set -u

LOG_PREFIX="ARCO_SYSTEM_PREP:"
SYSTEM_PREP_LOG="/home/mks/printer_data/logs/kaos_system_prep.log"

log() {
    echo "${LOG_PREFIX} $*"
}

# ── Parse parameters ──────────────────────────────────────────────────────────
#
# Accept as environment variables or positional args (KEY=VALUE)

for arg in "$@"; do
    case "$arg" in
        LOG_MIN_MB=*)          LOG_MIN_MB="${arg#LOG_MIN_MB=}" ;;
        INCLUDE_SYSTEM_LOGS=*) INCLUDE_SYSTEM_LOGS="${arg#INCLUDE_SYSTEM_LOGS=}" ;;
    esac
done
LOG_MIN_MB="${LOG_MIN_MB:-0}"
INCLUDE_SYSTEM_LOGS="${INCLUDE_SYSTEM_LOGS:-0}"

# Validate LOG_MIN_MB is a non-negative integer
case "$LOG_MIN_MB" in
    ''|*[!0-9]*)
        log "truncate_active_logs_status=aborted_invalid_LOG_MIN_MB=$LOG_MIN_MB"
        exit 1
        ;;
esac

log "truncate_active_logs_log_min_mb=$LOG_MIN_MB"
log "truncate_active_logs_include_system_logs=$INCLUDE_SYSTEM_LOGS"

# ── Candidate log list ────────────────────────────────────────────────────────
#
# kaos_system_prep.log is intentionally excluded — it's the active log we're
# writing to. It gets a marker entry at the end instead.

CANDIDATES="
/home/mks/printer_data/logs/klippy.log
/home/mks/printer_data/logs/moonraker.log
/home/mks/printer_data/logs/crowsnest.log
/home/mks/printer_data/logs/webcamd.log
/home/mks/printer_data/logs/kaos_installer_deploy.log
"

if [ "$INCLUDE_SYSTEM_LOGS" = "1" ]; then
    CANDIDATES="$CANDIDATES
/var/log/syslog
/var/log/messages
"
fi

# ── Size inventory ────────────────────────────────────────────────────────────

log "truncate_active_logs_size_report_begin"
for f in $CANDIDATES; do
    if [ -f "$f" ]; then
        size_kb=$(du -k -- "$f" 2>/dev/null | cut -f1)
        size_kb="${size_kb:-0}"
        log "truncate_active_logs_size=$(printf '%6d' "$size_kb")KB  $f"
    else
        log "truncate_active_logs_size=not_present  $f"
    fi
done
log "truncate_active_logs_size_report_end"

# ── Truncation ────────────────────────────────────────────────────────────────

truncated=0
skipped_size=0
skipped_missing=0
failed=0

for f in $CANDIDATES; do
    fname=$(basename -- "$f")

    if [ ! -f "$f" ]; then
        log "truncate_active_logs_skipped_missing=$fname"
        skipped_missing=$((skipped_missing + 1))
        continue
    fi

    size_kb=$(du -k -- "$f" 2>/dev/null | cut -f1)
    size_kb="${size_kb:-0}"
    min_kb=$((LOG_MIN_MB * 1024))

    if [ "$LOG_MIN_MB" -gt 0 ] && [ "$size_kb" -lt "$min_kb" ]; then
        log "truncate_active_logs_skipped_below_threshold=$fname size=${size_kb}KB threshold=${min_kb}KB"
        skipped_size=$((skipped_size + 1))
        continue
    fi

    if : > "$f" 2>/dev/null; then
        log "truncate_active_logs_truncated=$fname was=${size_kb}KB"
        truncated=$((truncated + 1))
    else
        log "truncate_active_logs_failed=$fname"
        failed=$((failed + 1))
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────

log "truncate_active_logs_truncated_count=$truncated"
log "truncate_active_logs_skipped_below_threshold_count=$skipped_size"
log "truncate_active_logs_skipped_missing_count=$skipped_missing"
log "truncate_active_logs_failed_count=$failed"
log "truncate_active_logs_status=completed"

# ── Marker in kaos_system_prep.log ───────────────────────────────────────────
#
# Written after all other logs are done so the marker clearly delineates
# where truncation happened in the log history.

if [ -f "$SYSTEM_PREP_LOG" ]; then
    echo "${LOG_PREFIX} truncate_active_logs_marker truncated_at=$(date) truncated_count=$truncated" >> "$SYSTEM_PREP_LOG"
fi

exit 0
