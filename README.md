# Phrozen Arco – KAOS (Klipper Add-On System)

## Project Status

This is a development project for the Phrozen Arco running Klipper.

KAOS modifies stock Phrozen Arco behavior. It is intended for advanced users who are comfortable with SSH, Klipper configuration files, firmware updates, and recovery from configuration errors.

Use at your own risk. Keep backups of your working configuration before installing.

---

### Jump to
- [Disclaimer](#disclaimer)
- [Credits](#thankscredits)

---

### Installation
- Download the latest version here: [Releases](https://gitlab.com/sanders.chris/phrozenarco/-/releases)
- Follow the [Installation Instructions](#installation-overview)
- Update your slicer G-Code as per: [KAOS G-code](https://gitlab.com/sanders.chris/phrozenarco/-/blob/88ec4c1dad946d2dc2edc06f8f370d3c5bf3f168/KAOS_Slicer_G-Code.md)



---

## What is KAOS?

KAOS is a modular Klipper add-on system for the Phrozen Arco.

It provides:

- disabling of /root/soft_shutdown.sh 
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

## Disable /root/soft_shutdown.sh 
/root/soft_shutdown.sh runs once every 0.1 seconds on the stock Arco searching for a button press of a button that does not exist. It consumes 10% of Arco CPU time and provides no functionality or value. It appears to be a remnent of a test. This update disables it, freeing up CPU cycles.

## Safety & movement protection
- Safer movement protection 
- Trusted homing checks/ tracking & false-homed-state protection 
- Safer recovery handling (WIP)
- Startup safety reset(WIP)
- Protected service-position moves 
- Safer probing requirements 
- Improved PG28 homing 
- Safer startup behavior 

## Logging & troubleshooting
- Cleaner console logging 
- Adjustable log level 
- Log categories 
- Debug mode support 
- KAOS state/debug helpers 


## Multi-language Console/Log Message support
- Multi-language message support 
- Selectable log/message language (en, fr, cz) more on request
- Safe missing-translation fallback 
- Vendor-control message protection 


## AMS / Chroma / multi-material
- Reduced purge waste tuning 
- Safer AMS service moves 
- Safer cutter/chute, waiting-area, pause-area movement 
- Post-purge priming control 
- Improved end-of-print cut/retract handling 


## Bed leveling & first-layer tools
- Fixed G30
- Adaptive bed mesh 
- Z Tilt 
    - Z-tilt once only runs on first print of session
- Screws Tilt helper 


## Cooling & electronics protection
- Board fan control 
- CPU temperature fan override 
- MCU temperature fan control 
- Tunable board fan target 


## Motion tuning & print stability
- Dynamic Speed by Height macro
    - Tall-thin print stability tuning 
    - Dynamic speed by Z height 
    - Dynamic speed enable/disable 
    - Automatic speed/accel restore 
-Stepper hold-current control 
    - Reduced idle motor heat/noise, extended life


## Lights, sounds & convenience
- LED light controls 
- Lights on at startup 
- Delayed lights off (WIP)
- Startup beep option
- KAOS menu helpers 


## Configuration & maintenance
- Central user settings 
- Split feature files 
- Easier troubleshooting by feature 
- Cleaner macro list 
- Compatibility wrappers for upgrades 
- Easier feature updates 

## Installation & updates
- USB update installer 
- Installer validation checks 
- Installer failure diagnostics
- Installer trace log 


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

Pre-built release zips are attached to each GitLab tag (see [Releases](https://gitlab.com/sanders.chris/phrozenarco/-/releases)). The release uses Phrozen's nested-zip format: an outer distribution wrapper containing `phrozen_dev/phrozen_dev.zip` (the inner archive the printer's updater actually consumes). To install:

1. Download `Arco_FW_V199_KAOS_<version>.zip`
2. Unzip on a PC — you'll see a `phrozen_dev/` folder containing `phrozen_dev.zip`
3. Copy that whole `phrozen_dev/` folder (with `phrozen_dev.zip` inside it) to a USB stick root
4. Plug into the printer and run the Phrozen update flow — the updater finds `phrozen_dev/phrozen_dev.zip` and unpacks it
5. The printer reboots automatically after install. If it does not, full power-cycle it (a Klipper-only restart isn't enough; Python modules need a fresh load).

---

## Releases

### Tag format

Release tags must use the format **`<firmware>-k<kaos>`**, where the firmware portion is dotted-numeric. The firmware-prefix is mandatory: every release explicitly names the Phrozen firmware version it targets and requires. Order mirrors the output zip filename (firmware first, then KAOS).

Examples:

| Tag                 | Firmware target | KAOS version | Zip filename                          |
|---------------------|-----------------|--------------|---------------------------------------|
| `1.9.9-k0.9.5`      | 1.9.9           | 0.9.5        | `Arco_FW_V199_KAOS_0.9.5.zip`         |
| `1.9.9-k1.0.0-rc1`  | 1.9.9           | 1.0.0-rc1    | `Arco_FW_V199_KAOS_1.0.0-rc1.zip`     |
| `2.0.0-k0.10`       | 2.0.0           | 0.10         | `Arco_FW_V200_KAOS_0.10.zip`          |

CI rejects any tag that does not match this format — the build job fails with a clear error before producing anything.

### CI release on tag push

```bash
git tag 1.9.9-k0.9.5
git push origin 1.9.9-k0.9.5
```

GitLab CI runs (in order):

1. `verify` — `tests/verify.sh` (audit + behavioral diff suite)
2. `build_release_zip` — validates the tag format, runs `tools/build_release.sh`, attaches the zip as a CI artifact
3. `release` — creates a GitLab [Release](https://gitlab.com/sanders.chris/phrozenarco/-/releases) page for the tag with the zip linked as a downloadable asset

### Building locally

`tools/build_release.sh` accepts the same tag format, plus a two-arg manual mode for iterating without tagging:

```bash
# Auto from `git describe --tags` (must match the tag format)
tools/build_release.sh

# From an explicit tag
tools/build_release.sh 1.9.9-k0.9.5

# Manual mode (skips tag-format validation; for local dev iteration)
tools/build_release.sh 0.9.5 1.9.9
```

The script flattens `config/` and `phrozen_dev/` into the layout the on-printer install script expects, drops in `install/phrozen_install*.sh`, stamps `KAOS_VERSION.txt` with build metadata, and zips it to `dist/`.

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

## Thanks/Credits
- Thanks to [solutionphil](https://github.com/solutionphil) for starting the original project [here](https://github.com/solutionphil/PhrozenArco):
- Thanks to  thanks to [Jay Smith](https://www.facebook.com/jay.smith.122210/) and [Edwin Tan](https://www.facebook.com/ejtan1) for the lighting macros
- Thanks to [Joost van der Linden](https://www.facebook.com/3DMadMesh) for the original Advanced Prime Line


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