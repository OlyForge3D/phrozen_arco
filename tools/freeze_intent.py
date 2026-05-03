"""
Freeze an [INTENT] annotation into a scenario JSON file.

Use this after a `verify.sh` run reports `[FAIL]` or `[STALE_INTENT]` for a
scenario whose diff you've reviewed and confirmed is correct. It captures a
content-addressable hash of the current rendered trace alongside the
explanation, so the annotation auto-expires the moment the trace changes
(at which point a future maintainer is forced to re-verify).

Workflow:

    1. You change a macro. `tests/verify.sh` reports
       `[FAIL] orca_purge_initial: UNEXPECTED diff (regression candidate)`.
    2. You read the diff. You decide it's the intentional behavior change.
    3. You run:
         python3 tools/freeze_intent.py orca_purge_initial --reason "..."
       This:
         - Re-renders the scenario's current trace
         - Hashes the filtered trace
         - Writes expect_diff=true + diff_explanation + intent_trace_hash
           into the scenario JSON.
    4. You commit. `verify.sh` now shows [INTENT] with your reason.
    5. Months later, somebody changes the same scenario's behavior. The
       trace hash mismatches; verify.sh reports [STALE_INTENT] and points
       them back here. They re-verify, re-freeze, the cycle continues.

Run `python3 tools/freeze_intent.py --help` for arg details.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.diff_branches import (
    apply_macro_state_overrides, filter_intentional, filter_motion,
    render_baseline, render_current, run_startup_delayed_gcodes, trace_hash,
)
from tools.klipper_cfg import load_repo_config
from tools.render_macros import default_state, seed_macro_variables


def freeze(scenario_path: Path, reason: str, repo_root: Path = Path(".")) -> int:
    if not scenario_path.exists():
        print(f"ERROR: scenario file not found: {scenario_path}", file=sys.stderr)
        return 2

    scenario = json.loads(scenario_path.read_text())

    # Render the current trace exactly the way diff_branches does, so the
    # hash we store will match the hash diff_branches computes at verify time.
    state_overrides = scenario.get("state", {})
    macro_overrides = scenario.get("macro_state_overrides", {})
    cfg = load_repo_config(repo_root)
    state = default_state(**state_overrides)
    seed_macro_variables(state, cfg)
    apply_macro_state_overrides(state, macro_overrides)
    trace = render_current(cfg, scenario, state)

    if trace.errors:
        print(f"ERROR: render produced errors; cannot freeze:", file=sys.stderr)
        for e in trace.errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    cur_lines = filter_intentional(filter_motion(trace.lines))
    h = trace_hash(cur_lines)

    # Update the scenario JSON in-place. Preserve key ordering as best we can.
    scenario["expect_diff"] = True
    scenario["diff_explanation"] = reason
    scenario["intent_trace_hash"] = h

    scenario_path.write_text(json.dumps(scenario, indent=4) + "\n")

    print(f"Froze intent for {scenario_path.name}")
    print(f"  reason: {reason}")
    print(f"  hash:   {h}")
    print(f"  lines:  {len(cur_lines)} (filtered, normalized)")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Freeze an INTENT annotation: capture a content hash of the current trace alongside the explanation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("scenario",
                   help="Scenario name (without .json) or path to the scenario JSON file.")
    p.add_argument("--reason", "-r", required=True,
                   help="Human-readable explanation: WHY does this scenario differ from baseline? "
                        "Will be shown in verify output. Be specific.")
    p.add_argument("--scenarios", default="tests/scenarios",
                   help="Scenario directory (default: tests/scenarios)")
    p.add_argument("--repo", default=".",
                   help="Repo root (default: cwd)")
    args = p.parse_args(argv)

    repo = Path(args.repo)
    sname = args.scenario
    if sname.endswith(".json") or "/" in sname:
        scenario_path = Path(sname)
        if not scenario_path.is_absolute():
            scenario_path = repo / scenario_path
    else:
        scenario_path = repo / args.scenarios / f"{sname}.json"

    return freeze(scenario_path, args.reason, repo)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
