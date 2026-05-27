#!/bin/sh
# KAOS Migration Script — one-time migration from Phrozen forks to mainline.
#
# This script migrates a Phrozen Arco printer from the OlyForge3D Klipper/Moonraker
# forks to mainline repositories, and sets up KAOS as a Moonraker-managed add-on.
#
# One-liner (run on the printer via SSH):
#   wget -qO- https://raw.githubusercontent.com/OlyForge3D/phrozen_arco/dev/migrate_to_kaos.sh | sh
#
# What it does:
#   1. Switches ~/klipper origin to mainline Klipper3d/klipper
#   2. Switches ~/moonraker origin to mainline Arksine/moonraker
#   3. Sparse-clones KAOS (OlyForge3D/phrozen_arco) to ~/kaos
#   4. Adds [update_manager kaos] to moonraker.conf
#   5. Runs phrozen_install.sh to deploy phrozen_dev + configs
#   6. Reboots the printer
#
# Safe to run multiple times (idempotent).
# POSIX sh compatible.

set -eu

# --- Configuration -----------------------------------------------------------

KLIPPER_DIR="$HOME/klipper"
MOONRAKER_DIR="$HOME/moonraker"
KAOS_DIR="$HOME/kaos"
MOONRAKER_CONF="$HOME/printer_data/config/moonraker.conf"

MAINLINE_KLIPPER="https://github.com/Klipper3d/klipper.git"
MAINLINE_MOONRAKER="https://github.com/Arksine/moonraker.git"
KAOS_REPO="https://github.com/OlyForge3D/phrozen_arco.git"
KAOS_BRANCH="dev"

# Pinned commits — initial versions to check out during migration.
# Ongoing pin enforcement is handled by phrozen_install.sh via moonraker.conf.
KLIPPER_PIN="0aacbc39736c933491690bf8174a0658acf4482f"   # v0.12.0+168 (has minimum_cruise_ratio)
MOONRAKER_PIN="71517b255dc43c7e99fbc269d34deba9b30dd9f6"  # v0.8.0-306

# Known fork URLs to migrate away from (matched as substrings)
FORK_KLIPPER_PATTERNS="OlyForge3D/phrozen_klipper|jpapiez/phrozen"
FORK_MOONRAKER_PATTERNS="OlyForge3D/phrozen_moonraker|jpapiez/phrozen"

# --- Helpers -----------------------------------------------------------------

info()  { echo "KAOS_MIGRATE: $*"; }
warn()  { echo "KAOS_MIGRATE [WARN]: $*" >&2; }
fatal() { echo "KAOS_MIGRATE [ERROR]: $*" >&2; exit 1; }

check_git() {
    command -v git >/dev/null 2>&1 || fatal "git not found. Cannot proceed."
}

# Returns 0 if the origin URL of a git repo matches any of the fork patterns.
is_fork_remote() {
    repo_dir="$1"
    patterns="$2"
    current_url=$(git -C "$repo_dir" remote get-url origin 2>/dev/null) || return 1
    echo "$current_url" | grep -qiE "$patterns"
}

# Switch a repo's origin to the new URL and pin to a specific commit.
switch_remote() {
    repo_dir="$1"
    new_url="$2"
    branch="$3"
    pin_sha="$4"  # pinned commit SHA

    current_url=$(git -C "$repo_dir" remote get-url origin 2>/dev/null) || true
    if [ "$current_url" = "$new_url" ]; then
        info "  Already pointing to $new_url"
    else
        info "  Switching origin: $current_url -> $new_url"
        git -C "$repo_dir" remote set-url origin "$new_url"
    fi

    info "  Fetching from new origin..."
    git -C "$repo_dir" fetch origin --prune 2>/dev/null || warn "Fetch failed — check network"

    # Checkout the pinned commit (detached HEAD is fine — update_manager handles the rest).
    if git -C "$repo_dir" cat-file -e "$pin_sha" 2>/dev/null; then
        git -C "$repo_dir" checkout "$branch" 2>/dev/null || git -C "$repo_dir" checkout -b "$branch" "origin/$branch" 2>/dev/null || true
        git -C "$repo_dir" reset --hard "$pin_sha" 2>/dev/null || true
        info "  Pinned to $pin_sha"
    else
        warn "  Pinned commit $pin_sha not found. Falling back to origin/$branch HEAD."
        git -C "$repo_dir" checkout "$branch" 2>/dev/null || git -C "$repo_dir" checkout -b "$branch" "origin/$branch" 2>/dev/null || true
        git -C "$repo_dir" reset --hard "origin/$branch" 2>/dev/null || true
    fi
}

# --- Preflight ---------------------------------------------------------------

