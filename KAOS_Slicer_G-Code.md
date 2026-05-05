# Slicer G-code Reference

The following sections are from the included `GCode.txt` reference file.

---

## Change Filament G-code

```gcode
; ===== Change Filament G-Code =====
TOOLCHANGE NEXT={next_extruder} FLUSH={flush_length} RETRACT_OLD={retraction_length[current_extruder]} RETRACT_NEW={retraction_length[next_extruder]}
; ===== End  Change Filament G-Code =====
```

---

## Layer Change G-code

```gcode
; =====  Layer Change G-Code =====
SET_PRINT_STATS_INFO CURRENT_LAYER={layer_num + 1}
; ===== End  Layer Change =====
```

---

## Machine Start G-code

```gcode
; ===== Machine Start G-Code =====
; ====================================
; machine start g-code with adaptive bed mesh (explicit profile management)
M118 Starting print...
M107 ; turn off part cooling fan
G90 ; absolute positioning

M140 S[first_layer_bed_temperature] ; set bed to final temperature
M104 S140 ; set hotend to probing temperature
M190 S[first_layer_bed_temperature] ; wait for bed to reach final temperature
M109 S140 ; wait for hotend to reach probing temperature

PG28 ; home all axes

Z_TILT_ONCE ; run tramming once per session
PRZ_WIPEMOUTH ; wipe nozzle
M106 S255 ; turn on part cooling fan for probing
BED_MESH_CLEAR ; clear any active mesh profile first

BED_MESH_CALIBRATE_CUSTOM MESH_MIN_X={adaptive_bed_mesh_min[0]} MESH_MIN_Y={adaptive_bed_mesh_min[1]} MESH_MAX_X={adaptive_bed_mesh_max[0]} MESH_MAX_Y={adaptive_bed_mesh_max[1]}

TP_OUT ; disable PG28/G30/G31 to prevent mid-print homing
PRZ_WAITINGAREA ; move to waiting area
M106 S0 ; turn off part cooling fan
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

---

## Before Layer Change G-code

```gcode
; ===== BEFORE_LAYER_CHANGE G-Code =====
;Optional Advance Prime Line
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
