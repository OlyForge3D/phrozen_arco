# Verification tools

Static analysis tools for the Klipper config in `config/`. Run them whenever
you change a macro to confirm you haven't introduced a behavioral regression.

## Quick start

```sh
tests/verify.sh              # terse output: summaries + verdicts + INTENT explanations
tests/verify.sh --verbose    # adds: every audit warning/info, full diff body for each INTENT
```

Runs the full suite. Exits non-zero if anything fails. The `--verbose` flag
is forwarded to both `audit_macros.py` and `diff_branches.py`.

## Tools

### `tools/audit_macros.py`

Walks every `[gcode_macro]` in `config/` and reports:

| Severity | What it means |
|----------|---------------|
| `[E]` Error | Reads or writes a variable that doesn't exist; calls a macro that doesn't exist. **Exits non-zero.** |
| `[W]` Warning | Cross-macro state coupling outside of declared state containers; missing `description:` field on public macros. |
| `[I]` Info | Cross-writes to known state containers (intentional); macros that look unused but are state containers / firmware entry points. |

Run: `python3 tools/audit_macros.py`

#### How the audit classifies "state containers"

A **state container** is a macro that exists only to hold `variable_*` for
other macros to read or write — it has no real motion or extruder work in
its `gcode:` body. Examples in this repo: `_TRUSTED_HOME`,
`_RECOVERY_STATE`, `_KAOS_SAFETY_MODE_CONFIG`, `_KAOS_DYNAMIC_SPEED`,
`_PROBE_GATE`, `_LIGHTS_STATE`, `_Z_TILT_STATE`, `PRZ_RUNTIME_STATE`,
`PRZ_GEOMETRY`.

When macro X writes `SET_GCODE_VARIABLE MACRO=Y VARIABLE=… VALUE=…` to
*another* macro Y, the audit picks between two outcomes:

- If Y is a state container → `[I]` info ("intentional state-container write").
- If Y is not → `[W]` warning ("cross-macro write — coupling").

The classifier walks Y's body and asks "does this macro do real work?".
Any `G…`/`M…`/`T…` line, or any call to another active macro, counts as
real work and disqualifies Y. There's a small whitelist of
**diagnostic-only commands** that don't count as work — currently
`KAOS_LOG`, `_KAOS_LOG`, and `RESPOND`. That's why a state container can
contain a logging line in its body and still be classified correctly.
The whitelist lives in `tools/audit_macros.py` inside
`is_state_container()`. Add a name only if a new logging-only idiom
appears in the codebase (rare); never add anything with motion or state
side effects, or the audit will misclassify state containers that call it.

#### Resolving a `[W]` cross-macro write warning

Two valid responses, depending on whether the coupling is intentional:

1. **The coupling is unwanted.** Extract the shared variable into a
   dedicated `_FOO_STATE` container macro that holds nothing but
   `variable_*` declarations and (optionally) one `_KAOS_LOG` line. Update
   the writers to point at it. The warning becomes `[I]` info. Examples
   already in the repo: `_PROBE_GATE`, `_LIGHTS_STATE`, `_Z_TILT_STATE`.

2. **The coupling is genuinely OK and you don't want a state container
   for it.** Document why in a comment near the write site. The warning
   will keep firing — that's the audit's job, to surface coupling so a
   reader can find it.

### `tools/render_macros.py`

Renders a single macro to its flat sequence of g-code commands, with
recursive expansion of any sub-macro calls and state mutation on
`SET_GCODE_VARIABLE`. Mostly a library used by `diff_branches.py`, but
runnable directly for one-off inspections:

```sh
python3 tools/render_macros.py TOOLCHANGE \
    --params '{"NEXT":1, "FLUSH":50, "RETRACT_OLD":2, "RETRACT_NEW":2}' \
    --revision a35f99d   # or HEAD, or any git ref; default is working tree
```

The renderer matches Klipper's actual semantics: each macro's body is
expanded once via Jinja2 against the entry-time state; Jinja side effects
(`SET_GCODE_VARIABLE`) propagate to subsequent sub-macro renders; G-code
motion is **not** simulated (Klipper queues the rendered output without
caring about the post-motion position either). The output is suitable for
byte-for-byte diffing.

