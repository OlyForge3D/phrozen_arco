"""
Static audit of every gcode_macro in the repo.

Walks every macro definition and reports:

    [W] cross-macro variable writes
        SET_GCODE_VARIABLE MACRO=X VARIABLE=Y issued from a macro that is not X.
        These create cross-coupling between macros and are easy to break in
        a refactor; they should be intentional and rare.

    [E] reads of variables that don't exist
        printer["gcode_macro X"].field where X has no variable_field defined.
        Klipper renders these as Undefined which becomes a runtime error or
        silent zero depending on the filter chain.

    [E] writes to variables that don't exist
        SET_GCODE_VARIABLE MACRO=X VARIABLE=Y where X has no variable_Y.
        Klipper accepts this and creates the variable, but it usually means
        a typo or a stale reference.

    [E] calls to macros that don't exist
        A macro body invokes FOO but no [gcode_macro FOO] is defined.
        Will fail at runtime when the body executes.

    [W] cycles in the call graph
        Macro A calls B which (transitively) calls A. Could infinite-loop.

    [I] dead macros (defined, never called, not on the firmware/user-entry
        whitelist).

The script exits 1 if any [E] is found, 0 otherwise. [W] and [I] are always
informational.

Run from the repo root:

    python3 tools/audit_macros.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Make this script runnable both as `python3 tools/audit_macros.py` and
# via `python3 -m tools.audit_macros`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.klipper_cfg import Config, load_repo_config, GcodeMacro


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# printer["gcode_macro X"].field   or   printer['gcode_macro X'].field
READ_RE = re.compile(
    r"""printer\s*\[\s*['"]gcode_macro\s+(\w+)['"]\s*\]\s*\.\s*(\w+)"""
)

# {% set local = printer["gcode_macro X"] %} — namespace alias; we can't tell
# which field the local is used for, so we treat this as "macro X is read
# from" (used for keeping read-only state containers off the dead-macro list).
NAMESPACE_BIND_RE = re.compile(
    r"""printer\s*\[\s*['"]gcode_macro\s+(\w+)['"]\s*\](?!\s*\.)"""
)

# SET_GCODE_VARIABLE MACRO=X VARIABLE=Y (VALUE=... ignored)
WRITE_RE = re.compile(
    r"""SET_GCODE_VARIABLE\s+MACRO\s*=\s*(\w+)\s+VARIABLE\s*=\s*(\w+)""",
    re.IGNORECASE,
)


# Tokens that look like a macro name when they appear at the start of a gcode
# line. We use the first whitespace-delimited token of each non-comment,
# non-blank, non-Jinja line.
MACRO_CALL_FIRST_TOKEN_RE = re.compile(r"^\s*([A-Za-z_][\w]*)\b")


# Builtin gcode commands that look like macro names but aren't. If a line
# starts with one of these, do NOT treat it as a macro call.
BUILTIN_GCODE = {
    # Standard G/M
    "G0", "G1", "G2", "G3", "G4", "G10", "G11", "G17", "G18", "G19",
    "G20", "G21", "G28", "G29", "G30", "G31", "G40", "G54", "G80",
    "G90", "G91", "G92", "G93", "G94",
    "M0", "M1", "M2", "M17", "M18", "M82", "M83", "M84", "M104", "M105",
    "M106", "M107", "M109", "M114", "M115", "M117", "M118", "M119",
    "M140", "M141", "M155", "M190", "M191", "M201", "M202", "M203",
    "M204", "M205", "M206", "M211", "M218", "M220", "M221", "M226",
    "M280", "M290", "M303", "M304", "M400", "M401", "M402", "M420",
    "M500", "M501", "M502", "M503", "M569", "M600", "M701", "M702",
    "M851", "M900", "M905", "M906", "M907", "M913", "M914", "M915",
    "M928", "M999",
    # Klipper extras
    "BED_MESH_CALIBRATE", "BED_MESH_CLEAR", "BED_MESH_PROFILE",
    "PROBE", "PROBE_ACCURACY", "PROBE_CALIBRATE", "Z_TILT_ADJUST_BASE",
    "SAVE_CONFIG", "SAVE_GCODE_STATE", "RESTORE_GCODE_STATE",
    "SET_GCODE_OFFSET", "SET_GCODE_VARIABLE", "SET_KINEMATIC_POSITION",
    "SET_VELOCITY_LIMIT", "SET_PIN", "SET_FAN_SPEED", "SET_HEATER_TEMPERATURE",
    "SET_PRESSURE_ADVANCE", "SET_TMC_CURRENT", "SET_FILAMENT_SENSOR",
    "SET_PRINT_STATS_INFO", "SET_STEPPER_ENABLE", "SDCARD_RESET_FILE",
    "ACCELEROMETER_QUERY", "ACCELEROMETER_MEASURE",
    "TEMPERATURE_WAIT", "TURN_OFF_HEATERS", "RESPOND",
    "FORCE_MOVE", "PID_CALIBRATE", "STEPPER_BUZZ",
    "RESHAPER_CALIBRATE", "TUNING_TOWER",
    # Phrozen firmware P-commands (handled by the MKS_THR firmware, not Klipper macros)
    "P0", "P1", "P2", "P3", "P28",
    # Klipper extras for our printer
    "G0.1", "G1.1", "M84.1", "M99109", "M99190", "G28.1", "G31.1", "BASE_PAUSE",
    "BASE_RESUME", "BASE_CANCEL_PRINT",
    # Slicer placeholder commands embedded in start-gcode
    "SET_PRINT_STATS_INFO",
    # Phrozen Tn (tool change) — handled by phrozen_dev plugin. Bare "T"
    # shows up when the body has T{params.NEXT} (Jinja-templated tool number).
    "T", "T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9",
    "T10", "T11", "T12", "T13", "T14", "T15",
    # KAOS Python plugin commands (phrozen_dev/extras provide these at runtime;
    # they are not [gcode_macro] entries in our config).
    "KAOS_LOG", "KAOS_LOG_LEVEL", "KAOS_LOG_FLAGS", "KAOS_LOG_LANGUAGE",
    # Klipper builtins I missed in the first pass
    "UPDATE_DELAYED_GCODE", "SET_TEMPERATURE_FAN_TARGET",
}


# Macros that are called by something OUTSIDE the macro graph: firmware
# (phrozen_dev/dev.py P-commands), the slicer's start/end/change-filament
# G-code, the user via console, or Klipper internals (homing_override,
# delayed_gcode). These are entry points and are NOT "dead" if no macro calls
# them.
EXTERNAL_ENTRY_POINTS = {
    # Firmware P-command dispatch (phrozen_dev calls these by name)
    "PG101", "PG102", "PG103", "PG104", "PG105", "PG106", "PG107", "PG108",
    "PG109", "PG110", "PG111", "PG112", "PG113", "PG114", "PG115", "PG116",
    "PG117", "PG118", "PG119",
    "PRZ_SPITTING_SCRAPE",     # has firmware translation entry
    "PRZ_PAUSE_WAITINGAREA",   # called by phrozen_dev pause-trigger flows
    "PRZ_PRINTING_START",      # called from G29 and (commented) homing_override
    "PRZ_MANUAL_WAITING",      # user-triggered manual-feed waiting
    # Slicer Change-Filament G-code entry
    "TOOLCHANGE",
    "ORCA_PURGE",
    # Slicer start G-code entries
    "PG28", "G28", "G29", "G30", "G31", "G40",
    "Z_TILT_ONCE", "Z_TILT_ADJUST", "Z_TILT_CLEAR",
    "BED_MESH_CALIBRATE_CUSTOM",
    "PRZ_WIPEMOUTH", "PRZ_WAITINGAREA",
    "TP_OUT", "TP_PUT",
    "START_PRINT", "PRINT_END", "CANCEL_PRINT",
    # Pause/Resume (Moonraker / fluidd UI)
    "PAUSE", "PAUSE_PRINTING", "PAUSEMA", "RESUME",
    # User-facing controls
    "M84", "M18", "M106", "M109", "M190", "M303", "M304",
    "G0", "G1",
    "SCREWS_TILT_CALCULATE",
    "SHAPER_CALIBRATE",
    "AUTHORIZE_POWER_LOSS_RECOVERY",
    "KAOS_SAFETY_MODE_SAFE", "KAOS_SAFETY_MODE_BULLETPROOF",
    "KAOS_LIGHTS_ON", "KAOS_LIGHTS_OFF", "KAOS_LIGHTS_TOGGLE",
    "KAOS_BEEP_NOTIFY",
    "KAOS_SET_LOG_LEVEL", "KAOS_SET_LOG_FLAGS", "KAOS_SET_LOG_LANGUAGE",
    "KAOS_TOGGLE_LOG_LEVEL",
    "KAOS_DYNAMIC_SPEED_ENABLE", "KAOS_DYNAMIC_SPEED_DISABLE",
    "DEBUG_TRUST",
    "probe_up", "probe_off",
    # KAOS_LOG is a Python-side macro provided by the phrozen_dev plugin (not
    # a [gcode_macro] in our config); the wrapper _KAOS_LOG calls it.
}


# Macros called from non-macro contexts that the analyzer would otherwise miss.
# These are calls inside [homing_override], [delayed_gcode], or fan/Z config
# blocks. We pre-seed them as "called" so they don't show as dead code.
CALLED_FROM_NON_MACRO_CONTEXT = {
    # homing_override calls these
    "_CLEAR_TRUSTED_HOME", "_CLEAR_RECOVERY_AUTH",
    "_KAOS_SAFETY_MODE_ENABLE_INTERNAL_MOTION_BYPASS",
    "_KAOS_SAFETY_MODE_DISABLE_INTERNAL_MOTION_BYPASS",
    "_SET_TRUSTED_XY", "_SET_TRUSTED_Z", "_SET_TRUSTED_XYZ",
    "PRZ_WIPEMOUTH",
    # delayed_gcode and other [...] sections
    "TURN_ON_LIGHT_AT_BOOT", "LIGHTS_OFF_DELAY",
    "_KAOS_STARTUP_LOGGING", "startup_beep",
    "apply_hold_current", "apply_board_fan_target",
    "DYNAMIC_SPEED_LOOP", "BOARD_FAN_CPU_LOOP",
    "KINEMATIC_POSITION",
    # G/M renames target the original — the renamed macro is the public name
}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def strip_comments(line: str) -> str:
    """Strip Klipper-style line/inline comments. Klipper treats # and ; as
    comment leaders both at line start and after whitespace."""
    # Outside of {% %} and { } context. Approximate: any unquoted ; or #.
    # For audit purposes, this is good enough.
    out = []
    i = 0
    in_str = None
    in_jinja = 0
    while i < len(line):
        c = line[i]
        if in_str:
            out.append(c)
            if c == in_str and (i == 0 or line[i-1] != "\\"):
                in_str = None
        elif c in "'\"":
            in_str = c
            out.append(c)
        elif c == "{" and i + 1 < len(line) and line[i+1] == "%":
            in_jinja += 1
            out.append(c)
        elif c == "%" and i + 1 < len(line) and line[i+1] == "}" and in_jinja > 0:
            in_jinja -= 1
            out.append(c)
        elif (c in ";#") and in_jinja == 0:
            # inline comment - drop the rest of the line
            break
        else:
            out.append(c)
        i += 1
    return "".join(out)


def find_calls(macro: GcodeMacro, known_macros: set[str]) -> list[tuple[int, str]]:
    """Find every macro call inside `macro`'s body.

    A line is a macro call if, after stripping leading whitespace and any
    leading Jinja blocks, its first token matches a known macro name AND that
    token is not a builtin gcode. Returns (line_number, callee_name) pairs.
    Line numbers are 1-indexed within the body.
    """
    calls: list[tuple[int, str]] = []
    for ln_idx, raw in enumerate(macro.body.splitlines(), start=1):
        line = strip_comments(raw).strip()
        if not line:
            continue
        # Skip pure Jinja control lines
        if line.startswith("{%") or line.startswith("{#") or line.startswith("{{"):
            continue
        # Skip lines that are entirely action_*() expressions
        if line.startswith("{action_") or line.startswith("{ action"):
            continue
        # Klipper conditionals like {% if ... %}content{% endif %} on one line:
        # peel off the leading {% ... %} blocks.
        while line.startswith("{%"):
            end = line.find("%}")
            if end < 0:
                break
            line = line[end+2:].lstrip()
        if not line:
            continue
        m = MACRO_CALL_FIRST_TOKEN_RE.match(line)
        if not m:
            continue
        token = m.group(1)
        if token in BUILTIN_GCODE:
            continue
        if token in known_macros:
            calls.append((ln_idx, token))
    return calls


# {% set ALIAS = printer["gcode_macro X"] %}
ALIAS_BIND_RE = re.compile(
    r"""\{\s*%\s*set\s+(\w+)\s*=\s*printer\s*\[\s*['"]gcode_macro\s+(\w+)['"]\s*\](?!\s*\.)""",
)


def find_reads(macro: GcodeMacro) -> list[tuple[int, str, str]]:
    """Return (line, target_macro, variable) tuples for every read of a
    macro's variable.

    Catches both:
      - direct: `printer["gcode_macro X"].field`
      - aliased: `{% set GEO = printer["gcode_macro X"] %}` followed later
        by `GEO.field` (we track in-macro aliases)
    """
    reads: list[tuple[int, str, str]] = []

    # First pass: build alias table for this macro
    aliases: dict[str, str] = {}  # local_name -> target_macro
    for raw in macro.body.splitlines():
        for m in ALIAS_BIND_RE.finditer(raw):
            aliases[m.group(1)] = m.group(2)

    # Second pass: find direct reads + alias reads
    for ln_idx, raw in enumerate(macro.body.splitlines(), start=1):
        for m in READ_RE.finditer(raw):
            reads.append((ln_idx, m.group(1), m.group(2)))
        # Aliased reads: <ALIAS>.<field>
        for alias, target in aliases.items():
            for m in re.finditer(r"\b" + re.escape(alias) + r"\.(\w+)", raw):
                # Skip if this is the alias-bind line itself
                if ALIAS_BIND_RE.search(raw):
                    continue
                reads.append((ln_idx, target, m.group(1)))
    return reads


def find_writes(macro: GcodeMacro) -> list[tuple[int, str, str]]:
    """Return (line, target_macro, variable) tuples for every SET_GCODE_VARIABLE."""
    writes: list[tuple[int, str, str]] = []
    for ln_idx, raw in enumerate(macro.body.splitlines(), start=1):
        line = strip_comments(raw)
        for m in WRITE_RE.finditer(line):
            writes.append((ln_idx, m.group(1), m.group(2)))
    return writes


def find_cycles(call_graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan-style DFS to find cycles in the call graph.

    Returns a list of cycles, each as a sequence of macro names.
    """
    cycles: list[list[str]] = []
    visited: set[str] = set()

    def dfs(node: str, stack: list[str], on_stack: set[str]) -> None:
        if node in on_stack:
            # Found cycle: trim stack back to the recurrence
            idx = stack.index(node)
            cycles.append(stack[idx:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        on_stack.add(node)
        stack.append(node)
        for nxt in call_graph.get(node, set()):
            dfs(nxt, stack, on_stack)
        stack.pop()
        on_stack.discard(node)

    for n in list(call_graph.keys()):
        if n not in visited:
            dfs(n, [], set())
    return cycles


def find_calls_in_text(text: str, known_macros: set[str]) -> set[str]:
    """Find all macro calls inside an arbitrary multi-line string (used for
    [homing_override] and [delayed_gcode] bodies)."""
    found: set[str] = set()
    for raw in text.splitlines():
        line = strip_comments(raw).strip()
        if not line or line.startswith("{%") or line.startswith("{action_"):
            continue
        while line.startswith("{%"):
            end = line.find("%}")
            if end < 0:
                break
            line = line[end+2:].lstrip()
        if not line:
            continue
        m = MACRO_CALL_FIRST_TOKEN_RE.match(line)
        if not m:
            continue
        token = m.group(1)
        if token in BUILTIN_GCODE:
            continue
        if token in known_macros:
            found.add(token)
    return found


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

def is_state_container(macro: GcodeMacro) -> bool:
    """A "state container" macro exists primarily to hold variables for other
    macros to read/write. Its `gcode:` body has no motion or extruder commands;
    it may have logging or be entirely empty.

    Cross-macro writes targeting state containers are intentional (callers
    update shared state) and should be demoted from [W] coupling warnings to
    [I] informational.
    """
    if not macro.variables:
        return False  # no variables = not a container
    body = macro.body
    # Strip comments and Jinja blocks for this heuristic
    cleaned = re.sub(r"\{[%#].*?[%#]\}", "", body, flags=re.DOTALL)
    cleaned = re.sub(r"\{action_respond_info\([^}]*\)\}", "", cleaned)
    cleaned = re.sub(r"\{[^}]*\}", "", cleaned)  # remove any remaining {jinja}
    for raw in cleaned.splitlines():
        line = strip_comments(raw).strip()
        if not line:
            continue
        # Any G or M command, or any uppercase command word, makes this not a
        # pure state container. KAOS_LOG and respond_info-only is OK.
        if re.match(r"^[GMT]\d", line):
            return False
        m = MACRO_CALL_FIRST_TOKEN_RE.match(line)
        if not m:
            continue
        tok = m.group(1)
        # Logging / diagnostic commands don't count as "real" macro work for
        # the purpose of state-container classification. KAOS_LOG was the
        # original public name; _KAOS_LOG is the renamed-to-internal form.
        if tok in {"KAOS_LOG", "_KAOS_LOG", "RESPOND"}:
            continue
        # Any other uppercase command word → not a state container
        if tok.isupper() or tok[0].isupper():
            return False
    return True


def audit(cfg: Config, verbose: bool = False) -> int:
    macros = cfg.macros
    macro_names = set(macros.keys())

    # Klipper's `rename_existing:` field renames the existing macro to the
    # given new name, so the new name should count as a known macro for the
    # purpose of detecting "unknown command" calls.
    for m in macros.values():
        if m.rename_existing:
            macro_names.add(m.rename_existing)

    state_containers: set[str] = {
        n for n, m in macros.items() if is_state_container(m)
    }

    # Build call graph (macro -> set of macros it calls)
    call_graph: dict[str, set[str]] = {n: set() for n in macro_names}
    for name, m in macros.items():
        for _, callee in find_calls(m, macro_names):
            if callee != name:
                call_graph[name].add(callee)

    # Also seed from non-macro contexts: homing_override, delayed_gcode bodies
    seeded_callees: set[str] = set(CALLED_FROM_NON_MACRO_CONTEXT)
    for s in cfg.sections:
        if s.kind == "homing_override":
            # Klipper config homing_override has the gcode in a different
            # field; we don't parse those bodies the same way. Use seeded set.
            pass
    for d in cfg.delayed.values():
        seeded_callees |= find_calls_in_text(d.body, macro_names)

    # Build error/warning lists ----------------------------------------------
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    # --- E: unknown variable reads ---
    for name, m in macros.items():
        for ln, tgt, var in find_reads(m):
            if tgt not in macros:
                errors.append(
                    f"  [E] {m.file}:{m.body_start_line + ln - 1} {name} reads "
                    f'printer["gcode_macro {tgt}"].{var} but macro {tgt} is not defined'
                )
                continue
            tgt_macro = macros[tgt]
            if f"variable_{var}" not in tgt_macro.variables:
                # Don't flag well-known special variables Klipper provides
                # (none for gcode_macro — they're all user-declared).
                errors.append(
                    f"  [E] {m.file}:{m.body_start_line + ln - 1} {name} reads "
                    f'printer["gcode_macro {tgt}"].{var} but {tgt} has no variable_{var}'
                )

    # --- E/W: writes ---
    for name, m in macros.items():
        for ln, tgt, var in find_writes(m):
            if tgt not in macros:
                errors.append(
                    f"  [E] {m.file}:{m.body_start_line + ln - 1} {name} writes "
                    f"SET_GCODE_VARIABLE MACRO={tgt} VARIABLE={var} but macro {tgt} is not defined"
                )
                continue
            tgt_macro = macros[tgt]
            if f"variable_{var}" not in tgt_macro.variables:
                errors.append(
                    f"  [E] {m.file}:{m.body_start_line + ln - 1} {name} writes "
                    f"SET_GCODE_VARIABLE MACRO={tgt} VARIABLE={var} but {tgt} has no variable_{var}"
                )
            if tgt != name:
                if tgt in state_containers:
                    info.append(
                        f"  [I] {m.file}:{m.body_start_line + ln - 1} {name} writes "
                        f"{tgt}.{var} (state container — intentional)"
                    )
                else:
                    warnings.append(
                        f"  [W] {m.file}:{m.body_start_line + ln - 1} {name} writes "
                        f"SET_GCODE_VARIABLE MACRO={tgt} VARIABLE={var} (cross-macro write — coupling)"
                    )

    # --- E: calls to unknown macros ---
    # (Already filtered in find_calls because we only return calls to
    # known_macros; unknown tokens that aren't builtins remain a concern but
    # could be Klipper extras we don't have in the BUILTIN_GCODE list.)
    # Re-scan looking for unknown first-tokens explicitly.
    for name, m in macros.items():
        for ln_idx, raw in enumerate(m.body.splitlines(), start=1):
            line = strip_comments(raw).strip()
            if not line or line.startswith("{%") or line.startswith("{action_"):
                continue
            while line.startswith("{%"):
                end = line.find("%}")
                if end < 0:
                    break
                line = line[end+2:].lstrip()
            if not line or line.startswith("#"):
                continue
            tm = MACRO_CALL_FIRST_TOKEN_RE.match(line)
            if not tm:
                continue
            tok = tm.group(1)
            if tok in BUILTIN_GCODE or tok in macro_names:
                continue
            # Unknown first token. This could be a built-in we missed or a real bug.
            warnings.append(
                f"  [W] {m.file}:{m.body_start_line + ln_idx - 1} {name} invokes "
                f"unknown command '{tok}' (may be Klipper builtin not in the audit table; verify)"
            )

    # --- W: cycles ---
    for cyc in find_cycles(call_graph):
        if len(cyc) > 1:
            warnings.append(f"  [W] cycle in call graph: {' -> '.join(cyc)}")

    # --- I: dead macros ---
    called: set[str] = set()
    for callees in call_graph.values():
        called |= callees
    called |= seeded_callees
    called |= EXTERNAL_ENTRY_POINTS
    # rename_existing targets are not "called by name" but they ARE the original
    # behaviour of the renamed macro — never report them as dead.
    rename_targets = {m.rename_existing for m in macros.values() if m.rename_existing}
    called |= rename_targets

    # State containers (and any other macro) are also "alive" if their
    # variables are read (printer["gcode_macro X"].field) OR if their
    # namespace is bound to a local Jinja variable for later access
    # (printer["gcode_macro X"] without .field) anywhere.
    read_targets: set[str] = set()
    for m in macros.values():
        for _, tgt, _ in find_reads(m):
            read_targets.add(tgt)
        for raw in m.body.splitlines():
            for nm in NAMESPACE_BIND_RE.findall(raw):
                read_targets.add(nm)
    for d in cfg.delayed.values():
        for raw in d.body.splitlines():
            for nm in NAMESPACE_BIND_RE.findall(raw):
                read_targets.add(nm)
            for m in READ_RE.finditer(raw):
                read_targets.add(m.group(1))

    for name in macros.keys():  # iterate the real macros only
        if name in called:
            continue
        if name in read_targets:
            continue  # state container or just read-only — alive via reads
        info.append(f"  [I] dead macro: {name} ({macros[name].file})")

    # --- W: missing description on public-ish macros ---
    for name, m in macros.items():
        if name.startswith("_"):
            continue  # internal helpers don't strictly need descriptions
        if not m.description:
            warnings.append(f"  [W] {m.file} {name} has no description: line")

    # --- Print report ---
    print(f"Macros analyzed: {len(macros)}  Sections: {len(cfg.sections)}  Delayed gcodes: {len(cfg.delayed)}")
    print(f"Errors: {len(errors)}  Warnings: {len(warnings)}  Info: {len(info)}")

    # Errors are always shown (they block ship).
    if errors:
        print()
        print("=== ERRORS (block ship) ===")
        for e in errors:
            print(e)

    # Warnings and info are only shown with --verbose. They are noisy because
    # they include things like "macro X has no description:" which is doc
    # debt rather than a bug.
    if verbose:
        if warnings:
            print()
            print("=== WARNINGS ===")
            for w in warnings:
                print(w)
        if info:
            print()
            print("=== INFO ===")
            for i in info:
                print(i)
    elif warnings or info:
        print(f"(re-run with --verbose to see warnings and info)")

    return 1 if errors else 0


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Static audit of every gcode_macro in config/.")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Show all warnings and info; default is errors-only.")
    args = p.parse_args()

    cfg = load_repo_config(".")
    sys.exit(audit(cfg, verbose=args.verbose))
