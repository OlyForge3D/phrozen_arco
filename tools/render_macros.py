"""
Render Klipper gcode_macros to a flat sequence of commands.

Goal: for a given (Config, entry_macro_name, params, initial_state), emit
the exact sequence of G/M/T commands that Klipper would queue when the entry
macro is invoked.

Approach (matches Klipper's actual semantics):

  1. Render the entry macro's body once through Jinja2, with state-at-entry.
     This produces a flat string of g-code lines.

  2. Walk the rendered lines:
     - Strip comments and blanks.
     - {action_*(...)} expressions are diagnostic; we keep them as no-ops in
       the trace (filterable when diffing).
     - SET_GCODE_VARIABLE MACRO=X VARIABLE=Y VALUE=Z mutates our State (so
       subsequent sub-macro renders see the new value), and is recorded.
     - If a line's first token matches another defined macro, recursively
       render that macro with the line's params and state-now, and splice
       the result inline.
     - Anything else is a leaf gcode (G1, M104, T1, RESPOND, ...) and is
       emitted to the trace verbatim.

This intentionally does NOT simulate motion (we don't update toolhead
position when a G1 fires) — that's not what Klipper does at queue time
either, since the entire macro body is rendered to a string with Jinja
evaluations frozen at invocation time. State only mutates via Jinja side
effects (SET_GCODE_VARIABLE).

The output is suitable for byte-for-byte diffing between branches.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined, ChainableUndefined, UndefinedError

# Make this script runnable both as `python3 tools/render_macros.py` and via
# `python3 -m tools.render_macros`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.klipper_cfg import Config, GcodeMacro


# ---------------------------------------------------------------------------
# Jinja-friendly state wrapper
# ---------------------------------------------------------------------------

class Box:
    """Recursive dict <-> attribute/item wrapper.

    Klipper templates do `printer.toolhead.position.x` (attribute access) AND
    `printer["gcode_macro X"].variable_name` (item access then attribute). One
    wrapper that supports both, falling back to the underlying dict.
    """
    __slots__ = ("_data",)

    def __init__(self, data: dict | Any):
        self._data = data if isinstance(data, dict) else {}

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._data:
            raise AttributeError(f"Box has no attribute '{name}' (keys: {list(self._data)})")
        v = self._data[name]
        return Box(v) if isinstance(v, dict) else v

    def __getitem__(self, key: str):
        if key not in self._data:
            raise KeyError(f"Box has no key '{key}' (keys: {list(self._data)})")
        v = self._data[key]
        return Box(v) if isinstance(v, dict) else v

    def __setitem__(self, key: str, value: Any):
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        return f"Box({self._data!r})"


# ---------------------------------------------------------------------------
# State / scenario
# ---------------------------------------------------------------------------

def default_state(
    *,
    pos_x: float = 100.0,
    pos_y: float = 100.0,
    pos_z: float = 50.0,
    extruder_temp: float = 220.0,
    extruder_target: float = 220.0,
    cooling_fan_speed: float = 0.5,
    assist_fan_value: float = 0.5,
    fan_assist_value: float | None = None,  # legacy alias kept for older scenario JSONs
    max_velocity: float = 1000.0,
    max_accel: float = 40000.0,
    max_accel_to_decel: float = 10000.0,
    z_position_max: float = 303.0,
    x_position_max: float = 330.0,
    y_position_max: float = 330.0,
) -> dict:
    if fan_assist_value is not None:
        assist_fan_value = fan_assist_value
    """Build a fresh state dict that mirrors the structure Klipper exposes
    via the `printer` global in macro Jinja templates.

    All values default to the actual printer.cfg numbers but are overridable
    per scenario.
    """
    return {
        "toolhead": {
            "position": {"x": pos_x, "y": pos_y, "z": pos_z},
            "max_velocity": max_velocity,
            "max_accel": max_accel,
            "max_accel_to_decel": max_accel_to_decel,
            "axis_maximum": {"x": x_position_max, "y": y_position_max, "z": z_position_max},
            "extruder": "extruder",
        },
        "gcode_move": {
            "position": {"x": pos_x, "y": pos_y, "z": pos_z},
            "speed": 600.0,
        },
        "extruder": {
            "temperature": extruder_temp,
            "target": extruder_target,
        },
        "fan_generic cooling_fan": {"speed": cooling_fan_speed},
        "fan_generic Chamber_fan": {"speed": 0.0},
        "output_pin fan_assist": {"value": assist_fan_value},
        "configfile": {
            "settings": {
                "stepper_x": {"position_max": x_position_max, "position_min": -10},
                "stepper_y": {"position_max": y_position_max, "position_min": -10},
                "stepper_z": {"position_max": z_position_max, "position_min": -5.0},
                "extruder": {"max_temp": 350, "min_extrude_temp": 170},
                "printer": {"max_velocity": max_velocity, "max_accel": max_accel},
            }
        },
        "print_stats": {"state": "printing"},
        # Each gcode_macro X gets a sub-dict at state["gcode_macro X"] that
        # mirrors Klipper's `printer["gcode_macro X"]` namespace.
    }


def seed_macro_variables(state: dict, cfg: Config) -> None:
    """For every defined gcode_macro, install its `variable_*` defaults under
    state["gcode_macro NAME"]."""
    for name, m in cfg.macros.items():
        ns = state.setdefault(f"gcode_macro {name}", {})
        for key, raw in m.variables.items():
            if not key.startswith("variable_"):
                continue
            varname = key[len("variable_"):]
            ns[varname] = _coerce_value(raw)


def _coerce_value(raw: str) -> Any:
    """Best-effort coerce a raw Klipper variable value to a Python type."""
    s = raw.strip()
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


# ---------------------------------------------------------------------------
# Jinja env & rendering
# ---------------------------------------------------------------------------

def _make_env() -> Environment:
    """Build a Jinja2 environment that matches Klipper's template syntax.

    Klipper configures Jinja with single-brace variable delimiters:
        variable_start_string = '{'
        variable_end_string   = '}'
    Statements remain `{% ... %}` and comments `{# ... #}`.

    With this configuration, `{ action_raise_error("...") }` is a normal Jinja
    expression that calls a Python function. We register no-op stand-ins for
    Klipper's `action_*` builtins so the templates compile and run without
    triggering side effects.
    """
    env = Environment(
        variable_start_string="{",
        variable_end_string="}",
        block_start_string="{%",
        block_end_string="%}",
        comment_start_string="{#",
        comment_end_string="#}",
        # StrictUndefined: any access to a missing attribute or variable
        # raises UndefinedError. We catch these in render_macro() and surface
        # them as errors. This is critical for static verification — a typo
        # like `GEO.chute_xx` would otherwise render as empty string and
        # produce a `G1 X Y322` line that compares "equal" to baseline only
        # because both are equally garbled.
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
        autoescape=False,
    )

    # Klipper builtins: in production these have side effects (logging,
    # raising errors, calling Python remote methods). For static rendering
    # we make them no-ops that return empty strings so they render as blanks.
    def _noop(*a, **kw):
        return ""

    env.globals.update({
        "action_respond_info": _noop,
        "action_raise_error": _noop,
        "action_emergency_stop": _noop,
        "action_call_remote_method": _noop,
    })
    return env


def _normalize_template(body: str) -> str:
    """Strip Klipper-style comments before Jinja parses the body.

    Klipper's gcode_macro pre-processes comment lines (lines whose first
    non-whitespace character is `#` or `;`) before invoking Jinja. This
    matters because comment text frequently mentions `{% if %}` / `{% set %}`
    examples that would otherwise look like real Jinja statements to the
    parser and cause "unmatched endif" errors.

    Inline comments after a command (e.g. `G1 X10 ; move`) are NOT stripped
    here because the line might contain a Jinja expression earlier; we
    handle inline comments per-line during trace walking instead.
    """
    out = []
    for line in body.splitlines():
        s = line.lstrip()
        if s.startswith("#") or s.startswith(";"):
            continue
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Recursive macro expansion
# ---------------------------------------------------------------------------

# Builtin commands to NOT recursively expand (re-import the audit's table)
from tools.audit_macros import BUILTIN_GCODE  # noqa: E402

# Match SET_GCODE_VARIABLE for state mutation
SET_VAR_RE = re.compile(
    r"^\s*SET_GCODE_VARIABLE\s+MACRO\s*=\s*(\w+)\s+VARIABLE\s*=\s*(\w+)\s+VALUE\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)

# Match the first token of a line (potential macro call)
FIRST_TOKEN_RE = re.compile(r"^\s*([A-Za-z_][\w\.]*)\b")


def parse_call_params(line: str) -> dict:
    """Parse a macro/gcode invocation's parameter list.

    Supports both styles Klipper accepts:

      KEY=value KEY=value      (Klipper macro convention; values may be
                                 quoted with "..." or '...')
      Lvalue Lvalue            (Marlin style: single uppercase letter
                                 followed immediately by a numeric value,
                                 e.g. `M106 S255 P0`, `G1 X100 Y50 F600`)

    Returns a dict of param-name -> string value.
    """
    parts = line.split(None, 1)
    if len(parts) < 2:
        return {}
    rest = parts[1].strip()
    out: dict[str, str] = {}

    # First, find KEY=value pairs (also handle KEY="value with spaces")
    consumed_spans: list[tuple[int, int]] = []
    for m in re.finditer(
        r'(\w+)\s*=\s*("([^"]*)"|\'([^\']*)\'|(\S+))',
        rest,
    ):
        key = m.group(1)
        val = m.group(3) if m.group(3) is not None else (m.group(4) if m.group(4) is not None else m.group(5))
        out[key] = val
        consumed_spans.append((m.start(), m.end()))

    # Then, find Marlin-style L<digits> tokens in the un-consumed regions
    def in_consumed(pos: int) -> bool:
        return any(s <= pos < e for s, e in consumed_spans)

    for m in re.finditer(r"(?<![\w.])([A-Za-z])(-?\d+(?:\.\d+)?)", rest):
        if in_consumed(m.start()):
            continue
        out.setdefault(m.group(1).upper(), m.group(2))

    return out


@dataclass
class Trace:
    """Captured trace of rendering a single macro entry-point.

    .lines is the flat sequence of commands emitted. Each entry is the
    stripped command string (no trailing whitespace, comments removed).

    .errors is any rendering errors encountered (Jinja undefined, missing
    macros, etc.).
    """
    lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    call_stack: list[str] = field(default_factory=list)


MAX_DEPTH = 16  # recursion guard


def render_macro(
    cfg: Config,
    name: str,
    params: dict | None = None,
    state: dict | None = None,
    *,
    trace: Trace | None = None,
    depth: int = 0,
    include_action: bool = False,
) -> Trace:
    """Render the macro `name` into `trace`.lines, recursively expanding sub-
    macro calls and mutating `state` on SET_GCODE_VARIABLE.

    Returns the trace (same object passed in, or a fresh one).
    """
    if trace is None:
        trace = Trace()
    if state is None:
        state = default_state()
        seed_macro_variables(state, cfg)

    if depth > MAX_DEPTH:
        trace.errors.append(f"recursion overflow at {' -> '.join(trace.call_stack)} -> {name}")
        return trace

    if name not in cfg.macros:
        trace.errors.append(f"unknown macro: {name}")
        return trace

    macro = cfg.macros[name]
    trace.call_stack.append(name)
    try:
        # 1. Render template
        env = _make_env()
        try:
            template = env.from_string(_normalize_template(macro.body))
        except Exception as e:
            trace.errors.append(f"template parse error in {name}: {e}")
            return trace

        params = params or {}
        # Klipper exposes params with original-case keys. Slicer commonly
        # passes keys uppercase, but Klipper preserves whatever case the
        # caller sent. For our rendering, both `params.NEXT` and lowercase
        # access need to work.
        param_box = Box(dict(params))
        rawparams = " ".join(f"{k}={v}" for k, v in params.items())
        try:
            rendered = template.render(
                printer=Box(state),
                params=param_box,
                rawparams=rawparams,
            )
        except UndefinedError as e:
            trace.errors.append(f"undefined in {name}: {e.message}")
            return trace
        except Exception as e:
            trace.errors.append(f"render error in {name}: {type(e).__name__}: {e}")
            return trace

        # 2. Walk lines
        for raw in rendered.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            # An entirely empty rendered line we can skip.

            # 2a. SET_GCODE_VARIABLE — mutate state, then emit
            mvar = SET_VAR_RE.match(line)
            if mvar:
                tgt, var, val = mvar.group(1), mvar.group(2), mvar.group(3).strip()
                ns_key = f"gcode_macro {tgt}"
                if ns_key not in state:
                    state[ns_key] = {}
                state[ns_key][var] = _coerce_value(val)
                trace.lines.append(line)
                continue

            # 2b. Macro call?
            mtok = FIRST_TOKEN_RE.match(line)
            if mtok:
                tok = mtok.group(1)
                if tok in cfg.macros and tok != name:
                    sub_macro = cfg.macros[tok]
                    # rename_existing wrappers (e.g. G1, M106, M84, M109, M190)
                    # are transparent: in production the wrapper does some
                    # bookkeeping then calls the renamed original. For trace
                    # equivalence we emit the original line verbatim and skip
                    # the wrapper expansion. This keeps the trace at the
                    # gcode-command level and avoids inflating it with the
                    # wrappers' internal `G1.1 {rawparams}` boilerplate.
                    if sub_macro.rename_existing:
                        trace.lines.append(line)
                        continue
                    sub_params = parse_call_params(line)
                    # Mark the call site for diff readability
                    trace.lines.append(f"--> {tok}" + (" " + " ".join(f"{k}={v}" for k, v in sub_params.items()) if sub_params else ""))
                    render_macro(
                        cfg, tok, sub_params, state,
                        trace=trace, depth=depth + 1, include_action=include_action,
                    )
                    trace.lines.append(f"<-- {tok}")
                    continue
                # Klipper builtins / unknown commands — pass through
                trace.lines.append(line)
                continue

            # 2c. Unrecognized line shape (pure Jinja expression that didn't
            # produce a g-code-looking output) — keep for debugging
            trace.lines.append(line)

    finally:
        trace.call_stack.pop()

    return trace


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli(argv: list[str]) -> int:
    import argparse, json
    p = argparse.ArgumentParser(description="Render a Klipper gcode_macro to a flat trace.")
    p.add_argument("macro", help="entry-point macro name (e.g. TOOLCHANGE)")
    p.add_argument("--params", default="{}", help="JSON dict of macro params (e.g. '{\"NEXT\":1,\"FLUSH\":50}')")
    p.add_argument("--state", default=None, help="Path to JSON file overriding default state values")
    p.add_argument("--repo", default=".", help="Repo root (default: cwd)")
    p.add_argument("--revision", default=None, help="git revision to load config from (default: working tree)")
    args = p.parse_args(argv)

    from tools.klipper_cfg import load_repo_config, load_at_revision
    if args.revision:
        cfg = load_at_revision(args.repo, args.revision)
    else:
        cfg = load_repo_config(args.repo)

    state_overrides = {}
    if args.state:
        with open(args.state) as f:
            state_overrides = json.load(f)
    state = default_state(**state_overrides)
    seed_macro_variables(state, cfg)

    params = json.loads(args.params)
    trace = render_macro(cfg, args.macro, params, state)

    if trace.errors:
        for e in trace.errors:
            print(f"ERROR: {e}", file=sys.stderr)
    for line in trace.lines:
        print(line)
    return 1 if trace.errors else 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