### `tools/diff_branches.py`

For every scenario in `tests/scenarios/*.json`:

1. Load the config at a baseline git revision (default `a35f99d`, the
   pre-cleanup tip).
2. Load the current working-tree config.
3. Render the scenario's `current` entry on the working tree.
4. Render the scenario's `baseline` entry (or its `synthetic_sequence`) on
   the baseline.
5. Filter both traces (drop bracket markers, RESPOND logging, comments,
   normalize numeric formatting and whitespace, drop known-intentional
   patterns) and unified-diff the result.

Per-scenario verdicts:

- `[PASS]` — byte-identical motion sequence after normalization.
- `[INTENT]` — differs, but the scenario sets `expect_diff: true` with an
  explanation. By default the verdict line and explanation are printed but
  the unified diff body is suppressed; `--verbose` includes the diff.
- `[FAIL]` — differs unexpectedly. Treat as a regression candidate;
  investigate before shipping. FAIL diffs are always shown in full.

Run: `python3 tools/diff_branches.py [--baseline REV] [--scenario NAME] [--verbose]`

### `tools/freeze_intent.py`

Captures an INTENT annotation: stores `expect_diff: true`, an explanation,
and a content hash of the current rendered trace into a scenario JSON.
Use after `verify.sh` reports `[FAIL]` or `[STALE_INTENT]` for a diff
you've reviewed and confirmed is correct.

```sh
python3 tools/freeze_intent.py <scenario_name> --reason "<what changed and why>"
```

The hash auto-deauthorizes the intent if the trace ever changes again,
forcing a future maintainer to re-verify before the run can pass.

### `tools/klipper_cfg.py`

Library: minimal Klipper-config parser that exposes `[gcode_macro]`,
`[delayed_gcode]`, and other section types. Used by both `audit_macros.py`
and `render_macros.py`.

Supports loading either from disk (`load_repo_config(repo_root)`) or from a
git revision (`load_at_revision(repo_root, rev)`).

## Scenario format

`tests/scenarios/*.json` — one file per test case. Schema:

```json
{
    "name": "short_id",
    "description": "What this scenario covers and why.",
    "state": {
        "pos_x": 100, "pos_y": 100, "pos_z": 50,
        "extruder_temp": 220, "extruder_target": 220,
        "cooling_fan_speed": 0.5
    },
    "current": {"entry_point": "MACRO", "params": {"KEY": "value"}},
    "baseline": {
        "entry_point": "MACRO",
        "params": {...}
    },
    "expect_diff": false,
    "diff_explanation": "Used when expect_diff is true; explains why a non-trivial diff is correct."
}
```

For scenarios where the current macro doesn't exist on baseline (e.g. the
`TOOLCHANGE` wrapper introduced in round 3), the `baseline` block accepts a
`synthetic_sequence` instead of `entry_point`:

```json
"baseline": {
    "synthetic_sequence": [
        {"raw": "G91"}, {"raw": "G1 Z3 F12000"}, {"raw": "G90"},
        {"raw": "T1"},
        {"call": "ORCA_PURGE", "params": {"FLUSH": 50, "RETRACT": 2}}
    ]
}
```

`raw` lines are emitted literally; `call` entries recursively render the
named macro on the baseline config.

## Adding a new scenario

1. Create `tests/scenarios/your_name.json` matching the schema above.
2. Run `python3 tools/diff_branches.py --scenario your_name` to confirm it
   either passes or — if it intentionally introduces a behavioral change —
   set `expect_diff: true` with a clear `diff_explanation`.
3. Commit. Future refactors will run the scenario in `tests/verify.sh`.

## When the audit or diff fails

`[E]` from the audit usually means a typo — the script tells you exactly
what's missing. Fix and re-run.

`[FAIL]` from the diff usually means one of:

- A real motion regression. The diff shows exactly which line changed; trace
  back to the macro that emitted it and verify the change was intentional.
  If not, revert.
- A normalization gap in `_normalize_command` or `filter_motion`. If you see
  a diff that's purely cosmetic (whitespace, formatting), extend the
  normalizer rather than letting the diff sit.
- A new intentional change. Set `expect_diff: true` on the scenario and
  document the change.
