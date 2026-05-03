# Verification suite

A static + behavioral safety net for changes to the Klipper config in
`config/`. Run it on every PR before merging.

```sh
tests/verify.sh                 # quiet — summaries only
tests/verify.sh --verbose       # plus full warnings + per-INTENT diffs
```

Exits non-zero if anything fails.

The suite has two steps:

1. **Static audit** (`tools/audit_macros.py`) — parses every `[gcode_macro]`
   in `config/` and reports broken references, calls to undefined macros,
   typo'd variables, missing descriptions, and dead code. Uses no git.
2. **Behavioral diff** (`tools/diff_branches.py`) — for every scenario in
   `tests/scenarios/*.json`, renders the same macro under (a) the working
   tree and (b) a baseline git ref, then byte-diffs the resulting g-code.

The baseline ref defaults to `origin/PhrozenArcoKAOS` (this repo's
long-lived development branch). Override per run with
`BASELINE=<ref> tests/verify.sh`.

## What the verdicts mean

| Verdict | Meaning | Action |
|---|---|---|
| `[PASS]` | Current and baseline produce byte-identical motion sequences (after normalization). | None. |
| `[INTENT]` | They differ, but the scenario is annotated `expect_diff: true` AND the `intent_trace_hash` matches the current trace. The annotation is authoritative. | None — the explanation tells you why. |
| `[STALE_INTENT]` | They differ, the scenario is annotated `expect_diff: true`, but the trace has *changed since the intent was frozen*. The previous explanation no longer guarantees correctness. | Re-read the diff. Decide. If still correct, re-freeze (see below). |
| `[FAIL]` | They differ and there is no intent annotation. Likely a regression. | Read the diff. Either revert the change or, if the new behavior is correct, freeze it as an intent. |
| `[ERROR]` | A macro template failed to render (typo, missing variable, undefined called macro). | Fix the typo. The audit step usually flags this too. |

`[STALE_INTENT]` and `[FAIL]` always print the unified diff so you can
triage immediately. `[INTENT]` prints the explanation only; pass
`--verbose` to also see the diff body.

## How intents work (PR-scoped, content-addressed)

When a PR makes a change that intentionally alters a scenario's trace,
that change is captured in the scenario's JSON file as three fields:

```json
{
    ...,
    "expect_diff": true,
    "diff_explanation": "TP_PUT now writes to _PROBE_GATE instead of...",
    "intent_trace_hash": "sha256:7112a66a..."
}
```

The hash is over the rendered current trace at the moment the intent was
frozen. On every subsequent run, the diff tool re-renders and re-hashes
the current trace and compares. Three outcomes:

- **Hash matches:** current trace is exactly what was approved → `[INTENT]`.
- **Hash mismatches:** trace has drifted since the intent was approved →
  `[STALE_INTENT]`. Forces a human to re-verify before the run can pass.
- **Working tree converged with baseline (e.g. after the PR merges and a
  later branch starts from main):** current and baseline are identical
  → `[PASS]` (the intent annotation is dormant but harmless).

Practical consequence: intents stay in the repo as a permanent audit
trail (`git log -p tests/scenarios/X.json` shows every accepted change to
that scenario over time, with explanation), but they auto-deauthorize the
moment the trace changes — there is no manual "clear intents on merge"
step.

## Workflow: handling a `[FAIL]` or `[STALE_INTENT]`

1. Read the diff the tool printed.
2. **If the diff looks wrong**: fix the macro you changed. Re-run.
3. **If the diff is the intentional behavior change**: freeze it.

   ```sh
   python3 tools/freeze_intent.py <scenario_name> --reason "<short, specific explanation>"
   ```

   This renders the current trace, hashes it, and writes
   `expect_diff` + `diff_explanation` + `intent_trace_hash` into
   `tests/scenarios/<scenario_name>.json`. Commit the JSON change with
   the macro change.

   The `--reason` is human-facing — it'll be shown to whoever runs
   `verify.sh` later. Be specific. E.g. *"PG104 used to write fan speed
   live-from-sensor; now writes the captured PRZ_RUNTIME_STATE value
   so PG108 and ORCA_PURGE share one source of truth."*

## Adding a new scenario

Create `tests/scenarios/<name>.json`:

```json
{
    "name": "my_scenario",
    "description": "What this exercises and why we care.",
    "state": {
        "pos_x": 100, "pos_y": 100, "pos_z": 50,
        "extruder_temp": 220
    },
    "current": {
        "entry_point": "MY_MACRO",
        "params": {"KEY": "value"}
    },
    "baseline": {
        "entry_point": "MY_MACRO",
        "params": {"KEY": "value"}
    }
}
```

Run `tests/verify.sh`. If your new scenario `[PASS]`es, you're done.
If it `[FAIL]`s, follow the workflow above.

For scenarios that need a *synthetic* baseline (e.g. macros that didn't
exist in the baseline ref, like `TOOLCHANGE`), the `baseline` block
accepts a `synthetic_sequence` instead of `entry_point` — see
`toolchange_mid_print.json` for an example.

For scenarios that need to seed a `gcode_macro` variable to a specific
value before rendering (e.g. to exercise a gated-off code path), add a
`macro_state_overrides` field. Each entry is a macro name → variable map
applied on top of cfg defaults to BOTH current and baseline state:

```json
"macro_state_overrides": {
    "_PROBE_GATE": {"g30_enabled": 0},
    "G30":         {"k": 0}
}
```

The same override is applied to both branches. Each branch only reads
variables its own code defines, so harmless extras (e.g. setting
`G30.k=0` for a current branch that no longer reads `G30.k`) just sit in
state unused. See `g30_gated_off.json` for a real example: it sets the
gate flag in both forms (the new `_PROBE_GATE.g30_enabled` and the
legacy `G30.k`) so each branch's gating logic gates correctly off, and
both produce an empty trace → byte-identical PASS.

## Files in this directory

| Path | What |
|---|---|
| `verify.sh` | One-shot runner. CI calls this; humans call this. |
| `scenarios/*.json` | One file per test case. |
| `README.md` | This file. |

## Files used by the suite

| Path | What |
|---|---|
| `tools/audit_macros.py` | Static audit — runs in step 1. |
| `tools/render_macros.py` | Klipper-mode Jinja renderer (library). |
| `tools/diff_branches.py` | Scenario runner — runs in step 2. |
| `tools/freeze_intent.py` | Captures an INTENT (with content hash). |
| `tools/klipper_cfg.py` | Minimal Klipper-config parser (library). |
| `tools/README.md` | Tool internals + advanced usage. |

## When the tools are wrong

These are static analysis tools. They render macros against a mock
printer state and compare g-code strings. They DO catch:

- Motion-sequence regressions
- Typos in macro names or variables
- Calls to nonexistent macros
- Behavioral differences in heating, fans, extruder mode, accel limits,
  positions, dwell times

They DO NOT catch:

- Hardware-specific issues (a feedrate that's fine on paper but stalls
  on your specific machine)
- Issues triggered by Klipper plugin behavior we don't simulate (the
  KAOS Python plugin's runtime state)
- Anything outside the scenarios you've written

A clean `tests/verify.sh` run is necessary but not sufficient. Always
test on real hardware before deploying — at least one cold-extruder
manual exercise of every changed motion path. The verify suite is the
fast, repeatable gate; the printer is the final arbiter.
