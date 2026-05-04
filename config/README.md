# THIS MUST BE UPDATED

# Phrozen Arco – Klipper Add-On System (KAOS)
## Simple Setup & Quick Start Guide

This package adds smarter macros and safer behavior to the Phrozen Arco Klipper setup, including:

- Cleaner tool changes
- Optional Z-Tilt on first print
- Improved homing and nozzle wiping
- Optional dynamic speed control
- Simple user configuration

This is written for users who are **new to Klipper and 3D printing**.  
You only need to edit **one config file** and your slicer G-code.

### Jump to
- [Disclaimer](#disclaimer)
- [Credits](#thankscredits)

---

## What You Will Edit

You will only edit:

- `printer.cfg` (minimal changes)
- `kaos.cfg` (user settings)
- Your slicer **G-code**

You will NOT edit other stock Phrozen files.

---

## Step 1 — Upload the Reduced Includes Files

Copy these files to your printer:


- `kaos.cfg`
- `magic_ams_by_chris.cfg`


⚠️ Do NOT overwrite your existing `printer.cfg`.

---

## Step 2 — Add Includes to `printer.cfg`

Open:

- `printer.cfg`

Near the top of the file find these lines:

```ini
[include printer_MCU.cfg]
[include printer_gcode_macro.cfg]
```
Immediately after it, add:
```ini
[include kaos.cfg]

```

It should now look like this:
```ini
[include printer_MCU.cfg]
[include printer_gcode_macro.cfg]
[include kaos.cfg]
```

While printer.cfg is open, also comment out this section:
```ini
[output_pin board_fan]
pin: PA2
value: 1
```
So it becomes:
```ini
;[output_pin board_fan]
;pin: PA2
;value: 1
```
Save and restart Klipper.

---
## Step 3 — Set Your User Options

Open:

- `kaos.cfg`

Find this section near the top:

- `[gcode_macro _USER_CONFIG]`

This is the **only section most users should change.**

Here you can turn features on and off and set variables to control how some of the features work. The variable have been set to tested, safe (hopefully) values. See the kaos.cfg file for details of the values.

After making any changes tovalues in the `[gcode_macro _USER_CONFIG]`, save the file and **restart Klipper**.

---

## Step 4 — Update Your Slicer Start G-code

In your slicer (OrcaSlicer / PrusaSlicer / Bambu Studio):

If you are comfortable modifying your own Start G-Code,please do so. Otherwise, below is a working code that takes advantage of all of the features of this addon.

Replace your **Start G-code** with:

```gcode
; ===== Phrozen Arco Machine Start G-Code =====
; ====================================
; machine start g-code with adaptive bed mesh (explicit profile management)
M107 ; turn off part cooling fan
G90 ; absolute positioning

M140 S[first_layer_bed_temperature] ; set bed to final temperature
M104 S140 ; set hotend to probing temperature
M190 S[first_layer_bed_temperature] ; wait for bed to reach final temperature
M109 S140 ; wait for hotend to reach probing temperature

PG28 ; home all axes
Z_TILT_ONCE ; run tramming once per session
PRZ_WIPEMOUTH ; wipe nozzle
BED_MESH_CLEAR ; clear any active mesh profile first

BED_MESH_CALIBRATE_CUSTOM MESH_MIN_X={adaptive_bed_mesh_min[0]} MESH_MIN_Y={adaptive_bed_mesh_min[1]} MESH_MAX_X={adaptive_bed_mesh_max[0]} MESH_MAX_Y={adaptive_bed_mesh_max[1]}

TP_OUT ; disable PG28/G30/G31 to prevent mid-print homing
PRZ_WAITINGAREA ; move to waiting area

G21 ; set units to millimeters
M83 ; extruder relative mode

M109 S{first_layer_temperature[0]} ; heat to final printing temperature
P0 M1
P28
P2 A1
; ====================================
SET_PRINT_STATS_INFO TOTAL_LAYER=[total_layer_count]

; ===== End  Start =====
```

## Step 5 — Optional: AMS / Multi-Material

If you do not use AMS / multi-material, comment this section out with a `;`  like:

`; [include magic_ams_by_chris.cfg]`

If you use AMS / multi-material:

- Make sure this file is uploaded:
  - `magic_ams_by_chris.cfg`
- Make sure it is included in kaos.cfg (it is by default):
  - `[include magic_ams_by_chris.cfg]`

- Save `kaos.cfg`
- Restart Klipper


Copy the following single line to the 'Change Filament G-Code' section of your Machine G-code:

```gcode
TOOLCHANGE NEXT={next_extruder} FLUSH={flush_length} RETRACT_OLD={retraction_length[current_extruder]} RETRACT_NEW={retraction_length[next_extruder]}
```

That one line replaces the old multi-line block. Orca will then automatically emit its own `T<n>` (the actual tool change) immediately after, which the firmware uses to drive the cut + load + prime cycle.

How a tool change actually plays out on hardware:

1. **Slicer fires our `TOOLCHANGE`** — lifts Z 3mm (skipped near the Z safety ceiling), retracts the old filament by `RETRACT_OLD`, stashes the slicer's `FLUSH` and `RETRACT_NEW` for later, lowers Z. **No `T<n>` and no `ORCA_PURGE` here yet.**
2. **Slicer fires its own `T<n>`** — the firmware takes over: depressurize, travel to cutter, **CUT**, load new filament, prime 55mm of new color at the chute (firmware-fired PG101 → PG106 → PG110 → PG113 → `_SPITTING_FRAME`).
3. **`PRZ_SPITTING_END`** (the tail of the firmware's prime sequence) sees the pending stash from step 1 and runs **`ORCA_PURGE`** — color flush (slicer's `FLUSH` value) + cool kicks + wipe across the brush + temp/fan restore. The wipe lands on the new color, after the prime, just before the print resumes.

This split exists because Orca always emits its own `T<n>` after the change-filament-gcode block — there's no slicer setting that suppresses it. Letting the firmware's `T<n>` drive the cut keeps cuts to exactly one per change, and deferring `ORCA_PURGE` to `PRZ_SPITTING_END` keeps the flush + wipe ordered correctly relative to the cut. The Z lift/lower is symmetric inside `TOOLCHANGE`, so it can never desync.

## Step 6 — First Test Print

After setup:

- Restart Klipper
- Run a small single-color test print
- Watch:
  - homing behavior
  - nozzle wipe
  - bed probing
  - first layer adhesion

Do not run long or multi-color prints until this works correctly.

---

## What NOT To Edit

Unless you know whaty you are doing, do NOT edit:

- `magic_ams_by_chris.cfg`
- Stock Phrozen macros
- Stock `printer.cfg` logic (other than adding the `[include ...]` and [output_pin board_fan] lines)

Only edit:

- `kaos.cfg`
- Your slicer **Start G-code**

---

# Optional Advanced Prime Line
This will give you a compact L shaped prime line on your first layer. It is tied to the corner of your print to minimize oozing and reduce space required for adaptive probing. There are two versions. A small "L" and larger, multi line "L". Only add one of the two.

## Advanced Prime Line (Compact) 

Copy the following code to the `Before Layer Change G-Code` section of your Machine Gcode

```gcode
;Advance Prime Line
{if layer_num == 0} ;Only prime on first layer
G0 X{max((min(print_bed_max[0] - 12, first_layer_print_min[0] + 80) - 82.5), 0)} Y{max((min(print_bed_max[1] - 3, first_layer_print_min[1] + 80) - 82.5), 0) + 21.25} Z5 F6000
G0 Z[first_layer_height] F600
G1 E3 F1800
G1 Y{max((min(print_bed_max[1] - 3, first_layer_print_min[1] + 80) - 82.5), 0)} E{21.25 * 0.5 * first_layer_height * nozzle_diameter[0]} F3000
G1 X{max((min(print_bed_max[0] - 12, first_layer_print_min[0] + 80) - 82.5), 0) + 21.25} E{21.25 * 0.5 * first_layer_height * nozzle_diameter[0]} F3000
G1 Z1 F600
{endif}
;##### END OF Advanced Prime Line #######
```


## Advanced Prime Line (Large) 
Copy the following code to the `Before Layer Change G-Code` section of your Machine Gcode

```gcode
;Advance Prime Line
{if layer_num == 0}
G0 X{max((min(print_bed_max[0] - 12, first_layer_print_min[0] + 80) - 85), 0)} Y{max((min(print_bed_max[1] - 3, first_layer_print_min[1] + 80) - 85), 0)} Z5 F6000
G0 Z[first_layer_height] F600
G1 E3 F1800
G1 X{(min(print_bed_max[0] - 12, first_layer_print_min[0] + 80))} E{85 * 0.5 * first_layer_height * nozzle_diameter[0]} F3000
G1 Y{max((min(print_bed_max[1] - 3, first_layer_print_min[1] + 80) - 85), 0) + 2} E{2 * 0.5 * first_layer_height * nozzle_diameter[0]} F3000
G1 X{max((min(print_bed_max[0] - 12, first_layer_print_min[0] + 80) - 85), 0)} E{85 * 0.5 * first_layer_height * nozzle_diameter[0]} F3000
G1 Y{max((min(print_bed_max[1] - 3, first_layer_print_min[1] + 80) - 85), 0) + 85} E{83 * 0.5 * first_layer_height * nozzle_diameter[0]} F3000
G1 X{max((min(print_bed_max[0] - 12, first_layer_print_min[0] + 80) - 85), 0) + 2} E{2 * 0.5 * first_layer_height * nozzle_diameter[0]} F3000
G1 Y{max((min(print_bed_max[1] - 3, first_layer_print_min[1] + 80) - 85), 0) + 3} E{82 * 0.5 * first_layer_height * nozzle_diameter[0]} F3000
G1 X{max((min(print_bed_max[0] - 12, first_layer_print_min[0] + 80) - 85), 0) + 3} Z0
G1 X{max((min(print_bed_max[0] - 12, first_layer_print_min[0] + 80) - 85), 0) + 6}
G1 Z1 F600
{endif}
;##### END OF Advanced Prime Line #######
```


## Common Issues


## Thanks/Credits
- Thanks to [solutionphil](https://github.com/solutionphil) for starting the original project [here](https://github.com/solutionphil/PhrozenArco):
- Thanks to  thanks to [Jay Smith](https://www.facebook.com/jay.smith.122210/) and [Edwin Tan](https://www.facebook.com/ejtan1) for the lighting macros
- Thanks to [Joost van der Linden](https://www.facebook.com/3DMadMesh) for the original Advanced Prime Line

## Disclaimer

This configuration modifies stock Phrozen Arco Klipper behavior.

- These settings have been tested on our own machines
- Your printer, hardware, and setup may differ
- Results may vary (YMMV)
- Use at your own risk
- No warranty is provided

Always keep a backup of your working configuration before making changes.
