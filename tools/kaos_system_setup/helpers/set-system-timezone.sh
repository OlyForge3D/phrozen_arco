#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# set-system-timezone.sh
# KAOS helper: sets system timezone, accepting either a fixed UTC offset
# or a named IANA timezone.
#
# Called by run.sh as part of the Set_Timezone toggle, in one of two modes:
#   set-system-timezone.sh --utc-offset=N         (e.g. --utc-offset=-4)
#   set-system-timezone.sh --iana-zone=NAME       (e.g. --iana-zone=America/Chicago)
#
# --utc-offset mode uses the Etc/GMT* zoneinfo entries: a FIXED offset
# from UTC that never observes daylight saving time. Use this when you
# want a specific number and nothing else.
#
# --iana-zone mode uses a real IANA region name and hands it straight to
# timedatectl / zoneinfo. This IS DST-aware: the OS applies whatever DST
# rules that region observes, automatically, going forward. Use this when
# DST-correct behavior matters.
#
# If both flags are supplied, --iana-zone wins (more precise / DST-aware).
#
# NOTE on --utc-offset's sign: POSIX TZ convention is inverted from
# common usage -- Etc/GMT+N == UTC-N (west of Greenwich), Etc/GMT-N ==
# UTC+N (east). The sign flip in the offset branch below is intentional.

set -u

UTC_OFFSET=""
IANA_ZONE=""

for arg in "$@"; do
    case "$arg" in
        --utc-offset=*) UTC_OFFSET="${arg#*=}" ;;
        --iana-zone=*)  IANA_ZONE="${arg#*=}" ;;
        *) echo "set-system-timezone.sh: unknown_argument=$arg" >&2 ;;
    esac
done

if [ "$(id -u)" != "0" ]; then
    echo "set-system-timezone.sh: ERROR must run as root" >&2
    exit 1
fi

if [ -n "$IANA_ZONE" ]; then
    TARGET_ZONE="$IANA_ZONE"
    MODE="iana_zone"
else
    # Defensive re-validation -- this script should never trust its caller.
    case "$UTC_OFFSET" in
        -1[01]|-[1-9]|0|[1-9]|1[01]) : ;;
        *)
            echo "set-system-timezone.sh: ERROR invalid --utc-offset=$UTC_OFFSET (must be -11..11)" >&2
            exit 1
            ;;
    esac
    # Flip sign per POSIX Etc/GMT convention (see header note).
    ETC_VALUE=$((0 - UTC_OFFSET))
    if [ "$ETC_VALUE" -gt 0 ]; then
        TARGET_ZONE="Etc/GMT+${ETC_VALUE}"
    elif [ "$ETC_VALUE" -lt 0 ]; then
        TARGET_ZONE="Etc/GMT${ETC_VALUE}"
    else
        TARGET_ZONE="Etc/GMT"
    fi
    MODE="utc_offset"
fi

if [ ! -e "/usr/share/zoneinfo/${TARGET_ZONE}" ]; then
    echo "set-system-timezone.sh: ERROR zoneinfo not found: /usr/share/zoneinfo/${TARGET_ZONE} (mode=$MODE)" >&2
    exit 1
fi

CURRENT_ZONE=""
if [ -L /etc/localtime ]; then
    CURRENT_ZONE=$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')
fi

if [ "$CURRENT_ZONE" = "$TARGET_ZONE" ]; then
    echo "set-system-timezone.sh: already_set zone=$TARGET_ZONE mode=$MODE (no change)"
    exit 0
fi

# Prefer timedatectl when available (systemd systems); fall back to the
# manual /etc/localtime + /etc/timezone method otherwise.
if command -v timedatectl >/dev/null 2>&1; then
    if timedatectl set-timezone "$TARGET_ZONE" 2>/dev/null; then
        echo "set-system-timezone.sh: status=completed method=timedatectl zone=$TARGET_ZONE mode=$MODE"
        exit 0
    else
        echo "set-system-timezone.sh: timedatectl failed, falling back to manual method" >&2
    fi
fi

ln -sf "/usr/share/zoneinfo/${TARGET_ZONE}" /etc/localtime
echo "$TARGET_ZONE" > /etc/timezone

echo "set-system-timezone.sh: status=completed method=manual zone=$TARGET_ZONE mode=$MODE"
exit 0
