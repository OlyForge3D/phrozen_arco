# Phrozen Arco – KAOS Klipper Add-On System

## Project Status

This is a development project for the Phrozen Arco running Klipper.

KAOS modifies stock Phrozen Arco behavior. It is intended for advanced users who are comfortable with SSH, Klipper configuration files, firmware updates, and recovery from configuration errors.

Use at your own risk. Keep backups of your working configuration before installing.

---

## What is KAOS?

KAOS is a modular Klipper add-on system for the Phrozen Arco.

It provides:

- safer movement and homing behavior
- centralized user configuration
- split feature-based config files
- AMS / Chroma-related macro improvements
- adaptive mesh and leveling helpers
- lighting, fan, beeper, and stepper helpers
- optional Python-assisted logging and translation support
- USB installer support for easier deployment

KAOS is no longer a single-file add-on. The current architecture uses a top-level config file plus modular feature files.

---

## Current Architecture

KAOS is organized into three main areas:

```text
/home/mks/printer_data/config/
├── printer.cfg
├── printer_gcode_macro.cfg
├── kaos.cfg
└── kaos/
    ├── kaos_beeper.cfg
    ├── kaos_debug.cfg
    ├── kaos_dynamic_speed.cfg
    ├── kaos_fans.cfg
    ├── kaos_lights.cfg
    ├── kaos_logging.cfg
    ├── kaos_mesh.cfg
    ├── kaos_safety.cfg
    ├── kaos_screws_tilt.cfg
    ├── kaos_steppers.cfg
    ├── kaos_z_tilt.cfg
    └── magic_ams_by_chris.cfg
```

Python support files are installed here:

```text
/home/mks/klipper/klippy/extras/phrozen_dev/
├── dev.py
├── kaos_logging.py
├── kaos_translations.py
└── lang/
    ├── kaos_translations_en.py
    ├── kaos_translations_fr.py
    └── kaos_translations_zh.py
```

The main entry point from `printer.cfg` is:

```ini
[include kaos.cfg]
```

`kaos.cfg` then loads the split feature files from the `kaos/` directory.

---

## Key Design Rules

### 1. `kaos.cfg` is the top-level KAOS config

`kaos.cfg` should contain the main user-facing configuration and include structure.

### 2. Feature logic belongs in split files

Feature-specific macros belong in the `/config/kaos/` folder.

Examples:

- fan logic → `kaos_fans.cfg`
- Z tilt logic → `kaos_z_tilt.cfg`
- safety wrappers → `kaos_safety.cfg`
- adaptive mesh → `kaos_mesh.cfg`
- logging wrappers → `kaos_logging.cfg`

### 3. `_USER_CONFIG` is the central policy/config macro

User-adjustable KAOS settings should be exposed through `_USER_CONFIG` where practical.

### 4. Internal helper macros use underscore names

Internal helpers should generally be named with a leading underscore, for example:

```text
_KAOS_LOG
_KAOS_STARTUP_LOGGING
_KAOS_SAFETY_MODE_REQUIRE_PHYSICAL_TRUSTED_XYZ
```

This keeps the UI macro list cleaner.

### 5. Public compatibility wrappers may exist temporarily

Some public names may remain as compatibility wrappers during transition, such as:

```text
KAOS_LOG
```

But internal KAOS config files should prefer:

```text
_KAOS_LOG
```

---

## Installation Overview

KAOS is installed using a Phrozen-style USB update package.


---

## Installer Verification

After installing, check that the installer ran:

```bash
cat /home/mks/printer_data/config/kaos_install_ran.txt
```


Confirm the kaos folder exists:

```bash
ls -la /home/mks/printer_data/config/kaos/
```

Confirm language files copied:

```bash
ls -la /home/mks/klipper/klippy/extras/phrozen_dev/lang/
```

Confirm Python support files copied:

