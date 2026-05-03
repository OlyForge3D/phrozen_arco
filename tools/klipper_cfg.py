"""
Minimal Klipper config parser for static analysis of gcode_macro definitions.

Parses the subset of Klipper config syntax that we need:
  - [section_name] section headers (optionally with a value: [section_name X])
  - key: value or key=value option lines (within a section)
  - gcode: multi-line bodies (everything until the next [section] or EOF)
  - # and ; comments (line-leading)

Only [gcode_macro NAME], [delayed_gcode NAME], and a few other section types
are exposed in detail; the rest are returned as opaque blobs so the parser
doesn't break on Klipper extensions we don't care about.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


SECTION_RE = re.compile(r"^\[([\w_]+)(?:\s+([^\]]+))?\]\s*$")
OPTION_RE = re.compile(r"^([a-zA-Z_][\w]*)\s*[:=]\s*(.*?)\s*$")
GCODE_KEY_RE = re.compile(r"^gcode\s*:\s*(.*)$")


@dataclass
class GcodeMacro:
    name: str                           # e.g. "PG101"
    description: str = ""
    variables: dict[str, str] = field(default_factory=dict)  # variable_X -> raw value string
    rename_existing: str | None = None
    body: str = ""                      # raw gcode body
    body_start_line: int = 0            # 1-indexed line in source file
    file: str = ""                      # source file path


@dataclass
class DelayedGcode:
    name: str
    initial_duration: str = ""
    body: str = ""
    body_start_line: int = 0
    file: str = ""


@dataclass
class Section:
    """A non-macro section we don't care about in detail; keep options as a dict."""
    kind: str                           # e.g. "stepper_z", "extruder", "printer"
    label: str = ""                     # e.g. "stepper_z" -> ""; "tmc5160 stepper_x" -> "stepper_x"
    options: dict[str, str] = field(default_factory=dict)
    file: str = ""


@dataclass
class Config:
    """Parsed view of the union of all .cfg files we loaded."""
    macros: dict[str, GcodeMacro] = field(default_factory=dict)
    delayed: dict[str, DelayedGcode] = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)

    def section_options(self, kind: str, label: str = "") -> dict[str, str]:
        """Return options for the first section matching (kind, label)."""
        for s in self.sections:
            if s.kind == kind and s.label == label:
                return s.options
        return {}


def parse_cfg(path: str | Path) -> Config:
    """Parse a single .cfg file into a fresh Config."""
    cfg = Config()
    add_cfg(cfg, path)
    return cfg


