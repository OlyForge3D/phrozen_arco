"""
Compare gcode traces between the working tree (current) and a baseline git
revision, across a curated scenario matrix.

For every scenario in tests/scenarios/*.json:

  1. Load Config from the baseline revision (default: a35f99d) via git show.
  2. Load Config from the working tree.
  3. Render the scenario's `current` entry on the working tree.
  4. Render the scenario's `baseline` entry on the baseline:
     - If `baseline.entry_point` is set, render that single macro.
     - If `baseline.synthetic_sequence` is set, walk the list, rendering each
       {"raw": "..."} as a literal line and each {"call": "X", "params": {...}}
       as a recursive expansion of macro X.
  5. Filter both traces to motion-relevant lines and compare.

Output:

  - PASS: traces are byte-identical (after filtering brackets/comments).
  - INTENT: traces differ but the scenario's `expect_diff` flag is set;
    show the diff so a human can verify it matches the intended change.
  - FAIL: traces differ unexpectedly (regression candidate).

Exit code: 0 only if every scenario is PASS or INTENT (with diff matching
expectation); non-zero if any FAIL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from difflib import unified_diff
from pathlib import Path

# Self-importable from tools/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import re

from tools.klipper_cfg import Config, load_at_revision, load_repo_config
from tools.render_macros import (
    Trace, default_state, render_macro, seed_macro_variables, parse_call_params,
)


# ---------------------------------------------------------------------------
# Filtering: strip the bracket markers and pure-empty lines from a trace so
# the diff sees just the gcode commands, not our recursion bookkeeping.
# ---------------------------------------------------------------------------

# RESPOND / action_respond_info-driven console messages are diagnostic only —
# strip them from the comparison so logging-style refactors don't show up
# as "regressions" in the motion trace.
RESPOND_RE = re.compile(r"^\s*RESPOND\b", re.IGNORECASE)


def _normalize_command(s: str) -> str:
    """Normalize a single gcode line for comparison.

    - Strip inline `;` and `#` comments and trailing whitespace.
    - Collapse runs of whitespace into single spaces.
    - Normalize numeric formatting so `-2` == `-2.0` == `-2.00`.
    - Drop trailing English-word junk after the last well-formed gcode token
      (handles legacy lines like `G4 P45000 Added for kinematics`).
    """
    # Drop inline comments — both `;` and `#` are comment markers in Klipper.
    for marker in (";", "#"):
        s = s.split(marker, 1)[0]
    # Collapse whitespace
    s = " ".join(s.split())
    if not s:
        return s

    # Tokenize. Keep tokens that look like gcode commands or KEY=VALUE / Lvalue
    # parameters; drop trailing tokens that are bare English words.
    parts = s.split()
    keep = []
    for p in parts:
        if not keep:
            # First token must be a command. Always keep.
            keep.append(p)
            continue
        # KEY=value (KEY may be a single letter or a word; value any non-space)
        if "=" in p:
            keep.append(p)
            continue
        # Single-letter Marlin-style: A123 / A-1.5 / A12.0
        if re.match(r"^[A-Za-z]-?\d", p):
            keep.append(p)
            continue
        # Otherwise it's a stray English word — stop here.
        break

    s = " ".join(keep)

    # Numeric normalization within tokens.
    def _norm_num(tok: str) -> str:
        m = re.match(r"^([A-Za-z]?)(-?\d+(?:\.\d+)?)$", tok)
        if not m:
            # Also handle KEY=value where value is numeric
            kv = re.match(r"^(\w+=)(-?\d+(?:\.\d+)?)$", tok)
            if kv:
                key, num = kv.group(1), kv.group(2)
                try:
                    v = float(num)
                    if v == int(v):
                        return f"{key}{int(v)}"
                    return f"{key}{v:g}"
                except ValueError:
                    return tok
            return tok
        prefix, num = m.group(1), m.group(2)
        try:
            v = float(num)
            if v == int(v):
                return f"{prefix}{int(v)}"
            return f"{prefix}{v:g}"
        except ValueError:
            return tok
    return " ".join(_norm_num(p) for p in s.split())


# Lines that match any of these regexes are known-intentional changes we
# made between baseline and current. They are filtered out of BOTH sides of
# the diff so they don't show as regressions in any scenario.
INTENTIONAL_CHANGES = [
    # Round 2: PRZ_WIPEMOUTH cycle alternation removed (single-lane is the
    # only supported pattern now, no per-call cycle state).
    re.compile(r"^SET_GCODE_VARIABLE MACRO=PRZ_WIPEMOUTH VARIABLE=wipe_cycle\b"),
    # Round 1: SET_GCODE_OFFSET z=0 inside PRINT_END had a Chinese inline
    # comment in baseline that survives our `;` strip but not our `#` strip.
    # (After the #-strip fix this should already collapse, but keep this rule
    # as belt-and-suspenders.)
]


def filter_intentional(lines: list[str]) -> list[str]:
    return [l for l in lines if not any(p.match(l) for p in INTENTIONAL_CHANGES)]


def trace_hash(filtered_lines: list[str]) -> str:
    """Stable hash over the filtered motion sequence.

    Used to content-address an [INTENT] annotation. When a scenario sets
    `intent_trace_hash`, the verdict logic compares this hash of the
    currently-rendered trace against the stored value. If they match, the
    intent applies. If not, the intent is STALE and must be re-confirmed
    via `tools/freeze_intent.py`.

    The input must be the post-filter, post-normalize line list (same form
    diff sees) so cosmetic-only changes don't invalidate hashes.
    """
    h = hashlib.sha256()
    for line in filtered_lines:
        h.update(line.encode("utf-8"))
        h.update(b"\n")
    return f"sha256:{h.hexdigest()}"


def filter_motion(lines: list[str]) -> list[str]:
    """Return only the gcode lines that affect printer state, normalized for
    comparison.

    Drops:
      - "--> X ..." / "<-- X" recursion brackets (rendering bookkeeping)
      - Empty lines and pure whitespace
      - RESPOND ... diagnostic logging
      - Pure-comment lines and inline `; ...` comment tails

    Normalizes:
      - Whitespace between tokens (single space)
      - Numeric formatting (`-2` == `-2.0` == `-2.00`)
    """
    out = []
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("-->") or s.startswith("<--"):
            continue
        if s.startswith("#") or s.startswith(";"):
            continue
        if RESPOND_RE.match(s):
            continue
        norm = _normalize_command(s)
        if not norm:
            continue
        out.append(norm)
    return out


def run_startup_delayed_gcodes(cfg: Config, state: dict) -> None:
    """Klipper fires every [delayed_gcode] at boot if its `initial_duration`
    is > 0. Some of these mutate gcode_macro variables (e.g. baseline
    `apply_transit_override` set GLOBAL_PARAM.g_bottom_print_y = 302).

    For a faithful baseline render we replay these on the baseline state.
    We only render their bodies for SET_GCODE_VARIABLE side effects; we
    don't queue any motion commands since these run before any print starts.
    """
    SET_RE = re.compile(
        r"SET_GCODE_VARIABLE\s+MACRO\s*=\s*(\w+)\s+VARIABLE\s*=\s*(\w+)\s+VALUE\s*=\s*(\S+)",
        re.IGNORECASE,
    )
    from tools.render_macros import _normalize_template, _make_env, Box, _coerce_value
    from jinja2 import UndefinedError

    env = _make_env()
    for name, dg in cfg.delayed.items():
        if not dg.initial_duration:
            continue
        try:
            template = env.from_string(_normalize_template(dg.body))
            rendered = template.render(printer=Box(state), params=Box({}), rawparams="")
        except (UndefinedError, Exception):
            continue
        for line in rendered.splitlines():
            m = SET_RE.search(line)
            if m:
                tgt, var, val = m.group(1), m.group(2), m.group(3)
                ns_key = f"gcode_macro {tgt}"
                if ns_key not in state:
                    state[ns_key] = {}
                state[ns_key][var] = _coerce_value(val)


def render_baseline(cfg: Config, scenario: dict, state: dict) -> Trace:
    """Render the baseline side of a scenario.

    Supports two shapes:
      {"entry_point": "X", "params": {...}}
        -- render macro X with given params on the baseline cfg.
      {"synthetic_sequence": [{"raw": "..."}, {"call": "X", "params": {...}}, ...]}
        -- emit each raw line literally, recursively expand each call.
    """
    trace = Trace()
    bl = scenario["baseline"]
    if "entry_point" in bl:
        render_macro(cfg, bl["entry_point"], bl.get("params", {}), state, trace=trace)
        return trace
    if "synthetic_sequence" in bl:
        for step in bl["synthetic_sequence"]:
            if "raw" in step:
                trace.lines.append(step["raw"])
            elif "call" in step:
                render_macro(cfg, step["call"], step.get("params", {}), state, trace=trace)
            else:
                trace.errors.append(f"unknown synthetic_sequence step: {step}")
        return trace
    trace.errors.append("baseline has neither entry_point nor synthetic_sequence")
    return trace


def render_current(cfg: Config, scenario: dict, state: dict) -> Trace:
    trace = Trace()
    cur = scenario["current"]
    render_macro(cfg, cur["entry_point"], cur.get("params", {}), state, trace=trace)
    return trace


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def apply_macro_state_overrides(state: dict, overrides: dict) -> None:
    """Apply scenario-supplied gcode_macro variable overrides on top of the
    defaults seeded from cfg.

    Format:
        {"_PROBE_GATE": {"g30_enabled": 0}, "G30": {"k": 0}}

    The same overrides are applied to BOTH current and baseline state. Each
    branch only reads variables its version of the code defines, so harmless
    extras (e.g. setting `G30.k=0` for a current branch that no longer reads
    `G30.k`) just sit in state unused.
    """
    for macro_name, vars_dict in overrides.items():
        ns_key = f"gcode_macro {macro_name}"
        if ns_key not in state:
            state[ns_key] = {}
        for var, value in vars_dict.items():
            state[ns_key][var] = value


def run_one(scenario_path: Path, repo_root: Path, baseline_rev: str) -> dict:
    scenario = json.loads(scenario_path.read_text())

    state_overrides = scenario.get("state", {})
    macro_overrides = scenario.get("macro_state_overrides", {})

    # Build current cfg + state
    current_cfg = load_repo_config(repo_root)
    current_state = default_state(**state_overrides)
    seed_macro_variables(current_state, current_cfg)
    apply_macro_state_overrides(current_state, macro_overrides)
    current_trace = render_current(current_cfg, scenario, current_state)

    # Build baseline cfg + state. Replay any startup delayed_gcodes that
    # mutate gcode_macro variables (e.g. baseline's apply_transit_override
    # which set g_bottom_print_y to 302 at boot).
    baseline_cfg = load_at_revision(repo_root, baseline_rev)
    baseline_state = default_state(**state_overrides)
    seed_macro_variables(baseline_state, baseline_cfg)
    run_startup_delayed_gcodes(baseline_cfg, baseline_state)
    apply_macro_state_overrides(baseline_state, macro_overrides)
    baseline_trace = render_baseline(baseline_cfg, scenario, baseline_state)

    cur_lines = filter_intentional(filter_motion(current_trace.lines))
    bl_lines = filter_intentional(filter_motion(baseline_trace.lines))

    # Display the baseline ref/SHA naturally: SHAs get truncated, ref names
    # are shown verbatim (so "origin/PhrozenArcoKAOS" doesn't get cut to
    # "origin/P").
    bl_label = baseline_rev[:8] if all(c in "0123456789abcdef" for c in baseline_rev.lower()) and len(baseline_rev) >= 7 else baseline_rev
    diff = list(unified_diff(
        bl_lines, cur_lines,
        fromfile=f"baseline ({bl_label})",
        tofile="current (working tree)",
        lineterm="",
    ))

    return {
        "name": scenario.get("name", scenario_path.stem),
        "scenario_path": str(scenario_path),
        "description": scenario.get("description", ""),
        "expect_diff": scenario.get("expect_diff", False),
        "diff_explanation": scenario.get("diff_explanation", ""),
        "intent_trace_hash": scenario.get("intent_trace_hash", ""),
        "current_trace_hash": trace_hash(cur_lines),
        "current_errors": current_trace.errors,
        "baseline_errors": baseline_trace.errors,
        "current_lines": cur_lines,
        "baseline_lines": bl_lines,
        "diff": diff,
    }


def _freeze_hint(name: str, reason_placeholder: str = "describe the change") -> str:
    return (f"          To accept as intentional, run:\n"
            f"            python3 tools/freeze_intent.py {name} --reason \"{reason_placeholder}\"")


def report(results: list[dict], verbose: bool = False) -> int:
    """Print a verdict per scenario and return the overall exit code.

    Verdicts:
      [PASS]         Current trace is byte-identical to baseline.
      [INTENT]       expect_diff=true AND intent_trace_hash matches the
                     current rendered trace. The annotation is authoritative.
      [STALE_INTENT] expect_diff=true BUT intent_trace_hash either is missing
                     or doesn't match the current trace. The previous intent
                     no longer applies; re-verify and re-freeze. Treated as
                     a soft FAIL (non-zero exit).
      [FAIL]         Traces differ and there is no intent annotation.
      [ERROR]        Rendering itself failed (typo / missing macro).

    Default (verbose=False): INTENT prints verdict + explanation only, not
    the diff body. STALE_INTENT and FAIL always show the diff in full.
    """
    n_pass = n_intent = n_stale = n_fail = n_error = 0

    for r in results:
        name = r["name"]
        errs = r["current_errors"] + r["baseline_errors"]
        if errs:
            n_error += 1
            print(f"\n[ERROR] {name}")
            for e in errs:
                print(f"  - {e}")
            continue

        identical = (r["current_lines"] == r["baseline_lines"])
        if identical:
            n_pass += 1
            print(f"[PASS]    {name}: byte-identical motion sequence")
            continue

        if r["expect_diff"]:
            stored_hash = r["intent_trace_hash"]
            current_hash = r["current_trace_hash"]

            if stored_hash and stored_hash == current_hash:
                n_intent += 1
                print(f"[INTENT]  {name}: differs as expected")
                print(f"          {r['diff_explanation']}")
                if verbose:
                    print()
                    for line in r["diff"]:
                        print("    " + line)
                    print()
                else:
                    print()
                continue

            # expect_diff=true but the trace has changed (or no hash recorded).
            n_stale += 1
            print(f"[STALE_INTENT]  {name}: scenario marked expect_diff but trace has changed since the intent was frozen")
            if not stored_hash:
                print(f"          (no intent_trace_hash recorded yet — first run after marking expect_diff)")
            else:
                print(f"          stored hash:  {stored_hash}")
                print(f"          current hash: {current_hash}")
            print(f"          previous explanation: {r['diff_explanation']}")
            print(f"          Re-verify the diff. If still intentional:")
            print(f"            python3 tools/freeze_intent.py {name} --reason \"...\"")
            print()
            for line in r["diff"]:
                print("    " + line)
            print()
        else:
            # No intent annotation; this is a regression candidate.
            n_fail += 1
            print(f"[FAIL]    {name}: UNEXPECTED diff (regression candidate)")
            print(f"          {r['description']}")
            print()
            for line in r["diff"]:
                print("    " + line)
            print()
            print(_freeze_hint(name))
            print()

    parts = [f"{n_pass} PASS", f"{n_intent} INTENT"]
    if n_stale:
        parts.append(f"{n_stale} STALE_INTENT")
    parts.extend([f"{n_fail} FAIL", f"{n_error} ERROR"])
    print("Summary: " + ", ".join(parts))
    if not verbose and n_intent:
        print("(re-run with --verbose to see the full diff for each [INTENT] scenario)")
    return 0 if (n_fail == 0 and n_error == 0 and n_stale == 0) else 1


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Compare gcode traces between branches.")
    p.add_argument("--repo", default=".", help="Repo root")
    p.add_argument("--baseline", default="origin/main",
                   help="Baseline git revision to compare against (default: origin/main; "
                        "use any ref e.g. main, HEAD~1, a tag, or a SHA).")
    p.add_argument("--scenarios", default="tests/scenarios",
                   help="Directory of scenario JSON files")
    p.add_argument("--scenario", default=None,
                   help="Run a single scenario by name (without .json)")
    p.add_argument("--show-traces", action="store_true",
                   help="Print full traces, not just diffs")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="For [INTENT] scenarios, also print the actual unified diff. "
                        "Default prints the verdict + explanation but suppresses the "
                        "diff body. FAIL diffs are always shown in full.")
    args = p.parse_args(argv)

    scenario_dir = Path(args.repo) / args.scenarios
    files = sorted(scenario_dir.glob("*.json"))
    if args.scenario:
        files = [f for f in files if f.stem == args.scenario]
        if not files:
            print(f"No scenario named '{args.scenario}'", file=sys.stderr)
            return 2

    results = [run_one(f, Path(args.repo), args.baseline) for f in files]

    if args.show_traces:
        for r in results:
            print(f"\n=== {r['name']} ===")
            print("--- baseline ---")
            for line in r["baseline_lines"]:
                print(f"  {line}")
            print("--- current ---")
            for line in r["current_lines"]:
                print(f"  {line}")
        print()

    return report(results, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
