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

# Pinned commits — these are the tested versions for the Phrozen Arco.
# Moonraker's update_manager will refuse to update beyond these.
KLIPPER_PIN="ed66982b8eb06ce8843d8b5163c6bd290e1754c9"   # v0.11.0-257
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
    info "  Cloning KAOS (sparse: config/, phrozen_dev/, install/) to ~/kaos..."

    # Use sparse checkout to avoid pulling tests/, tools/, reference/, etc.
    git clone --no-checkout --filter=blob:none --branch "$KAOS_BRANCH" \
        "$KAOS_REPO" "$KAOS_DIR" 2>/dev/null || fatal "Failed to clone KAOS repo"

    cd "$KAOS_DIR"
    git sparse-checkout init --cone
    git sparse-checkout set config phrozen_dev install
    git checkout "$KAOS_BRANCH"
    cd "$HOME"

    info "  Sparse clone complete"
fi
echo ""

# --- Step 4: Add [update_manager kaos] to moonraker.conf ---------------------

info "[4/5] Moonraker update_manager"
if [ ! -f "$MOONRAKER_CONF" ]; then
    warn "  $MOONRAKER_CONF not found — skipping update_manager setup"
else
    # Pin Klipper updates
    if grep -q '\[update_manager klipper\]' "$MOONRAKER_CONF" 2>/dev/null; then
        info "  [update_manager klipper] already present"
    else
        info "  Adding [update_manager klipper] (pinned)"
        cat >> "$MOONRAKER_CONF" << KLIPPER_EOF

[update_manager klipper]
channel: dev
pinned_commit: $KLIPPER_PIN
KLIPPER_EOF
    fi

    # Pin Moonraker updates
    if grep -q '\[update_manager moonraker\]' "$MOONRAKER_CONF" 2>/dev/null; then
        info "  [update_manager moonraker] already present"
    else
        info "  Adding [update_manager moonraker] (pinned)"
        cat >> "$MOONRAKER_CONF" << MOONRAKER_EOF

[update_manager moonraker]
channel: dev
pinned_commit: $MOONRAKER_PIN
MOONRAKER_EOF
    fi

    # KAOS update_manager section
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

# --- Step 5: Run KAOS installer -----------------------------------------------

info "[5/5] Running KAOS installer"
INSTALLER="$KAOS_DIR/install/phrozen_install.sh"
if [ -f "$INSTALLER" ]; then
    chmod +x "$INSTALLER"
    exec "$INSTALLER"
else
    fatal "Installer not found at $INSTALLER. Clone may have failed."
fi