def add_cfg(cfg: Config, path: str | Path) -> None:
    """Merge sections from one .cfg file into an existing Config.

    Klipper resolves duplicate sections by 'last definition wins' for macros;
    we mimic that here by overwriting earlier macros with later ones.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Skip blank lines and pure comments at the top level
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            i += 1
            continue

        m = SECTION_RE.match(stripped)
        if not m:
            # Stray content outside any section — skip
            i += 1
            continue

        kind = m.group(1).strip()
        label = (m.group(2) or "").strip()
        section_start = i + 1  # 1-indexed
        i += 1

        # Collect option lines until we hit another section header (or EOF).
        # 'gcode:' is special: it starts a multi-line body that continues until
        # the next section header or EOF.
        in_gcode = False
        gcode_lines: list[str] = []
        gcode_start = 0
        options: dict[str, str] = {}
        variables: dict[str, str] = {}
        description = ""
        rename_existing: str | None = None
        initial_duration: str = ""

        while i < n:
            raw = lines[i]
            stripped = raw.strip()

            if stripped.startswith("[") and SECTION_RE.match(stripped):
                # Hit the next section
                break

            if in_gcode:
                gcode_lines.append(raw)
                i += 1
                continue

            mg = GCODE_KEY_RE.match(stripped)
            if mg:
                in_gcode = True
                gcode_start = i + 1
                rest = mg.group(1)
                if rest:
                    gcode_lines.append(rest)
                i += 1
                continue

            mo = OPTION_RE.match(stripped)
            if mo:
                key = mo.group(1)
                value = mo.group(2)
                # Strip inline ; or # comment trailing parts only if the option
                # is one we care about; for general options we keep the raw value.
                if key.startswith("variable_"):
                    # Inline ; or # is a comment in Klipper
                    val_clean = re.split(r"\s+[;#]", value, 1)[0].rstrip()
                    variables[key] = val_clean
                elif key == "description":
                    description = value
                elif key == "rename_existing":
                    rename_existing = value.strip()
                elif key == "initial_duration":
                    initial_duration = value.strip()
                else:
                    val_clean = re.split(r"\s+[;]", value, 1)[0].rstrip()
                    options[key] = val_clean
                i += 1
                continue

            # Non-option, non-section line: ignore it (or it's a continuation)
            i += 1

        body = "\n".join(gcode_lines)

        if kind == "gcode_macro":
            cfg.macros[label] = GcodeMacro(
                name=label,
                description=description,
                variables=variables,
                rename_existing=rename_existing,
                body=body,
                body_start_line=gcode_start,
                file=str(p),
            )
        elif kind == "delayed_gcode":
            cfg.delayed[label] = DelayedGcode(
                name=label,
                initial_duration=initial_duration,
                body=body,
                body_start_line=gcode_start,
                file=str(p),
            )
        else:
            cfg.sections.append(Section(
                kind=kind,
                label=label,
                options=options,
                file=str(p),
            ))


def load_repo_config(repo_root: str | Path, cfg_files: Iterable[str] | None = None) -> Config:
    """Load all known config files from a repo root.

    If cfg_files is None, defaults to the standard set we maintain.
    """
    repo = Path(repo_root)
    if cfg_files is None:
        cfg_files = [
            "config/printer.cfg",
            "config/printer_gcode_macro.cfg",
            "config/kaos.cfg",
            "config/kaos/kaos_safety.cfg",
            "config/kaos/kaos_logging.cfg",
            "config/kaos/kaos_fans.cfg",
            "config/kaos/kaos_lights.cfg",
            "config/kaos/kaos_steppers.cfg",
            "config/kaos/kaos_beeper.cfg",
            "config/kaos/kaos_mesh.cfg",
            "config/kaos/kaos_z_tilt.cfg",
            "config/kaos/kaos_screws_tilt.cfg",
            "config/kaos/kaos_dynamic_speed.cfg",
            "config/kaos/kaos_debug.cfg",
            "config/kaos/magic_ams_by_chris.cfg",
        ]
    cfg = Config()
    for rel in cfg_files:
        p = repo / rel
        if p.exists():
            add_cfg(cfg, p)
    return cfg


def load_at_revision(repo_root: str | Path, revision: str, cfg_files: Iterable[str] | None = None) -> Config:
    """Load config at a specific git revision via `git show`.

    Files that don't exist at that revision are silently skipped (so we can
    compare older revisions that lacked some files).
    """
    import subprocess
    if cfg_files is None:
        cfg_files = [
            "config/printer.cfg",
            "config/printer_gcode_macro.cfg",
            "config/kaos.cfg",
            "config/kaos/kaos_safety.cfg",
            "config/kaos/kaos_logging.cfg",
            "config/kaos/kaos_fans.cfg",
            "config/kaos/kaos_lights.cfg",
            "config/kaos/kaos_steppers.cfg",
            "config/kaos/kaos_beeper.cfg",
            "config/kaos/kaos_mesh.cfg",
            "config/kaos/kaos_z_tilt.cfg",
            "config/kaos/kaos_screws_tilt.cfg",
            "config/kaos/kaos_dynamic_speed.cfg",
            "config/kaos/kaos_debug.cfg",
            "config/kaos/magic_ams_by_chris.cfg",
        ]
    cfg = Config()
    for rel in cfg_files:
        try:
            text = subprocess.check_output(
                ["git", "-C", str(repo_root), "show", f"{revision}:{rel}"],
                text=True, encoding="utf-8", stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            continue  # file didn't exist at that revision
        # add_cfg expects a path; write to a temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as tf:
            tf.write(text)
            tmp_path = tf.name
        try:
            add_cfg(cfg, tmp_path)
            # Override the .file attribute to point to the original path so
            # error messages reference the real config filename.
            for m in cfg.macros.values():
                if m.file == tmp_path:
                    m.file = rel
            for d in cfg.delayed.values():
                if d.file == tmp_path:
                    d.file = rel
            for s in cfg.sections:
                if s.file == tmp_path:
                    s.file = rel
        finally:
            import os
            os.unlink(tmp_path)
    return cfg