```bash
ls -la /home/mks/klipper/klippy/extras/phrozen_dev/kaos_logging.py
ls -la /home/mks/klipper/klippy/extras/phrozen_dev/kaos_translations.py
```

---

## Important Restart Note

After installing Python files, do a full machine restart.

Restarting Klipper from the UI may not fully reload updated Python modules.

Recommended:

```bash
sudo reboot
```

or power-cycle the printer.

---

## Logging System

KAOS uses two layers of logging.

### Config-level logging

Config macros should use:

```gcode
_KAOS_LOG LEVEL=2 CATEGORY=TEST MSG="Message here"
```

Level mapping:

```text
0 = ERROR
1 = WARN
2 = INFO
3 = DEBUG
```

### Compatibility logging

`KAOS_LOG` may exist as a compatibility wrapper for older calls, but new KAOS config files should use `_KAOS_LOG`.

To search for outdated public calls:

```bash
grep -R -n "^[[:space:]]*KAOS_LOG[[:space:]]" /home/mks/printer_data/config
```

Harmless console prefixes like this do not need changing:

```gcode
RESPOND PREFIX="KAOS_LOG" MSG="..."
```

---

## Translation Support

KAOS includes Python translation support using:

```text
kaos_translations.py
lang/
```

Language files live in:

```text
/home/mks/klipper/klippy/extras/phrozen_dev/lang/
```

Missing translations should fall back safely rather than breaking printer behavior.

Do not translate or suppress vendor messages that are used as functional control signals.

Some Phrozen / Arco console messages appear to be read by other parts of the system, including HMI, AMS, and lighting behavior.

---

## Major Feature Areas

### Safety and Trusted Homing

KAOS adds a trusted-home framework because the Arco may report axes as homed after `SET_KINEMATIC_POSITION`, even when the printer has not physically homed.

Core concepts:

- physical trusted XY
- physical trusted XYZ
- recovery authorization
- internal motion bypass for controlled vendor routines

Relevant files:

```text
kaos_safety.cfg
magic_ams_by_chris.cfg
```

---

### Homing and Movement Protection

KAOS wraps or guards movement-related behavior to reduce unsafe motion after startup, failed recovery, or false homed-state reporting.

Important macros may include:

```text
PG28
G28 wrapper
_REQUIRE_TRUSTED_XY
_REQUIRE_TRUSTED_XYZ
```

Exact macro names may vary by development version.

---

### AMS / Chroma / Purge Behavior

KAOS includes AMS and purge-related macro improvements, including safe service movement and purge/wipe handling.

Relevant routines may include:

```text
PG101
PRZ_WIPEMOUTH
PRZ_WAITINGAREA
PRZ_CUT_WAITINGAREA
PRZ_PAUSE_WAITINGAREA
_SAFE_SERVICE_TRANSIT
ORCA_PURGE
```

These routines should be treated carefully because some vendor messages and P-codes are functional, not merely cosmetic logs.

---

### Bed Mesh

KAOS includes an adaptive bed mesh wrapper:

```text
BED_MESH_CALIBRATE_CUSTOM
```

It can adjust mesh density based on print size and requires trusted physical homing before probing.

Relevant file:

```text
kaos_mesh.cfg
```

---

### Z Tilt

KAOS includes Z tilt helpers such as:

```text
Z_TILT_ONCE
Z_TILT_CLEAR
Z_TILT_ADJUST wrapper
```

Relevant file:

```text
kaos_z_tilt.cfg
```

---

### Screws Tilt

KAOS includes guided bed screw adjustment wrappers.

Relevant file:

```text
kaos_screws_tilt.cfg
```

---

### Fans

KAOS can manage board fan behavior using MCU and CPU temperature logic.

Relevant file:

```text
kaos_fans.cfg
```

---

### Lights

KAOS includes startup and manual light control helpers.

Relevant file:

```text
kaos_lights.cfg
```

---

### Beeper

