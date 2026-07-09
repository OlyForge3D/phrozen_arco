#!/usr/bin/env bash
# KAOS_VERSION: v1.0 2026-06-09

# KAOS / Arco conservative disk-space cleanup helper
# Purpose: reclaim meaningful space without touching Phrozen vendor runtime paths or user config.
# Usage:
#   sudo bash kaos_reclaim_disk_space.sh --dry-run
#   sudo bash kaos_reclaim_disk_space.sh
#
# Optional flags:
#   --yes       Run without interactive confirmation
#   --dry-run   Show what would be removed, remove nothing

set -u

DRY_RUN=0
ASSUME_YES=0
LOG_FILE="/home/mks/kaos_disk_cleanup.log"

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --help|-h)
      sed -n '1,18p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Use --help for usage."
      exit 2
      ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo bash $0"
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || LOG_FILE="/tmp/kaos_disk_cleanup.log"
touch "$LOG_FILE" 2>/dev/null || LOG_FILE="/tmp/kaos_disk_cleanup.log"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

run_cmd() {
  if [ "$DRY_RUN" -eq 1 ]; then
    log "DRY-RUN: $*"
  else
    log "RUN: $*"
    sh -c "$*" 2>&1 | tee -a "$LOG_FILE"
  fi
}

size_of() {
  du -sh "$@" 2>/dev/null | sort -h || true
}

log "============================================================"
log "KAOS disk cleanup starting. Dry run: $DRY_RUN"
log "Log file: $LOG_FILE"
log "Disk before:"
df -h / | tee -a "$LOG_FILE"

log "Largest top-level paths before cleanup:"
du -xh / 2>/dev/null | sort -h | tail -40 | tee -a "$LOG_FILE"

cat <<'MSG'

This conservative cleanup targets:
  - APT package caches and unused packages
  - journal/log retention cleanup
  - rotated/compressed logs
  - Python __pycache__ folders under common Arco/Klipper locations
  - Klipper build output at /home/mks/klipper/out
  - old printer_data log archives and backups

It does NOT delete:
  - /home/mks/printer_data/config
  - /root/phrozen or /root/phrozen/build
  - source folders such as /home/mks/klipper, /home/mks/moonraker, /home/mks/crowsnest
  - active .log files, except optional journal vacuuming handled by journalctl

MSG

if [ "$DRY_RUN" -eq 0 ] && [ "$ASSUME_YES" -ne 1 ]; then
  printf "Continue with cleanup? Type YES to continue: "
  read -r answer
  if [ "$answer" != "YES" ]; then
    log "Cancelled by user."
    exit 0
  fi
fi

log "Checking candidate sizes before cleanup..."
size_of \
  /var/cache/apt \
  /var/log \
  /home/mks/klipper/out \
  /home/mks/printer_data/backup \
  /home/mks/printer_data/logs \
  /home/mks/.cache \
  /root/.cache \
  2>/dev/null | tee -a "$LOG_FILE" || true

# 1) APT cache cleanup and unused package cleanup.
if command -v apt-get >/dev/null 2>&1; then
  run_cmd "apt-get clean"
  run_cmd "apt-get autoclean -y"
  run_cmd "apt-get autoremove --purge -y"
else
  log "apt-get not found; skipping APT cleanup."
fi

# 2) Journal cleanup. Safe even if journald is volatile; no-op where unsupported.
if command -v journalctl >/dev/null 2>&1; then
  run_cmd "journalctl --vacuum-size=20M"
else
  log "journalctl not found; skipping journal vacuum."
fi

# 3) Remove rotated/compressed logs, but avoid deleting active .log files.
run_cmd "find /var/log -type f \\( -name '*.gz' -o -name '*.1' -o -name '*.old' -o -name '*.xz' \\) -print -delete"
run_cmd "find /home/mks/printer_data/logs -type f \\( -name '*.gz' -o -name '*.1' -o -name '*.old' -o -name '*.xz' \\) -print -delete 2>/dev/null || true"

# 4) Clear printer_data backups only if the directory exists.
# These are normally generated config backups, not active config.
run_cmd "find /home/mks/printer_data/backup -mindepth 1 -maxdepth 1 -print -exec rm -rf {} + 2>/dev/null || true"

# 5) Remove Klipper firmware build output. Recreated automatically by future builds.
run_cmd "rm -rf /home/mks/klipper/out"

# 6) Remove Python bytecode/cache folders in common printer software paths only.
# Avoid filesystem-wide __pycache__ deletion to reduce risk and runtime.
for base in \
  /home/mks/klipper \
  /home/mks/moonraker \
  /home/mks/crowsnest \
  /home/mks/KlipperScreen \
  /home/mks/printer_data/config \
  /home/mks/printer_data/moonraker \
  /home/mks/moonraker-timelapse; do
  if [ -d "$base" ]; then
    run_cmd "find '$base' -type d -name '__pycache__' -prune -print -exec rm -rf {} +"
    run_cmd "find '$base' -type d -name '.pytest_cache' -prune -print -exec rm -rf {} +"
  fi
done

# 7) User/root caches. Keep this conservative: cache only, not hidden app config.
run_cmd "find /home/mks/.cache -mindepth 1 -maxdepth 1 -print -exec rm -rf {} + 2>/dev/null || true"
run_cmd "find /root/.cache -mindepth 1 -maxdepth 1 -print -exec rm -rf {} + 2>/dev/null || true"

log "Disk after:"
df -h / | tee -a "$LOG_FILE"

log "Largest top-level paths after cleanup:"
du -xh / 2>/dev/null | sort -h | tail -40 | tee -a "$LOG_FILE"

log "KAOS disk cleanup finished."
