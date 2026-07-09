#!/bin/sh
# KAOS System Setup — curated one-time system-prep helpers, integrated into the
# KAOS install/update flow.
#
# This is a curated, pin-safe subset of the upstream KAOS System Prep toolkit.
# It intentionally EXCLUDES:
#   * the runtime KAOS_SYSTEM_PREP macro / gcode_shell_command runner, and
#   * the version updaters (Moonraker / web UI / Crowsnest / system files),
#     which would fight this fork's pinned-commit update strategy, and
#   * disable-soft-shutdown (already handled by install/phrozen_install.sh).
#
# Design:
#   * Single entry point invoked by install/phrozen_install.sh (gated).
#   * Vendored, tested helper scripts live in ./kaos_system_setup/helpers/.
#   * Safe, idempotent FIXES and stability improvements run by default. Only
#     preference/destructive/needs-input helpers and all maintenance actions
#     are opt-in via KAOS_SETUP_* environment variables.
#   * Every helper is non-fatal: a failure logs a warning and continues.
#
# Usage:
#   sh tools/kaos_system_setup.sh                 # default: safe fixes only
#   KAOS_SETUP_CONFIGURE_SWAP_ZRAM=1 sh tools/kaos_system_setup.sh
#   KAOS_SETUP_ALL_SAFE=1 sh tools/kaos_system_setup.sh   # all non-updating helpers
#   KAOS_SETUP_SET_TIMEZONE=1 KAOS_SETUP_TIMEZONE=America/Chicago sh tools/kaos_system_setup.sh
#   sh tools/kaos_system_setup.sh --list          # list helpers and their gates
#   sh tools/kaos_system_setup.sh --dry-run       # show what would run, change nothing
#
# POSIX sh compatible. Safe to run multiple times (helpers are idempotent).

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)
HELPERS_DIR="$SCRIPT_DIR/kaos_system_setup/helpers"

# --- Home / log directory detection (mks or prz based systems) ---------------
if [ -d /home/mks ]; then
    HOME_DIR="/home/mks"
elif [ -d /home/prz ]; then
    HOME_DIR="/home/prz"
else
    HOME_DIR="$HOME"
fi
LOG_DIR="$HOME_DIR/printer_data/logs"
SETUP_LOG="$LOG_DIR/kaos_system_setup.log"

DRY_RUN=0

# --- Gates -------------------------------------------------------------------
# Safe, idempotent FIXES: ON by default.
: "${KAOS_SETUP_FIX_APT_SOURCES:=1}"      # repair archived Debian Buster apt repos
: "${KAOS_SETUP_FIX_STOCK_NETWORK:=1}"    # disable known-failing stock network units
: "${KAOS_SETUP_FIX_USB_MOUNTPOINT:=1}"   # repair hidden USB gcodes mountpoint ownership

# Stability improvements: ON by default (reduce OOM / disk-full / eMMC wear).
: "${KAOS_SETUP_CONFIGURE_SWAP_ZRAM:=1}"  # configure swap / zram (prevents OOM on low-RAM boards)
: "${KAOS_SETUP_OPTIMIZE_LOGGING:=1}"     # shrink journald/logging (prevents disk-full / eMMC wear)
: "${KAOS_SETUP_TRIM_SERVICES:=1}"        # disable/mask non-essential background services

# Preference / destructive / needs-input CHANGES: opt-in (OFF by default).
: "${KAOS_SETUP_REMOVE_VNSTAT:=0}"        # remove vnstat service/package (destructive)
: "${KAOS_SETUP_PIN_KIAUH:=0}"            # pin KIAUH to v5.1.10 (fits pin strategy)
: "${KAOS_SETUP_SET_TIMEZONE:=0}"         # set timezone (needs KAOS_SETUP_TIMEZONE)
: "${KAOS_SETUP_TIMEZONE:=}"              # numeric UTC offset (-11..11) OR IANA zone name

# On-demand MAINTENANCE: opt-in (OFF by default).
: "${KAOS_SETUP_CHECK_HEALTH:=0}"         # read-only system health report
: "${KAOS_SETUP_CLEAN_LOGS:=0}"           # remove rotated/compressed printer logs
: "${KAOS_SETUP_TRUNCATE_LOGS:=0}"        # truncate active logs in place
: "${KAOS_SETUP_TRUNCATE_LOGS_MIN_MB:=0}" # only truncate logs >= this size (MB)
: "${KAOS_SETUP_TRUNCATE_INCLUDE_SYSTEM:=0}" # also truncate system logs
: "${KAOS_SETUP_RECLAIM_DISK:=0}"         # conservative disk-space cleanup

