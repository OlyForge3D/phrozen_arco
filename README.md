# This is A dev PROJECT
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