info "=== KAOS Migration ==="
info "Migrating to mainline Klipper + Moonraker with KAOS add-on"
echo ""

check_git

# Verify expected directories exist
[ -d "$KLIPPER_DIR/.git" ]   || fatal "$KLIPPER_DIR is not a git repo. Is this a Phrozen Arco?"
[ -d "$MOONRAKER_DIR/.git" ] || fatal "$MOONRAKER_DIR is not a git repo. Is this a Phrozen Arco?"

# --- Step 1: Migrate Klipper to mainline -------------------------------------

info "[1/5] Klipper remote"
if is_fork_remote "$KLIPPER_DIR" "$FORK_KLIPPER_PATTERNS"; then
    switch_remote "$KLIPPER_DIR" "$MAINLINE_KLIPPER" "master" "$KLIPPER_PIN"
else
    current=$(git -C "$KLIPPER_DIR" remote get-url origin 2>/dev/null)
    info "  Origin is already: $current (not a known fork — skipping)"
fi
echo ""

# --- Step 2: Migrate Moonraker to mainline -----------------------------------

info "[2/5] Moonraker remote"
if is_fork_remote "$MOONRAKER_DIR" "$FORK_MOONRAKER_PATTERNS"; then
    switch_remote "$MOONRAKER_DIR" "$MAINLINE_MOONRAKER" "master" "$MOONRAKER_PIN"
else
    current=$(git -C "$MOONRAKER_DIR" remote get-url origin 2>/dev/null)
    info "  Origin is already: $current (not a known fork — skipping)"
fi
echo ""

# --- Step 3: Clone KAOS (sparse) ---------------------------------------------

info "[3/5] KAOS repository"
if [ -d "$KAOS_DIR/.git" ]; then
    # Already cloned — just pull latest
    info "  ~/kaos exists, pulling latest..."
    git -C "$KAOS_DIR" fetch origin 2>/dev/null || warn "Fetch failed"
    git -C "$KAOS_DIR" reset --hard "origin/$KAOS_BRANCH" 2>/dev/null || warn "Reset failed"
else
    info "  Cloning KAOS to ~/kaos..."
    git clone --branch "$KAOS_BRANCH" --single-branch --depth 1 \
        "$KAOS_REPO" "$KAOS_DIR" || fatal "Failed to clone KAOS repo"
    info "  Clone complete"
fi
echo ""

# --- Step 4: Add [update_manager kaos] to moonraker.conf ---------------------

info "[4/5] Moonraker update_manager"
if [ ! -f "$MOONRAKER_CONF" ]; then
    warn "  $MOONRAKER_CONF not found — skipping update_manager setup"
else
    # KAOS update_manager section (phrozen_install.sh handles klipper/moonraker pins)
    if grep -q '\[update_manager kaos\]' "$MOONRAKER_CONF" 2>/dev/null; then
        info "  [update_manager kaos] already present"
    else
        info "  Adding [update_manager kaos]"
        cat >> "$MOONRAKER_CONF" << 'KAOS_EOF'

[update_manager kaos]
type: git_repo
path: ~/kaos
origin: https://github.com/OlyForge3D/phrozen_arco.git
primary_branch: dev
managed_services: klipper
install_script: install/phrozen_install.sh
KAOS_EOF
    fi

    info "  Update manager configured"
fi
echo ""

# --- Step 4b: Remove Phrozen phone-home, soft-shutdown, and cloud relay -------
# These are privileged operations (systemd, /etc, /root) that only need to run
# once during migration. The install script (run by Moonraker as mks) does NOT
# handle these.

TARGET_DIR="$KLIPPER_DIR/klippy/extras/phrozen_dev"

info "[4b] Removing Phrozen phone-home services"

# Kill running phone-home processes.
for proc in phrozen_slave_ota phrozen_master frpc frpc_script; do
    if pkill -f "$proc" 2>/dev/null; then
        info "  Killed $proc"
    fi
done

# Disable frpc systemd service if present.
if command -v systemctl >/dev/null 2>&1; then
    for unit in frpc.service; do
        if systemctl list-unit-files "$unit" >/dev/null 2>&1; then
            systemctl stop "$unit" 2>/dev/null || true
            systemctl disable "$unit" 2>/dev/null || true
            systemctl mask "$unit" 2>/dev/null || true
            info "  Stopped/disabled/masked $unit"
        fi
    done
fi

# Remove frp-oms directory (phone-home binaries and configs).
[ -d "$TARGET_DIR/frp-oms" ] && rm -rf "$TARGET_DIR/frp-oms" && info "  Removed frp-oms/"

# Remove /etc/frp and /usr/bin/frpc.
[ -d /etc/frp ] && rm -rf /etc/frp && info "  Removed /etc/frp/"
[ -f /usr/bin/frpc ] && rm -f /usr/bin/frpc && info "  Removed /usr/bin/frpc"

