# Slicer G-code Reference

The following sections are from the included `GCode.txt` reference file.

> **Note: Copy-pasting directly from this page may paste as a single line in some slicers. If that happens, paste into Notepad (Windows) or TextEdit (Mac) first, then copy from there and paste into your slicer.**


---

## Change Filament G-code

```
; ===== Change Filament G-Code =====
TOOLCHANGE NEXT={next_extruder} FLUSH={flush_length} RETRACT_OLD={retraction_length[current_extruder]} RETRACT_NEW={retraction_length[next_extruder]}
; ===== End  Change Filament G-Code =====
```

---

## Layer Change G-code

```
; =====  Layer Change G-Code =====
SET_PRINT_STATS_INFO CURRENT_LAYER={layer_num + 1}
; ===== End  Layer Change =====
```

---

## Machine Start G-code

```
; ===== Machine Start G-Code =====
; START_PRINT handles: staged heating, homing, Z tilt, adaptive bed mesh, AMS init.
; Klipper's built-in adaptive mesh uses [exclude_object] data from the gcode —
; no slicer mesh coordinates needed.
START_PRINT BED_TEMP=[bed_temperature_initial_layer_single] EXTRUDER_TEMP=[nozzle_temperature_initial_layer] TOTAL_LAYER_COUNT=[total_layer_count]
; ===== End  Start =====
```

> **Slicer requirement:** In OrcaSlicer → Process → Others, ensure **"Label objects"** is enabled (it is by default). This provides the object polygon data that Klipper uses for adaptive mesh bounds.

---

## Before Layer Change G-code

```
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
