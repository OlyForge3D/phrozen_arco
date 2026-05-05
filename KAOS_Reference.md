# KAOS v0.95 — Controls & Configuration Reference

---

## 1. End-User Facing Controls

These are commands you can run from the Klipper/Fluidd console or via the **KAOS Menu** popup (`KAOS_MENU`).

---

### Lights

**`KAOS_LIGHTS_ON` / `KAOS_LIGHTS_OFF` / `KAOS_LIGHTS_TOGGLE`**
Turn the chamber light on, off, or flip its current state.

---

### Sound

**`KAOS_BEEP_NOTIFY`**
Play a three-tone notification sequence on the board buzzer.

---

### Dynamic Speed

**`KAOS_DYNAMIC_SPEED_ENABLE` / `KAOS_DYNAMIC_SPEED_DISABLE`**
Enable or disable automatic speed and acceleration reduction as print height increases. Designed for tall, narrow, or top-heavy prints. On enable, captures the current acceleration as a baseline and starts a polling loop; on disable, restores original acceleration and resets speed scaling to 100%.

---

### Safety Mode

**`KAOS_SAFETY_MODE_SAFE` / `KAOS_SAFETY_MODE_BULLETPROOF`**
Switch between two safety profiles. **Safe** allows raw G0/G1 motion (e.g. Fluidd jog buttons) while still enforcing macro-level guards. **Bulletproof** blocks all raw movement unless the printer has a trusted home or power-loss recovery is authorized.

**`AUTHORIZE_POWER_LOSS_RECOVERY`**
Temporarily authorizes movement after a power loss without requiring a re-home. This allows a print to be continued but does not physically verify axis position — use with care.

---

### Calibration / Mesh / Tilt

**`G28` (via menu: Home Printer)**
Homes all axes using the trusted-home safety system.

**`BED_MESH_CALIBRATE` (Full Bed Mesh)**
Runs a full bed mesh probe across the entire print surface.

**`Z_TILT_ONCE`**
Runs Z tilt adjustment once per session; subsequent calls are skipped unless the flag is cleared. Accepts `FORCE=1` to override and re-run.

**`Z_TILT_ADJUST`**
Runs Z tilt adjustment immediately (safety-guarded; requires trusted XYZ home).

**`Z_TILT_CLEAR`**
Resets the run-once flag so `Z_TILT_ONCE` will execute again on the next call.

**`BED_MESH_PROFILE LOAD=default` / `SAVE=default` / `BED_MESH_CLEAR`**
Load the saved default mesh profile, save the current mesh as default (also calls `SAVE_CONFIG`), or clear the currently active mesh.

**`SCREWS_TILT_CALCULATE`**
Auto-homes if needed, then runs the screw tilt calculation to guide manual bed levelling of all four corners.

**`SAVE_CONFIG`**
Saves pending configuration changes to `printer.cfg` and restarts Klipper.

---

### Logging

**`KAOS_SET_LOG_LEVEL LEVEL=<0-3>`**
Set the verbosity of KAOS console output. `0`=ERROR, `1`=WARN (default/quiet), `2`=INFO, `3`=DEBUG.

**`KAOS_TOGGLE_LOG_LEVEL`**
Toggles between quiet (WARN) and debug modes.

**`KAOS_SET_LOG_FLAGS CATEGORIES=<0|1> TIMESTAMP=<0|1>`**
Controls log formatting. `CATEGORIES=1` prefixes each message with its subsystem tag (e.g. `[FAN]`, `[MESH]`). `TIMESTAMP=1` adds timestamps (Python-side logger).

**`KAOS_SET_LOG_LANGUAGE LANG=<en|fr|zh>`**
Sets the language for KAOS Python logger output. Options: `en` (English), `fr` (Français), `zh` (Chinese/Original).

**`KAOS_LOG_STATUS`**
Prints the current logging configuration (level, categories, timestamp, language) to the console.

---

### Debug / Recovery

