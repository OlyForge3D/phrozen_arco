# KAOS_VERSION: vbeta-kaos-v1-0-84-0874b9e7 2026-07-03
"""KAOS pre-home motion guard for Phrozen Arco.

This module is bootstrapped from phrozen_dev.dev, not loaded as a standalone
Klipper extra section. It wraps native G0/G1 only while KAOS physical-home trust
is unknown. After _SET_TRUSTED_XYZ, native G0/G1 handlers are restored so normal
printing has no ongoing KAOS movement-guard overhead.

This intentionally uses Klipper's internal gcode handler table because the goal
is command-level interception without Jinja G0/G1 wrappers.
"""

import logging
import time

LOG = logging.getLogger(__name__)


class KaosMotionGuard:
    def __init__(self, phrozen_dev):
        self.phrozen_dev = phrozen_dev
        self.printer = getattr(phrozen_dev, "G_PhrozenPrinter", None)
        self.gcode = getattr(phrozen_dev, "G_PhrozenGCode", None)

        if self.gcode is None:
            raise RuntimeError("KAOS Motion Guard: no gcode object available")

        self.guard_armed = True
        self.homing_bypass = False
        self.trusted_xy = False
        self.trusted_z = False
        # Separate from trusted_xy/trusted_z. Recovery authorization is a
        # user-accepted risk path for power-loss recovery; it does not mean the
        # printer is physically homed.
        self.recovery_authorized = False

        self._handlers = self._get_handler_table()
        self._orig_g0 = None
        self._orig_g1 = None
        self._orig_g28 = None
        self.g0_wrapped = False
        self.g1_wrapped = False
        self.g28_wrapped = False

        # Diagnostic-only: prove dispatch actually flows through the wrapper,
        # not just that a dict write succeeded. Incremented inside the
        # cmd_*_guarded methods themselves, so a nonzero count after a real
        # G1 means Klipper resolved the command through our replaced entry.
        self.g0_hits = 0
        self.g1_hits = 0
        self.g28_hits = 0

        self._register_control_commands()
        self._wrap_g0_g1()
        self._wrap_g28()
        LOG.info("KAOS Motion Guard: installed")

    def _is_mapping_like(self, obj):
        # Broader than isinstance(obj, dict): accepts any object that supports
        # containment and lookup, in case the real handler table is a dict
        # subclass or custom mapping rather than a plain dict.
        return hasattr(obj, "__contains__") and (
            hasattr(obj, "get") or hasattr(obj, "__getitem__")
        )

    def _get_handler_table(self):
        # Select the live handler mapping by command presence, not just by the
        # first attribute name that exists. On this Klipper build, both
        # gcode_handlers and ready_gcode_handlers can exist; the active dispatch
        # path after Klippy is ready is expected to be ready_gcode_handlers.
        preferred = ("ready_gcode_handlers", "gcode_handlers", "_gcode_handlers")

        fallback = None
        for attr in preferred:
            handlers = getattr(self.gcode, attr, None)
            if not self._is_mapping_like(handlers):
                continue

            if fallback is None:
                fallback = (attr, handlers)

            try:
                if "G0" in handlers or "G1" in handlers or "G28" in handlers:
                    self._handler_table_name = attr
                    return handlers
            except Exception:
                continue

        if fallback is not None:
            self._handler_table_name = fallback[0]
            return fallback[1]

        raise RuntimeError("KAOS Motion Guard: could not find Klipper gcode handler table")

    def _refresh_handler_table(self):
        self._handlers = self._get_handler_table()
        return self._handlers


    def _register_control_commands(self):
        commands = (
            ("KAOS_MOTION_GUARD_ARM", self.cmd_arm, "Arm KAOS pre-home motion guard"),
            ("KAOS_MOTION_GUARD_DISARM", self.cmd_disarm, "Disarm KAOS pre-home motion guard"),
            ("KAOS_MOTION_GUARD_TRUST_XYZ", self.cmd_trust_xyz, "Mark XYZ trusted and restore native G0/G1"),
            ("KAOS_MOTION_GUARD_TRUST_XY", self.cmd_trust_xy, "Mark XY trusted (Z remains at current state)"),
            ("KAOS_MOTION_GUARD_TRUST_Z", self.cmd_trust_z, "Mark Z trusted (XY remains at current state)"),
            ("KAOS_MOTION_GUARD_CLEAR_TRUST", self.cmd_clear_trust, "Clear trust and re-wrap G0/G1"),
            ("KAOS_MOTION_GUARD_AUTHORIZE_RECOVERY", self.cmd_authorize_recovery, "Allow guarded axis motion for user-authorized power-loss recovery"),
            ("KAOS_MOTION_GUARD_CLEAR_RECOVERY_AUTH", self.cmd_clear_recovery_auth, "Clear power-loss recovery motion authorization"),
            ("KAOS_MOTION_GUARD_STATUS", self.cmd_status, "Show KAOS motion guard status"),
            ("KAOS_HOME_IF_NEEDED", self.cmd_home_if_needed, "Home XYZ if KAOS trust is not already established; performs a short grace check before PG28 fallback"),
        )
        for name, func, desc in commands:
            self._register_or_replace(name, func, desc)

    def _register_or_replace(self, name, func, desc=None):
        # Prefer public registration for new KAOS commands, but tolerate reloads
        # by removing an existing KAOS handler first.
        if name in self._handlers:
            old = self._handlers.get(name)
            if getattr(old, "__self__", None) is self:
                self._handlers.pop(name, None)
            else:
                LOG.warning("KAOS Motion Guard: replacing existing command %s", name)
                self._handlers.pop(name, None)
        self.gcode.register_command(name, func, desc=desc)

    def _wrap_g0_g1(self):
        handlers = self._refresh_handler_table()

        if not self.g0_wrapped:
            current = handlers.get("G0") if hasattr(handlers, "get") else handlers["G0"] if "G0" in handlers else None
            if current is None:
                LOG.warning("KAOS Motion Guard: G0 handler not found; G0 not guarded")
            else:
                self._orig_g0 = current
                handlers["G0"] = self.cmd_G0_guarded
                self.g0_wrapped = True
                LOG.info("KAOS Motion Guard: wrapped G0")

        if not self.g1_wrapped:
            current = handlers.get("G1") if hasattr(handlers, "get") else handlers["G1"] if "G1" in handlers else None
            if current is None:
                LOG.warning("KAOS Motion Guard: G1 handler not found; G1 not guarded")
            else:
                self._orig_g1 = current
                handlers["G1"] = self.cmd_G1_guarded
                self.g1_wrapped = True
                LOG.info("KAOS Motion Guard: wrapped G1")

    def _restore_g0_g1(self):
        handlers = self._refresh_handler_table()
        if self.g0_wrapped and self._orig_g0 is not None:
            handlers["G0"] = self._orig_g0
            self.g0_wrapped = False
            LOG.info("KAOS Motion Guard: restored native G0")
        if self.g1_wrapped and self._orig_g1 is not None:
            handlers["G1"] = self._orig_g1
            self.g1_wrapped = False
            LOG.info("KAOS Motion Guard: restored native G1")

    def _wrap_g28(self):
        if self.g28_wrapped:
            return

        handlers = self._refresh_handler_table()

        current = handlers.get("G28") if hasattr(handlers, "get") else handlers["G28"] if "G28" in handlers else None
        if current is None:
            LOG.warning("KAOS Motion Guard: G28 handler not found; homing bypass wrapper not installed")
            return
        self._orig_g28 = current
        handlers["G28"] = self.cmd_G28_guarded
        self.g28_wrapped = True
        LOG.info("KAOS Motion Guard: wrapped G28")

    def _get_params(self, gcmd):
        try:
            return gcmd.get_command_parameters()
        except Exception:
            # Conservative fallback parser for older command objects.
            try:
                line = gcmd.get_commandline()
            except Exception:
                return {}
            parts = line.split()
            params = {}
            for part in parts[1:]:
                if not part:
                    continue
                key = part[0].upper()
                if key.isalpha():
                    params[key] = part[1:]
            return params

    def _is_internal_bypass_active(self):
        """Check _KAOS_SAFETY_MODE_CONFIG.motion_guard_bypass from the Jinja layer.

        This is the shared bypass flag used by _KAOS_SAFETY_MODE_ENABLE_INTERNAL_MOTION_BYPASS
        and _KAOS_SAFETY_MODE_DISABLE_INTERNAL_MOTION_BYPASS. Reading it here means the
        Python motion guard and Jinja-layer guards stay in sync without duplicating state.
        """
        try:
            cfg = self.printer.lookup_object("gcode_macro _KAOS_SAFETY_MODE_CONFIG")
            return bool(cfg.variables.get("motion_guard_bypass", 0))
        except Exception:
            return False

    def _clear_internal_motion_bypass(self, reason):
        """Force-clear the Jinja-layer internal motion bypass.

        This must not raise. It may run from a G28 finally block after a
        homing/probing failure, and raising here would mask the original
        homing error.
        """
        try:
            cfg = self.printer.lookup_object("gcode_macro _KAOS_SAFETY_MODE_CONFIG")
            cfg.variables["motion_guard_bypass"] = 0
            LOG.info("KAOS Motion Guard: internal motion bypass cleared REASON=%s", reason)
        except Exception:
            LOG.exception(
                "KAOS Motion Guard: failed to clear internal motion bypass REASON=%s",
                reason,
            )

    def _check_motion_allowed(self, gcmd):
        params = self._get_params(gcmd)
        has_x = "X" in params
        has_y = "Y" in params
        has_z = "Z" in params

        if not (has_x or has_y or has_z):
            return
        if not self.guard_armed:
            return
        if self.homing_bypass:
            return
        if self.recovery_authorized:
            return
        if self._is_internal_bypass_active():
            return
        # Allow Z moves during cutter calibration. The vendor sets G_CutCheckTest=True
        # for the duration of P11/P12 and the cut sequence requires controlled Z moves.
        if getattr(self.phrozen_dev, "G_CutCheckTest", False):
            return

        if (has_x or has_y) and not self.trusted_xy:
            raise gcmd.error("KAOS blocked XY move before trusted homing")
        if has_z and not self.trusted_z:
            raise gcmd.error("KAOS blocked Z move before trusted homing")

    def cmd_G0_guarded(self, gcmd):
        self.g0_hits += 1
        self._check_motion_allowed(gcmd)
        return self._orig_g0(gcmd)

    def cmd_G1_guarded(self, gcmd):
        self.g1_hits += 1
        self._check_motion_allowed(gcmd)
        return self._orig_g1(gcmd)

    def cmd_G28_guarded(self, gcmd):
        self.g28_hits += 1
        old_bypass = self.homing_bypass
        self.homing_bypass = True
        LOG.info("KAOS Motion Guard: homing bypass active REASON=G28")
        try:
            return self._orig_g28(gcmd)
        finally:
            self.homing_bypass = old_bypass
            self._clear_internal_motion_bypass("G28_finally")
            LOG.info("KAOS Motion Guard: homing bypass ended REASON=G28")

    def _respond(self, gcmd, msg):
        try:
            gcmd.respond_info(msg)
        except Exception:
            try:
                self.gcode.respond_info(msg)
            except Exception:
                LOG.info(msg)

    def _trust_xyz(self, reason):
        self.trusted_xy = True
        self.trusted_z = True
        self.homing_bypass = False
        self.guard_armed = False
        self._restore_g0_g1()
        LOG.info("KAOS Motion Guard: XYZ trusted; guard disarmed REASON=%s", reason)

    def _clear_trust(self, reason):
        self.trusted_xy = False
        self.trusted_z = False
        # Also clear recovery authorization. A power-loss recovery session ends
        # when trust is explicitly cleared (M84, CANCEL_PRINT, restart). If a
        # new recovery is needed, AUTHORIZE_POWER_LOSS_RECOVERY must be called
        # again. This prevents a stale recovery_authorized from silently bypassing
        # a re-armed guard after trust is cleared.
        self.recovery_authorized = False
        # Preserve an active homing bypass. Full-home homing_override clears
        # KAOS trust after G28 has already entered the Python homing bypass;
        # clearing trust must not block the remaining controlled homing moves.
        if not self.homing_bypass:
            self._clear_internal_motion_bypass(reason)
        else:
            LOG.info(
                "KAOS Motion Guard: preserving internal motion bypass during active homing REASON=%s",
                reason,
            )
        self.guard_armed = True
        self._wrap_g0_g1()
        LOG.info("KAOS Motion Guard: trust cleared; guard armed REASON=%s", reason)

    def _trust_xy(self, reason):
        self.trusted_xy = True
        LOG.info("KAOS Motion Guard: XY trusted REASON=%s", reason)

    def _trust_z(self, reason):
        self.trusted_z = True
        LOG.info("KAOS Motion Guard: Z trusted REASON=%s", reason)

    def _authorize_recovery(self, reason):
        self.recovery_authorized = True
        # Do NOT re-arm or re-wrap here. _clear_trust() already armed and
        # re-wrapped G0/G1 when trust was cleared (e.g. on power-loss reset).
        # Recovery authorization is a bypass on top of an already-armed guard,
        # not a separate arming event. Keeping the guard armed means recovery
        # moves still flow through _check_motion_allowed and increment hit
        # counters, and the authorization can be revoked by _clear_recovery_auth.
        LOG.info("KAOS Motion Guard: recovery motion authorized REASON=%s", reason)

    def _clear_recovery_auth(self, reason):
        self.recovery_authorized = False
        LOG.info("KAOS Motion Guard: recovery authorization cleared REASON=%s", reason)

    def cmd_arm(self, gcmd):
        reason = gcmd.get("REASON", "manual_arm")
        self.guard_armed = True
        self._wrap_g0_g1()
        self._respond(gcmd, "KAOS Motion Guard: armed REASON=%s" % reason)

    def cmd_disarm(self, gcmd):
        reason = gcmd.get("REASON", "manual_disarm")
        self.guard_armed = False
        self.homing_bypass = False
        self._restore_g0_g1()
        self._respond(gcmd, "KAOS Motion Guard: disarmed REASON=%s" % reason)

    def cmd_trust_xyz(self, gcmd):
        reason = gcmd.get("REASON", "trusted_home")
        self._trust_xyz(reason)
        self._respond(gcmd, "KAOS Motion Guard: XYZ trusted; guard disarmed REASON=%s" % reason)

    def cmd_trust_xy(self, gcmd):
        reason = gcmd.get("REASON", "trusted_xy")
        self._trust_xy(reason)
        self._respond(gcmd, "KAOS Motion Guard: XY trusted REASON=%s" % reason)

    def cmd_trust_z(self, gcmd):
        reason = gcmd.get("REASON", "trusted_z")
        self._trust_z(reason)
        self._respond(gcmd, "KAOS Motion Guard: Z trusted REASON=%s" % reason)

    def cmd_clear_trust(self, gcmd):
        reason = gcmd.get("REASON", "clear_trust")
        self._clear_trust(reason)
        self._respond(gcmd, "KAOS Motion Guard: trust cleared; guard armed REASON=%s" % reason)

    def cmd_authorize_recovery(self, gcmd):
        reason = gcmd.get("REASON", "power_loss_recovery")
        self._authorize_recovery(reason)
        self._respond(gcmd, "KAOS Motion Guard: recovery motion authorized REASON=%s" % reason)

    def cmd_clear_recovery_auth(self, gcmd):
        reason = gcmd.get("REASON", "clear_recovery_auth")
        self._clear_recovery_auth(reason)
        self._respond(gcmd, "KAOS Motion Guard: recovery authorization cleared REASON=%s" % reason)

    def cmd_home_if_needed(self, gcmd):
        """KAOS_HOME_IF_NEEDED TIMEOUT=10 INTERVAL=0.25

        Wait up to TIMEOUT seconds (checking every INTERVAL seconds) for KAOS
        trusted-XYZ state to become established. If trust is already present,
        return immediately. If trust appears during the wait, return without
        homing. If trust is still absent at timeout expiry, invoke PG28 as a
        safe fallback via the existing homing path, then validate trust was
        actually established.

        This command never sets trust directly. All trust state changes flow
        through the existing _SET_TRUSTED_XYZ / homing_override path.
        """
        timeout = gcmd.get_float("TIMEOUT", 10.0, minval=0.0)
        interval = gcmd.get_float("INTERVAL", 0.25, minval=0.05)

        if self.trusted_xy and self.trusted_z:
            LOG.info("KAOS_HOME_IF_NEEDED: XYZ already trusted; skipping home")
            self._respond(gcmd, "KAOS_HOME_IF_NEEDED: trusted home already established; no home required")
            return

        # Short grace-period check only — not a synchronization guarantee.
        # time.sleep() blocks this execution path while polling Python-level
        # trust state. If trust does not appear during this window, PG28
        # fallback is the real safety mechanism.
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.trusted_xy and self.trusted_z:
                LOG.info("KAOS_HOME_IF_NEEDED: XYZ trust appeared during wait; skipping fallback home")
                self._respond(gcmd, "KAOS_HOME_IF_NEEDED: vendor home detected; no fallback home required")
                return
            time.sleep(interval)

        # Trust did not appear within the timeout. Fall back to PG28, which
        # exercises the full homing_override and _SET_TRUSTED_XYZ path.
        LOG.info(
            "KAOS_HOME_IF_NEEDED: trust not established after %.1fs; invoking PG28 fallback",
            timeout,
        )
        self._respond(gcmd, "KAOS_HOME_IF_NEEDED: no vendor home detected after %.1fs; invoking PG28" % timeout)

        try:
            self.gcode.run_script_from_command("PG28")
        except Exception as e:
            raise gcmd.error("KAOS_HOME_IF_NEEDED: PG28 fallback failed: %s" % str(e))

        # Post-fallback trust validation. PG28 must have established trust via
        # the normal homing_override / _SET_TRUSTED_XYZ path. If trust is still
        # absent after PG28 completes, block the print with a clear error rather
        # than allowing motion in an untrusted state.
        if not (self.trusted_xy and self.trusted_z):
            raise gcmd.error(
                "KAOS_HOME_IF_NEEDED: PG28 completed but KAOS trusted-home state was not established. "
                "Check homing_override and _SET_TRUSTED_XYZ. Aborting to prevent untrusted motion."
            )

        LOG.info("KAOS_HOME_IF_NEEDED: PG28 fallback succeeded; XYZ trust confirmed")
        self._respond(gcmd, "KAOS_HOME_IF_NEEDED: PG28 fallback complete; trusted home confirmed")

    def cmd_status(self, gcmd):
        self._respond(
            gcmd,
            "KAOS Motion Guard: armed=%d bypass=%d trusted_xy=%d trusted_z=%d recovery_authorized=%d "
            "g0_wrapped=%d g1_wrapped=%d g28_wrapped=%d "
            "g0_hits=%d g1_hits=%d g28_hits=%d handler_table=%s"
            % (
                int(self.guard_armed),
                int(self.homing_bypass),
                int(self.trusted_xy),
                int(self.trusted_z),
                int(self.recovery_authorized),
                int(self.g0_wrapped),
                int(self.g1_wrapped),
                int(self.g28_wrapped),
                self.g0_hits,
                self.g1_hits,
                self.g28_hits,
                getattr(self, "_handler_table_name", "unknown"),
            ),
        )


def install_kaos_motion_guard(phrozen_dev):
    """Install the KAOS motion guard from a PhrozenDev instance."""
    if getattr(phrozen_dev, "_kaos_motion_guard_installed", False):
        return getattr(phrozen_dev, "_kaos_motion_guard", None)
    guard = KaosMotionGuard(phrozen_dev)
    phrozen_dev._kaos_motion_guard = guard
    phrozen_dev._kaos_motion_guard_installed = True
    return guard
