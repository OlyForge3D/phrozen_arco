#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# KAOS System Prep Helper — clean-printer-logs.sh
#
# Removes rotated/old Klipper log files from the printer_data/logs directory.
# Leaves the currently-active log files (klippy.log, moonraker.log,
# crowsnest.log, etc.) untouched — those are plain *.log with no suffix.
#
# Rotated-file patterns targeted:
#   *.log.[0-9]*       logrotate numeric suffix      klippy.log.1, .2, …
#   *.log.[0-9]*.gz    compressed numeric suffix     klippy.log.2.gz, …
#   *.log-[0-9]*       date suffix (dash form)       klippy.log-20241201
#   *.log.old          generic .old rollover
#
# Named files explicitly removed (services recreate on next run if needed):
#   KlipperScreen.log       stock pre-KAOS log; KlipperScreen not used on Arco
#   moonraker-obico.log     Obico client log; not used on Arco
#
# Safe to re-run; idempotent.  Non-fatal: individual delete failures are
# logged but do not exit non-zero.

set -u

LOG_PREFIX="ARCO_SYSTEM_PREP:"
LOG_DIR="/home/mks/printer_data/logs"

log() {
    echo "${LOG_PREFIX} $*"
}

# ── Preflight ──────────────────────────────────────────────────────────────────

if [ ! -d "$LOG_DIR" ]; then
    log "clean_printer_logs_status=skipped_log_dir_not_found"
    log "clean_printer_logs_log_dir=$LOG_DIR"
    exit 0
fi

log "clean_printer_logs_log_dir=$LOG_DIR"

# ── Inventory before ──────────────────────────────────────────────────────────

before_count=$(find "$LOG_DIR" -maxdepth 1 -type f | wc -l)
before_size=$(du -sh -- "$LOG_DIR" 2>/dev/null | cut -f1)
log "clean_printer_logs_before_files=$before_count"
log "clean_printer_logs_before_size=$before_size"

# ── Deletion ──────────────────────────────────────────────────────────────────
#
# Collect candidates into a temp file to avoid the subshell-counter problem
# (piping into a while loop spawns a subshell; variable increments are lost).

tmp_list=$(mktemp)
trap 'rm -f -- "$tmp_list"' EXIT

# Pattern-based: rotated/compressed log files
find "$LOG_DIR" -maxdepth 1 -type f \( \
    -name "*.log.[0-9]*"    \
    -o -name "*.log-[0-9]*" \
    -o -name "*.log.old"    \
    \) | sort >> "$tmp_list"

# Named files: present on Arco stock builds; services not active under KAOS
# and will recreate the file if ever needed.
for named in \
    "KlipperScreen.log" \
    "moonraker-obico.log"
do
    named_path="$LOG_DIR/$named"
    if [ -f "$named_path" ]; then
        echo "$named_path" >> "$tmp_list"
    fi
done

deleted=0
failed=0

while IFS= read -r f; do
    fname=$(basename -- "$f")
    if rm -- "$f" 2>/dev/null; then
        log "clean_printer_logs_deleted=$fname"
        deleted=$((deleted + 1))
    else
        log "clean_printer_logs_delete_failed=$fname"
        failed=$((failed + 1))
    fi
done < "$tmp_list"

# ── Inventory after ───────────────────────────────────────────────────────────

after_count=$(find "$LOG_DIR" -maxdepth 1 -type f | wc -l)
after_size=$(du -sh -- "$LOG_DIR" 2>/dev/null | cut -f1)
log "clean_printer_logs_deleted_count=$deleted"
log "clean_printer_logs_failed_count=$failed"
log "clean_printer_logs_after_files=$after_count"
log "clean_printer_logs_after_size=$after_size"
log "clean_printer_logs_status=completed"

exit 0