**`DEBUG_TRUST`**
Prints the current trusted-home state (XY, Z, XYZ) and Klipper's `homed_axes` value to the console. Useful for diagnosing unexpected motion blocks.

---

### Multi-Colour Printing (Magic AMS by Chris)

**`TOOLCHANGE NEXT=<n> FLUSH=<mm> RETRACT_OLD=<mm> RETRACT_NEW=<mm>`**
Slicer-facing tool change entry point. Lifts Z, retracts the old filament, and queues a post-prime purge for after the firmware's cut/load/prime cycle. Normally called automatically by Orca slicer's Change-Filament G-code.

**`ORCA_PURGE FLUSH=<mm> RETRACT=<mm>`**
Executes the colour-transition purge after a tool change. Splits large purge volumes into segments (`max_poop_size`), with fan cooling and a kick between each. Can be called standalone for testing.

---

## 2. User Configuration Settings

These live in `_USER_CONFIG` inside `kaos.cfg`. Edit them directly in the config file to change defaults; runtime changes can also be made via the macros above.

---

### Startup Behaviour

**`variable_enable_startup_light`** (`0` / `1`, default: `1`)
Turn the chamber light on automatically at boot.

**`variable_enable_startup_beep`** (`0` / `1`, default: `0`)
Play a short two-tone beep sequence when the printer finishes booting.

---

### Stepper Motors

**`variable_enable_hold_current`** (`0` / `1`, default: `1`)
Reduce TMC stepper hold current after homing to lower heat and wear. Applied values: X/Y = 1.0A, Z/Z1 = 0.9A, extruder = 0.5A.

---

### Board Fan Control

**`variable_enable_board_fan_ctrl`** (`0` / `1`, default: `1`)
Enable KAOS temperature-based control of the board cooling fan. When disabled, the fan falls back to its hardware default.

**`variable_board_fan_target`** (°C, default: `40`)
MCU temperature at which the board fan turns on under normal conditions.

**`variable_cpu_fan_on`** (°C, default: `55`) / **`variable_cpu_fan_off`** (°C, default: `45`)
CPU temperature thresholds for forcing the board fan on (override) and releasing it back to MCU-based control (with hysteresis).

**`variable_cpu_override_target`** (°C, default: `10`)
The fan target temperature set during a CPU override (effectively forces full fan speed).

---

### Dynamic Speed by Height

**`variable_dynamic_z1`** (mm, default: `100`) / **`variable_dynamic_z2`** (mm, default: `160`)
Height thresholds that define the three speed bands: full speed below `z1`, mid profile between `z1`–`z2`, high-Z profile above `z2`.

**`variable_dynamic_accel_mid`** (mm/s², default: `8000`) / **`variable_dynamic_accel_high`** (mm/s², default: `4000`)
Acceleration limits applied when entering the mid and high Z bands respectively.

**`variable_dynamic_speed_mid`** (%, default: `70`) / **`variable_dynamic_speed_high`** (%, default: `50`)
M220 global speed scale percentages applied in the mid and high Z bands.

---

### Multi-Colour / AMS Purge

**`variable_initial_purge_length`** (mm, default: `80`)
Extra filament purged on the first colour load when the slicer sends `FLUSH=0`. This is on top of the firmware's built-in 55mm prime.

**`variable_max_poop_size`** (mm, default: `100`)
Maximum purge volume per segment. Larger flush volumes are split into multiple segments with a fan-cool and kick between each.

---

### Logging Defaults

**`variable_log_level`** (`0`–`3`, default: `1`)
Startup log verbosity. `0`=ERROR, `1`=WARN, `2`=INFO, `3`=DEBUG.

**`variable_log_categories`** (`0` / `1`, default: `1`)
Show subsystem category tags in log messages (e.g. `[FAN]`, `[MESH]`).

**`variable_log_timestamp`** (`0` / `1`, default: `0`)
Prefix Python-side KAOS log messages with a timestamp.

**`variable_log_language`** (`en` / `fr` / `zh`, default: `'en'`)
Language for Python-side KAOS log output.