# Remove UDS socket left by phrozen_master.
rm -f /tmp/UNIX.domain 2>/dev/null || true

# Clean crontab entries referencing phone-home.
if command -v crontab >/dev/null 2>&1; then
    if crontab -l 2>/dev/null | grep -qE 'frpc|phrozen_master|phrozen_slave_ota'; then
        crontab -l 2>/dev/null | grep -vE 'frpc|phrozen_master|phrozen_slave_ota' | crontab - 2>/dev/null || true
        info "  Cleaned crontab phone-home entries"
    fi
fi

# Comment out phone-home lines in start.sh.
START_SH="$TARGET_DIR/start.sh"
if [ -f "$START_SH" ] && grep -q 'phrozen_slave_ota' "$START_SH" 2>/dev/null; then
    sed -i '/phrozen_slave_ota/{ /^[[:space:]]*#/! s/^/# KAOS disabled: / }' "$START_SH" 2>/dev/null || true
    sed -i '/killall phrozen_slave_ota/{ /^[[:space:]]*#/! s/^/# KAOS disabled: / }' "$START_SH" 2>/dev/null || true
    info "  Patched start.sh"
fi

# Comment out phone-home lines in KlipperScreen-start.sh.
KS_START="/home/mks/KlipperScreen/scripts/KlipperScreen-start.sh"
if [ -f "$KS_START" ]; then
    for pattern in phrozen_slave_ota phrozen_master frpc_script; do
        if grep -q "$pattern" "$KS_START" 2>/dev/null; then
            sed -i "/$pattern/{ /^[[:space:]]*#/! s/^/# KAOS disabled: / }" "$KS_START" 2>/dev/null || true
        fi
    done
    info "  Patched KlipperScreen-start.sh"
fi

info "[4c] Removing soft_shutdown"

# Kill soft_shutdown if running.
pkill -f '/root/soft_shutdown.sh' 2>/dev/null || true

# Comment out rc.local reference.
if [ -f /etc/rc.local ] && grep -q '/root/soft_shutdown.sh' /etc/rc.local 2>/dev/null; then
    sed -i '\|/root/soft_shutdown.sh| { /^[[:space:]]*#/! s|^|# KAOS disabled: |; }' /etc/rc.local 2>/dev/null || true
    info "  Disabled soft_shutdown in rc.local"
fi

# Disable systemd units referencing soft_shutdown.sh.
if command -v systemctl >/dev/null 2>&1; then
    grep -rl '/root/soft_shutdown.sh' /etc/systemd/system /lib/systemd/system 2>/dev/null | while IFS= read -r unitfile; do
        unit=$(basename "$unitfile")
        systemctl stop "$unit" 2>/dev/null || true
        systemctl disable "$unit" 2>/dev/null || true
        systemctl mask "$unit" 2>/dev/null || true
        info "  Stopped/disabled/masked $unit"
    done
fi

# Remove the script.
[ -f /root/soft_shutdown.sh ] && rm -f /root/soft_shutdown.sh && info "  Removed /root/soft_shutdown.sh"
[ -f "$TARGET_DIR/serial-screen/soft_shutdown.sh" ] && rm -f "$TARGET_DIR/serial-screen/soft_shutdown.sh"

info "[4d] Removing PhrozenGo (TUTK cloud relay)"

# Kill PhrozenGo processes.
pkill -f "phrozen-go-release" 2>/dev/null || true
pkill -f "PhrozenGoStart.sh" 2>/dev/null || true

# Remove PhrozenGo artifacts.
[ -f "$TARGET_DIR/PhrozenGo.tar" ] && rm -f "$TARGET_DIR/PhrozenGo.tar" && info "  Removed PhrozenGo.tar"
[ -d "/home/mks/PhrozenGo" ] && rm -rf "/home/mks/PhrozenGo" && info "  Removed ~/PhrozenGo/"
[ -f "$TARGET_DIR/PhrozenGoStart.sh" ] && rm -f "$TARGET_DIR/PhrozenGoStart.sh"
[ -f "$TARGET_DIR/serial-screen/PhrozenGoStart.sh" ] && rm -f "$TARGET_DIR/serial-screen/PhrozenGoStart.sh"

echo ""

# --- Step 5: Run KAOS installer -----------------------------------------------

info "[5/5] Running KAOS installer"
INSTALLER="$KAOS_DIR/install/phrozen_install.sh"
if [ -f "$INSTALLER" ]; then
    chmod +x "$INSTALLER"
    exec "$INSTALLER"
else
    fatal "Installer not found at $INSTALLER. Clone may have failed."
fi