# KAOS_SETUP_ALL_SAFE=1 enables every non-updating helper (fixes + changes +
# maintenance). It never enables the excluded pin-breaking updaters.
: "${KAOS_SETUP_ALL_SAFE:=0}"
if [ "$KAOS_SETUP_ALL_SAFE" = "1" ]; then
    KAOS_SETUP_FIX_APT_SOURCES=1
    KAOS_SETUP_FIX_STOCK_NETWORK=1
    KAOS_SETUP_FIX_USB_MOUNTPOINT=1
    KAOS_SETUP_OPTIMIZE_LOGGING=1
    KAOS_SETUP_TRIM_SERVICES=1
    KAOS_SETUP_REMOVE_VNSTAT=1
    KAOS_SETUP_CONFIGURE_SWAP_ZRAM=1
    KAOS_SETUP_PIN_KIAUH=1
    KAOS_SETUP_CHECK_HEALTH=1
fi

# --- Logging -----------------------------------------------------------------
log()  { echo "KAOS_SETUP: $*"; }
warn() { echo "KAOS_SETUP [WARN]: $*" >&2; SETUP_WARNING_COUNT=$((SETUP_WARNING_COUNT + 1)); }
SETUP_WARNING_COUNT=0

usage() {
    cat <<'EOF'
KAOS System Setup — curated, pin-safe system-prep helpers.

Options:
  --list       List helpers and whether they are enabled, then exit.
  --dry-run    Log what would run without executing any helper.
  -h, --help   Show this help.

Gates (environment variables; 1 = enable, 0 = skip):
  Safe fixes (default ON):
    KAOS_SETUP_FIX_APT_SOURCES, KAOS_SETUP_FIX_STOCK_NETWORK,
    KAOS_SETUP_FIX_USB_MOUNTPOINT
  Stability improvements (default ON):
    KAOS_SETUP_CONFIGURE_SWAP_ZRAM, KAOS_SETUP_OPTIMIZE_LOGGING,
    KAOS_SETUP_TRIM_SERVICES
  Changes (default OFF):
    KAOS_SETUP_REMOVE_VNSTAT, KAOS_SETUP_PIN_KIAUH,
    KAOS_SETUP_SET_TIMEZONE (+ KAOS_SETUP_TIMEZONE)
  Maintenance (default OFF):
    KAOS_SETUP_CHECK_HEALTH, KAOS_SETUP_CLEAN_LOGS,
    KAOS_SETUP_TRUNCATE_LOGS (+ _MIN_MB, _INCLUDE_SYSTEM), KAOS_SETUP_RECLAIM_DISK
  Bulk:
    KAOS_SETUP_ALL_SAFE=1  enable all of the above (never the version updaters)
EOF
}

# --- Helper runner (non-fatal, mirrors upstream run.sh semantics) ------------
# run_helper <file> <label> <enabled> [args...]
run_helper() {
    helper_file="$1"; label="$2"; enabled="$3"; shift 3
    helper_path="$HELPERS_DIR/$helper_file"

    if [ "$enabled" != "1" ]; then
        DISABLED_LABELS="$DISABLED_LABELS $label"
        return 0
    fi

    if [ ! -f "$helper_path" ]; then
        warn "helper_missing label=$label helper=$helper_file path=$helper_path"
        return 0
    fi

    if [ "$DRY_RUN" = "1" ]; then
        log "would_run label=$label helper=$helper_file args=$*"
        return 0
    fi

    chmod 755 "$helper_path" 2>/dev/null || true
    log "section_begin label=$label helper=$helper_file"
    if sh "$helper_path" "$@" >> "$SETUP_LOG" 2>&1; then
        log "section_end label=$label status=completed"
    else
        warn "section_end label=$label status=failed_nonfatal (see $SETUP_LOG)"
    fi
    return 0
}

list_helpers() {
    printf '%-26s %-8s %s\n' "LABEL" "ENABLED" "HELPER"
    printf '%-26s %-8s %s\n' "apt_sources_fix"     "$KAOS_SETUP_FIX_APT_SOURCES"     "fix-buster-apt-sources.sh"
    printf '%-26s %-8s %s\n' "stock_network_fix"   "$KAOS_SETUP_FIX_STOCK_NETWORK"   "fix-stock-network-services.sh"
    printf '%-26s %-8s %s\n' "usb_mountpoint_fix"  "$KAOS_SETUP_FIX_USB_MOUNTPOINT"  "fix-usb-mountpoint.sh"
    printf '%-26s %-8s %s\n' "optimize_logging"    "$KAOS_SETUP_OPTIMIZE_LOGGING"    "optimize-system-logging.sh"
    printf '%-26s %-8s %s\n' "trim_services"       "$KAOS_SETUP_TRIM_SERVICES"       "trim-background-services.sh"
    printf '%-26s %-8s %s\n' "remove_vnstat"       "$KAOS_SETUP_REMOVE_VNSTAT"       "remove-vnstat.sh"
    printf '%-26s %-8s %s\n' "configure_swap_zram" "$KAOS_SETUP_CONFIGURE_SWAP_ZRAM" "configure-swap-zram.sh"
    printf '%-26s %-8s %s\n' "pin_kiauh"           "$KAOS_SETUP_PIN_KIAUH"           "pin-kiauh-v5.1.10.sh"
    printf '%-26s %-8s %s\n' "set_timezone"        "$KAOS_SETUP_SET_TIMEZONE"        "set-system-timezone.sh"
    printf '%-26s %-8s %s\n' "check_health"        "$KAOS_SETUP_CHECK_HEALTH"        "check-system-health.sh"
    printf '%-26s %-8s %s\n' "clean_logs"          "$KAOS_SETUP_CLEAN_LOGS"          "clean-printer-logs.sh"
    printf '%-26s %-8s %s\n' "truncate_logs"       "$KAOS_SETUP_TRUNCATE_LOGS"       "truncate-active-logs.sh"
    printf '%-26s %-8s %s\n' "reclaim_disk"        "$KAOS_SETUP_RECLAIM_DISK"        "kaos_reclaim_disk_space.sh"
}

