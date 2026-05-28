# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

KAOS (Klipper Add-On System) is a modular Klipper firmware extension for the Phrozen Arco 3D printer. It consists of two layers:

1. **Klipper config files** (`config/`) — gcode macros, loaded via `printer.cfg → kaos.cfg → kaos/*.cfg`
2. **Python Klipper extras** (`phrozen_dev/`) — installed to `/home/mks/klipper/klippy/extras/phrozen_dev/` on the printer

## Running tests

```sh
tests/verify.sh              # quiet: summaries + verdicts only
tests/verify.sh --verbose    # full warnings + per-INTENT diffs
```

The suite exits non-zero on any failure. Run it after every macro change.

### Individual tools

```sh
python3 tools/audit_macros.py                         # static analysis only
python3 tools/diff_branches.py --scenario <name>      # one scenario
python3 tools/render_macros.py MACRO_NAME             # inspect rendered g-code
BASELINE=<git-ref> tests/verify.sh                    # compare against a specific ref
```

### Freezing an intentional behavioral change

When `verify.sh` reports `[FAIL]` for a diff you've reviewed and confirmed is correct:

```sh
python3 tools/freeze_intent.py <scenario_name> --reason "<what changed and why>"
```

### Adding a test scenario

Create `tests/scenarios/<name>.json` with `name`, `description`, `state`, `current`, and `baseline` fields. See `tests/README.md` for the full schema including `synthetic_sequence` (for macros that didn't exist on baseline) and `macro_state_overrides`.

## Building a release

```sh
tools/build_release.sh                  # auto from git describe --tags
tools/build_release.sh 1.9.9-k0.9.5    # explicit tag
tools/build_release.sh 0.9.5 1.9.9     # manual mode (no tag-format check)
```

Output goes to `dist/`. Tags must match `<firmware>-k<kaos>` (e.g. `1.9.9-k0.9.5`). CI runs `tests/verify.sh` before building.

## Architecture

### Config layer

`printer.cfg` includes `kaos.cfg`, which includes the split feature files:

```
config/
├── printer.cfg               # stock Phrozen; includes kaos.cfg
├── printer_gcode_macro.cfg   # stock + KAOS-wrapped vendor macros
├── kaos.cfg                  # top-level KAOS loader; contains _USER_CONFIG
└── kaos/
    ├── kaos_fans.cfg         # board/CPU fan control
    ├── kaos_filament.cfg     # filament load/unload macros
    ├── kaos_lights.cfg       # LED control
    ├── kaos_logging.cfg      # _KAOS_LOG and logging state macros
    ├── kaos_safety.cfg       # trusted-home framework, motion guards
    ├── kaos_dynamic_speed.cfg
    ├── kaos_z_tilt.cfg
    ├── kaos_screws_tilt.cfg
    ├── kaos_steppers.cfg
    ├── kaos_beeper.cfg
    ├── kaos_debug.cfg
    ├── kaos_menu.cfg
    └── magic_ams_by_chris.cfg  # multi-color/AMS purge logic
```

### Python layer

```
phrozen_dev/
├── dev.py                  # Klipper extension entry; installs kaos_logging shim
├── kaos_logging.py         # log-level filter + protocol/HMI-safe pass-through
├── cmds.py
├── base.py
└── cwebsocketapis.py
```

After installing or updating Python files, the printer needs a **full power-cycle** — a Klipper-only restart does not reload Python modules.

### Static analysis tools

```
tools/
├── audit_macros.py    # walks all [gcode_macro] sections; reports broken refs, undefined calls
├── render_macros.py   # Jinja2 renderer matching Klipper semantics (used by diff_branches)
├── diff_branches.py   # scenario runner: compares working tree vs baseline ref
├── freeze_intent.py   # writes expect_diff + content hash into a scenario JSON
└── klipper_cfg.py     # minimal Klipper config parser (library)
```

## Key design rules

- **`_USER_CONFIG`** in `kaos.cfg` is the single user-facing settings macro. All tunable defaults go here.
- **Feature logic belongs in `kaos/*.cfg`**, not in `kaos.cfg`. `kaos.cfg` is loader-only.
- **Internal macros use leading underscore** (`_KAOS_LOG`, `_KAOS_STARTUP_LOGGING`, `_SAFE_SERVICE_TRANSIT`). This keeps the Fluidd/Mainsail macro list clean.
- **`_KAOS_LOG` is the preferred logging call** inside KAOS config files. `KAOS_LOG` exists only as a compatibility wrapper; do not introduce new calls to it.
- **State containers** are macros that hold only `variable_*` with no real motion. Examples: `_TRUSTED_HOME`, `_RECOVERY_STATE`, `_PROBE_GATE`, `_Z_TILT_STATE`, `PRZ_RUNTIME_STATE`. Cross-writes to a state container produce `[I]` info; cross-writes to a non-container produce `[W]` warning.
- **Vendor messages are functional.** Some Arco console messages are read by HMI, AMS, and lighting subsystems. Do not suppress or translate them. The `KAOS_PROTOCOL_PREFIXES` list in `kaos_logging.py` bypasses filtering for known protocol families.
- **Prefer add-on files over vendor-file rewrites.** Minimize changes to stock Phrozen Python files.

## Logging

Config macros log via:

```gcode
_KAOS_LOG LEVEL=2 CATEGORY=FAN MSG="Message here"
```

Levels: `0=ERROR`, `1=WARN`, `2=INFO`, `3=DEBUG`.

Check for stale public `KAOS_LOG` calls (should be `_KAOS_LOG`):

```sh
grep -R -n "^[[:space:]]*KAOS_LOG[[:space:]]" config/
```

## Trusted-home safety framework

The Arco can report axes as homed after `SET_KINEMATIC_POSITION` without physical homing. KAOS tracks actual physical home state separately:

- `_TRUSTED_HOME` — state container holding `trusted_xy` and `trusted_xyz` flags
- `_RECOVERY_STATE` — tracks user-authorized power-loss recovery
- Guards like `_KAOS_SAFETY_MODE_REQUIRE_PHYSICAL_TRUSTED_XYZ` block unsafe motion until physically homed

Recovery authorization (`AUTHORIZE_POWER_LOSS_RECOVERY`) is always user-triggered, never automatic.