KAOS includes optional beep/startup notification support.

Relevant file:

```text
kaos_beeper.cfg
```

---

### Dynamic Speed

KAOS includes optional dynamic speed logic based on Z height.

Relevant file:

```text
kaos_dynamic_speed.cfg
```

---

### Stepper Idle / Hold Current

KAOS includes optional stepper hold-current helpers.

Relevant file:

```text
kaos_steppers.cfg
```

---

## Common Checks

### Check for old `KAOS_LOG` calls

```bash
grep -R -n "^[[:space:]]*KAOS_LOG[[:space:]]" /home/mks/printer_data/config
```

### Check for KAOS startup messages

```bash
grep -n "KAOS\|ADDON_LOG\|kaos_logging\|kaos_translations" /home/mks/printer_data/logs/klippy.log | tail -100
```

### Check for Klipper errors

```bash
grep -i -n "error\|failed\|traceback\|unknown command\|unable\|not found" /home/mks/printer_data/logs/klippy.log | tail -100
```

### Check installed split files

```bash
find /home/mks/printer_data/config/kaos -maxdepth 1 -type f -name "*.cfg" -ls
```

### Check installed language files

```bash
find /home/mks/klipper/klippy/extras/phrozen_dev/lang -maxdepth 1 -type f -name "*.py" -ls
```

---

## Development Notes

This project is actively changing.

Known areas of active development:

- installer reliability
- split config layout
- logging architecture
- translation files
- AMS / Chroma command behavior
- purge-into-infill and post-purge priming behavior
- trusted-home safety framework
- minimizing changes to stock Phrozen Python files

When possible, KAOS should prefer add-on files and lightweight hooks over large vendor-file rewrites.

---

## Disclaimer

This project modifies stock Phrozen Arco Klipper behavior.

These files are tested only on specific machines and firmware versions. Your printer, firmware, hardware revision, slicer setup, and AMS/Chroma behavior may differ.

Use at your own risk.

Always keep a known-good backup of:

```text
printer.cfg
printer_gcode_macro.cfg
kaos.cfg
kaos/
dev.py
cmds.py
```

No warranty is provided.







OLD 




# This is a DEV project
# These instructions are incorrect

# Phrozen Arco – Klipper Add-On System (KAOS)
## Purpose

This repository implements a centralized,  Klipper add-on system built around a single configuration file:
addon.cfg

The goal is to:
- Provide one authoritative config file for enabling/disabling features
- Avoid editing multiple .cfg files when tuning or experimenting
- Allow clean inclusion or exclusion of optional mods
- Make behavior predictable, debuggable, and reversible

If a feature exists, it should be:
- Declared
- Enabled or disabled
- Configured
…from addon.cfg.

## Instructions📑:
Installation intructions can be found in the [config/README.md](config/README.md) file in the [config directory](config/)

# Features/Functions


## Configuration & Core Infrastructure
Acts as a central settings area where you can turn features on or off and adjust how different parts of the system behave, all from one place.
- `_USER_CONFIG` — central configuration / policy macro support  
- Static include: `magic_ams_by_chris.cfg` — AMS / purge subsystem  

## AMS / Multi-Material Control
- `apply_transit_override` — adjusts internal waiting-area position used during service moves  
- `PG101` — smart pre-cut routine with optional extra cuts before firmware toolchange  
- `ORCA_PURGE` — main color-change purge routine used by Orca Slicer  
- `PRZ_SPITTING_START` — fixed-length priming of new filament after toolchange  
- `PRZ_SPITTING_NORMAL` — disabled stock purge step (handled by ORCA_PURGE instead)  
- `PRZ_SPITTING_END` — disabled stock temp-restore step (handled by ORCA_PURGE instead)  
- `_SAFE_SERVICE_TRANSIT` — shared safe movement logic for service and purge areas  
- `PRZ_WAITINGAREA` — moves toolhead to safe waiting position  
- `PRZ_CUT_WAITINGAREA` — moves toolhead safely to cutter / chute area  
- `PRZ_PAUSE_WAITINGAREA` — safe pause position away from the print  
- `PRZ_WIPEMOUTH` — multi-lane nozzle wipe routine for even wear on wiper  
- `PRINT_END` override — adds optional extra cuts before final firmware retract and shutdown  

