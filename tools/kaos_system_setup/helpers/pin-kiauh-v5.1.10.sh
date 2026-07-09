#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# ARCO System Prep helper: update KIAUH to a specific v5 tag and pin it there.
# Place this file beside phrozen_install.sh in the System Prep USB package.
# Safe to run more than once.
#
# Fix notes:
# - State backups are written outside the KIAUH git repo so they do not dirty the working tree.
# - Old internal KAOS state files inside the repo are removed before the dirty check.

set -u

: "${KIAUH_TAG:=v5.1.10}"
: "${KIAUH_PIN_BRANCH:=kiauh-v5-pinned}"
: "${KIAUH_REMOTE_URL:=}"
: "${CREATE_MISSING:=0}"
: "${KIAUH_DIR:=}"

timestamp=$(date +%Y%m%d_%H%M%S)

log() {
    echo "KIAUH_V5_PIN: $*"
}

find_kiauh_dir() {
    if [ -n "$KIAUH_DIR" ]; then
        echo "$KIAUH_DIR"
        return 0
    fi

    if [ -d /home/mks/kiauh ]; then
        echo "/home/mks/kiauh"
        return 0
    fi

    if [ -d /home/prz/kiauh ]; then
        echo "/home/prz/kiauh"
        return 0
    fi

    return 1
}

find_install_home() {
    if [ -d /home/mks ]; then
        echo "/home/mks"
        return 0
    fi
    if [ -d /home/prz ]; then
        echo "/home/prz"
        return 0
    fi
    echo "/home/mks"
    return 0
}


current_branch() {
    git rev-parse --abbrev-ref HEAD 2>/dev/null || echo UNKNOWN
}

current_describe() {
    git describe --tags --always 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || echo UNKNOWN
}

is_git_repo() {
    [ -d "$1/.git" ]
}

repo_is_dirty() {
    # Returns 0 if dirty, 1 if clean. Untracked files count as dirty.
    [ -n "$(git status --porcelain 2>/dev/null)" ]
}


cleanup_known_junk_files() {
    removed_count=0

    # Remove old KAOS state backups that earlier versions accidentally wrote inside the KIAUH repo.
    for f in .kaos_kiauh_state_before_*_pin_*.txt; do
        [ -e "$f" ] || continue
        if rm -f -- "$f" 2>/dev/null; then
            removed_count=$((removed_count + 1))
            log "removed_internal_state_file=$f"
        else
            log "remove_internal_state_file_status=failed_nonfatal file=$f"
        fi
    done

    log "cleanup_known_junk_removed_count=$removed_count"
}

ensure_origin_remote() {
    if git remote get-url origin >/dev/null 2>&1; then
        origin_url=$(git remote get-url origin 2>/dev/null || echo UNKNOWN)
        log "origin_current=$origin_url"

        if [ -n "$KIAUH_REMOTE_URL" ] && [ "$origin_url" != "$KIAUH_REMOTE_URL" ]; then
            git remote set-url origin "$KIAUH_REMOTE_URL" || return 1
            log "origin_updated=$KIAUH_REMOTE_URL"
        fi
        return 0
    fi

    if [ -n "$KIAUH_REMOTE_URL" ]; then
        git remote add origin "$KIAUH_REMOTE_URL" || return 1
        log "origin_added=$KIAUH_REMOTE_URL"
        return 0
    fi

    log "status=failed_no_origin_remote"
    return 1
}

create_missing_kiauh() {
    if [ "$CREATE_MISSING" != "1" ]; then
        log "status=skipped_kiauh_not_found"
        log "hint=set CREATE_MISSING=1 and optionally KIAUH_REMOTE_URL to clone KIAUH"
        exit 0
    fi

    if ! command -v git >/dev/null 2>&1; then
        log "status=failed_git_not_found"
        exit 1
    fi

    install_home=$(find_install_home)
    target="$install_home/kiauh"

    if [ -z "$KIAUH_REMOTE_URL" ]; then
        KIAUH_REMOTE_URL="https://github.com/dw-0/kiauh.git"
    fi

    log "kiauh_missing_create_requested=1"
    log "clone_target=$target"
    log "clone_remote=$KIAUH_REMOTE_URL"

    git clone "$KIAUH_REMOTE_URL" "$target" || {
        log "status=failed_clone"
        exit 1
    }

    KIAUH_DIR="$target"
}

already_pinned_to_tag() {
    current_tag=$(current_describe)
    current_branch_name=$(current_branch)

    if [ "$current_tag" = "$KIAUH_TAG" ] && [ "$current_branch_name" = "$KIAUH_PIN_BRANCH" ]; then
        return 0
    fi

    return 1
}

log "script_started_at=$(date)"
log "KIAUH_TAG=$KIAUH_TAG"
log "KIAUH_PIN_BRANCH=$KIAUH_PIN_BRANCH"
log "CREATE_MISSING=$CREATE_MISSING"

if ! command -v git >/dev/null 2>&1; then
    log "status=failed_git_not_found"
    exit 1
fi

if ! kiauh_path=$(find_kiauh_dir); then
    create_missing_kiauh
    kiauh_path="$KIAUH_DIR"
fi

log "kiauh_path=$kiauh_path"

if ! is_git_repo "$kiauh_path"; then
    log "status=skipped_not_git_repo"
    exit 0
fi

cd "$kiauh_path" || {
    log "status=failed_cannot_cd"
    exit 1
}

cleanup_known_junk_files

if already_pinned_to_tag; then
    log "current_branch=$(current_branch)"
    log "current_describe=$(current_describe)"
    log "status=skipped_already_pinned_to_$KIAUH_TAG"
    log "script_finished_at=$(date)"
    exit 0
fi

if repo_is_dirty; then
    log "working_tree_dirty=1"
    log "status=skipped_dirty_working_tree"
    log "hint=clean or backup the KIAUH folder before pinning to $KIAUH_TAG"
    log "dirty_status_begin"
    git status --porcelain 2>/dev/null || true
    log "dirty_status_end"
    exit 0
fi

ensure_origin_remote || {
    log "status=failed_origin_remote"
    exit 1
}

log "fetch_begin"
# Fetch tags from origin. This works with old Git and avoids relying on newer syntax.
if ! git fetch origin --tags; then
    log "status=failed_fetch_tags"
    exit 1
fi
log "fetch_status=completed"

if ! git rev-parse -q --verify "refs/tags/$KIAUH_TAG" >/dev/null 2>&1; then
    log "status=failed_missing_tag_$KIAUH_TAG"
    log "hint=confirm the origin remote is correct and that the tag exists upstream"
    exit 1
fi

tag_commit=$(git rev-list -n 1 "$KIAUH_TAG" 2>/dev/null || echo UNKNOWN)
log "target_tag_commit=$tag_commit"

# Pin to an exact tag by creating/resetting a local branch at that tag.
# No upstream is configured on purpose, so ordinary pulls do not silently move it forward.
if ! git checkout -B "$KIAUH_PIN_BRANCH" "$KIAUH_TAG"; then
    log "status=failed_checkout_pin_branch"
    exit 1
fi

# Remove upstream tracking if Git supports it. Failure is non-fatal on old Git.
git branch --unset-upstream "$KIAUH_PIN_BRANCH" >/dev/null 2>&1 || true

log "final_branch=$(current_branch)"
log "final_describe=$(current_describe)"
log "final_head=$(git rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
log "status=completed_pinned_to_$KIAUH_TAG"
log "script_finished_at=$(date)"
exit 0
