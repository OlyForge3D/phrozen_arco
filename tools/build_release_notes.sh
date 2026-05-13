#!/usr/bin/env bash
# Generate dist/RELEASE_NOTES.md for a release tag.
#
# The release notes are composed of:
#   - Header naming the KAOS + firmware versions and the tag they came from
#   - Installation section pulled verbatim from README.md's
#     "## Installation Overview" so the printed steps stay in lockstep
#     with the canonical docs
#   - "What's changed" generated from `git log <prev-tag>..<tag>` (noisy
#     by design — every commit since the previous release tag, no curation)
#
# Usage:
#   tools/build_release_notes.sh                 # tag from `git describe`
#   tools/build_release_notes.sh <firmware>-k<kaos>
#
# Output: dist/RELEASE_NOTES.md (referenced by .gitlab-ci.yml release job)

set -euo pipefail

TAG="${1:-}"
if [ -z "$TAG" ]; then
    TAG="$(git describe --tags --abbrev=0 2>/dev/null || true)"
fi
if [ -z "$TAG" ]; then
    echo "build_release_notes.sh: no tag given and no tags found" >&2
    exit 2
fi

if [[ ! "$TAG" =~ ^([0-9]+(\.[0-9]+)*)-k(.+)$ ]]; then
    echo "build_release_notes.sh: tag '$TAG' does not match <firmware>-k<kaos>" >&2
    exit 2
fi
FW_VERSION="${BASH_REMATCH[1]}"
KAOS_VERSION="${BASH_REMATCH[3]}"
if [[ "$KAOS_VERSION" =~ ^[vV] ]]; then
    echo "build_release_notes.sh: tag '$TAG' has v/V prefix on KAOS portion" >&2
    exit 2
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
README="$REPO_ROOT/README.md"
OUT="$REPO_ROOT/dist/RELEASE_NOTES.md"
mkdir -p "$(dirname "$OUT")"

# Extract the "## Installation Overview" section from README.md, stopping at
# the next "## " heading. Trailing blank lines and horizontal rules are
# stripped so the section concatenates cleanly with the rest of the notes.
INSTALL_SECTION="$(awk '
    /^## Installation Overview/ { capture=1; next }
    capture && /^## / { capture=0 }
    capture { lines[++n] = $0 }
    END {
        while (n > 0 && (lines[n] == "" || lines[n] ~ /^---+$/)) n--
        start = 1
        while (start <= n && lines[start] == "") start++
        for (i = start; i <= n; i++) print lines[i]
    }
' "$README")"

if [ -z "$INSTALL_SECTION" ]; then
    echo "build_release_notes.sh: '## Installation Overview' not found in README.md" >&2
    exit 2
fi

# Find the previous release tag (most recent tag reachable from TAG's parent).
# git describe needs annotated *or* lightweight tags via --tags. If TAG is the
# very first release, PREV_TAG ends up empty and we log all history.
PREV_TAG=""
if git rev-parse -q --verify "$TAG^{commit}" >/dev/null 2>&1; then
    PREV_TAG="$(git describe --tags --abbrev=0 "$TAG^" 2>/dev/null || true)"
fi

if [ -n "$PREV_TAG" ]; then
    RANGE="$PREV_TAG..$TAG"
    COMPARE_NOTE="Changes since \`$PREV_TAG\`:"
else
    RANGE="$TAG"
    COMPARE_NOTE="All commits up to \`$TAG\`:"
fi

CHANGES="$(git log --no-merges --pretty='- %s' "$RANGE" 2>/dev/null || true)"
if [ -z "$CHANGES" ]; then
    CHANGES="_(no commits in range)_"
fi

{
    echo "KAOS release **$KAOS_VERSION** for Phrozen Arco firmware **$FW_VERSION**."
    echo
    echo "Built from tag \`$TAG\`. Requires firmware **$FW_VERSION** — installing on a different firmware version is not supported."
    echo
    echo "## Installation"
    echo
    echo "$INSTALL_SECTION"
    echo
    echo "See the in-repo \`README.md\` and \`config/README.md\` for setup details."
    echo
    echo "## What's changed"
    echo
    echo "$COMPARE_NOTE"
    echo
    echo "$CHANGES"
} > "$OUT"

echo "Wrote $OUT"