## Cooling & Fan Control
Automatically manages the mainboard fan to keep the printer electronics cool while reducing unnecessary fan noise. The system uses temperature readings to decide when the fan should run faster or slower.
- `temperature_sensor cpu_temp` — host CPU temperature  
- `temperature_fan board_fan` — MCU-temp watermark fan control  
- `apply_board_fan_target` — startup application of `_USER_CONFIG.board_fan_target`  
- `BOARD_FAN_CPU_OVERRIDE` — CPU-based override state machine  
- `BOARD_FAN_CPU_LOOP` — periodic CPU/fan evaluation loop  

## Lighting Control
Controls the printer’s lights at startup and during normal use, allowing automatic lighting and easy manual toggling from the UI.
- `TURN_ON_LIGHT_AT_BOOT` — startup light routine  
- `LIGHTS_OFF_DELAY` — delayed light-off routine  
- `Lights_On` / `Lights_Off` / `Lights_Toggle` — UI-integrated light macros  

## Sound & Notifications
Provides simple beep sounds for startup and notifications so you can hear when certain events happen.
- `[output_pin beeper]` — buzzer pin definition  
- `startup_beep` — startup beep routine gated by `_USER_CONFIG.enable_startup_beep`  
- `Beep_Notify` — general-purpose notification tone macro  

## Core Behavior Overrides (Replace Stock Logic)
Changes a few built-in printer behaviors to make them safer and more reliable, especially for homing and bed mesh calibration.
- `PG28` — stateful homing wrapper replacing stock behavior  
- `PG28_CLEAR_HAS_RUN` — reset PG28 run-state  
- `G30` override — removes `BED_MESH_PROFILE LOAD=default` behavior  

## Bed Leveling & Mesh Routines
Helps guide manual bed leveling and automatically adjusts how detailed bed probing is based on the size of your print.
- `SCREWS_TILT_CALCULATE` wrapper — homes then runs screws tilt  
- `[screws_tilt_adjust]` — bed screw geometry / leveling config  
- `BED_MESH_CALIBRATE_CUSTOM` — adaptive probe-count mesh calibration wrapper  

## Gantry Tramming (Dual Z Tilt)
Keeps the printer’s gantry level by automatically aligning both Z motors, while avoiding unnecessary repeat leveling.
- `Z_TILT_ADJUST` wrapper — homes if needed, then calls base tilt  
- `Z_TILT_ONCE` — run-once tramming logic with optional force  
- `Z_TILT_CLEAR` — clears the run-once flag  
- `[z_tilt]` — dual-Z geometry definition  

## Motion Control (Dynamic Speed by Z Height)
Automatically slows the printer down on tall or narrow prints to reduce wobble, ringing, and print failures.
- `DYNAMIC_SPEED` — state holder  
- `DYNAMIC_SPEED_ENABLE` — enable + capture base accel  
- `DYNAMIC_SPEED_DISABLE` — disable + restore captured accel  
- `DYNAMIC_SPEED_LOOP` — periodic Z-band evaluation and application  

## Stepper Thermal / Idle Management
Reduces motor heat and noise when the motor is idle to help protect components and keep the printer quieter.
- `apply_hold_current` — startup routine to set HOLDCURRENT values  


## Disclaimer

This configuration modifies stock Phrozen Arco Klipper behavior.

- These settings have been tested on our own machines
- Your printer, hardware, and setup may differ
- Results may vary (YMMV)
- Use at your own risk
- No warranty is provided

Always keep a backup of your working configuration before making changes.