#!/usr/bin/env bash
# Run the full verification suite.
#
# Default output is terse:
#   - audit prints summary line; warnings/info hidden
#   - diff prints PASS/INTENT/FAIL/STALE_INTENT verdicts; INTENT shows the
#     explanation text but suppresses the actual diff body
#
# Flags / environment:
#   --verbose / -v        Forward --verbose to both audit and diff. Audit
#                         dumps every warning + info; diff includes the
#                         unified diff for each [INTENT] scenario.
#   BASELINE=<ref>        Override the git ref to compare against.
#                         Default: origin/PhrozenArcoKAOS (this repo's
#                         long-lived development branch).
#                         Examples:
#                           BASELINE=main tests/verify.sh
#                           BASELINE=$(git merge-base origin/PhrozenArcoKAOS HEAD) tests/verify.sh
#
# Exits non-zero if anything fails (audit errors; diff FAIL or STALE_INTENT
# or ERROR).
set -e
cd "$(dirname "$0")/.."

VERBOSE=""
case "${1:-}" in
    -v|--verbose) VERBOSE="--verbose" ;;
    "")           ;;
    *) echo "Usage: $0 [--verbose|-v]" >&2; exit 2 ;;
esac

BASELINE=${BASELINE:-origin/PhrozenArcoKAOS}

echo "=========================================="
echo "STEP 1: Static audit (variable / call graph)"
echo "=========================================="
python3 tools/audit_macros.py $VERBOSE
echo

echo "=========================================="
echo "STEP 2: Behavioral equivalence vs $BASELINE"
echo "=========================================="
python3 tools/diff_branches.py --baseline="$BASELINE" $VERBOSE
echo

echo "All checks passed."