# --- Argument parsing --------------------------------------------------------
case "${1:-}" in
    --list)      list_helpers; exit 0 ;;
    --dry-run)   DRY_RUN=1 ;;
    -h|--help)   usage; exit 0 ;;
    "")          ;;
    *)           echo "Unknown option: $1" >&2; usage; exit 2 ;;
esac

# --- Root check --------------------------------------------------------------
# Helpers modify system files/services and require root. Do not silently
# re-exec with a password here; the installer already runs as root.
if [ "$(id -u 2>/dev/null || echo 0)" != "0" ] && [ "$DRY_RUN" = "0" ]; then
    warn "not running as root; system helpers need root. Re-run with: sudo sh $0"
    exit 1
fi

mkdir -p "$LOG_DIR" 2>/dev/null || true
: > "$SETUP_LOG" 2>/dev/null || true

DISABLED_LABELS=""

log "started_at=$(date) home_dir=$HOME_DIR helpers_dir=$HELPERS_DIR dry_run=$DRY_RUN log=$SETUP_LOG"

# --- Build timezone args -----------------------------------------------------
# Numeric (-11..11) -> fixed UTC offset; anything else -> IANA zone name.
tz_args=""
if [ "$KAOS_SETUP_SET_TIMEZONE" = "1" ]; then
    if [ -z "$KAOS_SETUP_TIMEZONE" ]; then
        warn "set_timezone enabled but KAOS_SETUP_TIMEZONE is empty; skipping timezone"
        KAOS_SETUP_SET_TIMEZONE=0
    elif printf '%s' "$KAOS_SETUP_TIMEZONE" | grep -Eq '^-?[0-9]+$'; then
        tz_args="--utc-offset=$KAOS_SETUP_TIMEZONE"
    else
        tz_args="--iana-zone=$KAOS_SETUP_TIMEZONE"
    fi
fi

# --- Run helpers (safe fixes first, then changes, then maintenance) ----------
run_helper "fix-buster-apt-sources.sh"    "apt_sources_fix"     "$KAOS_SETUP_FIX_APT_SOURCES"
run_helper "fix-stock-network-services.sh" "stock_network_fix"  "$KAOS_SETUP_FIX_STOCK_NETWORK"
run_helper "fix-usb-mountpoint.sh"        "usb_mountpoint_fix"  "$KAOS_SETUP_FIX_USB_MOUNTPOINT"

run_helper "optimize-system-logging.sh"   "optimize_logging"    "$KAOS_SETUP_OPTIMIZE_LOGGING"
run_helper "trim-background-services.sh"  "trim_services"       "$KAOS_SETUP_TRIM_SERVICES"
run_helper "remove-vnstat.sh"             "remove_vnstat"       "$KAOS_SETUP_REMOVE_VNSTAT"
run_helper "configure-swap-zram.sh"       "configure_swap_zram" "$KAOS_SETUP_CONFIGURE_SWAP_ZRAM"
run_helper "pin-kiauh-v5.1.10.sh"         "pin_kiauh"           "$KAOS_SETUP_PIN_KIAUH"
# shellcheck disable=SC2086
run_helper "set-system-timezone.sh"       "set_timezone"        "$KAOS_SETUP_SET_TIMEZONE" $tz_args

run_helper "check-system-health.sh"       "check_health"        "$KAOS_SETUP_CHECK_HEALTH"
run_helper "clean-printer-logs.sh"        "clean_logs"          "$KAOS_SETUP_CLEAN_LOGS"
run_helper "truncate-active-logs.sh"      "truncate_logs"       "$KAOS_SETUP_TRUNCATE_LOGS" \
    "LOG_MIN_MB=$KAOS_SETUP_TRUNCATE_LOGS_MIN_MB" "INCLUDE_SYSTEM_LOGS=$KAOS_SETUP_TRUNCATE_INCLUDE_SYSTEM"
run_helper "kaos_reclaim_disk_space.sh"   "reclaim_disk"        "$KAOS_SETUP_RECLAIM_DISK" --yes

# --- Summary -----------------------------------------------------------------
[ -n "$DISABLED_LABELS" ] && log "disabled_by_setting:$DISABLED_LABELS"
log "finished_at=$(date) warnings=$SETUP_WARNING_COUNT log=$SETUP_LOG"

# Non-fatal overall: never abort the installer because of an optional helper.
exit 0
