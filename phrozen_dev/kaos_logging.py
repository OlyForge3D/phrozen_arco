# KAOS_VERSION: v0.95
####################################
# KAOS logging shim for Phrozen Arco AMS Klipper extension
# Purpose:
#   Keep vendor files mostly untouched by moving custom log filtering here.
#
# Install from dev.py with:
#
#   from .kaos_logging import install_kaos_logging
#
# Then inside PhrozenDev.__init__(), immediately after super(...).__init__(config):
#
#   install_kaos_logging(self)
#
# This module intentionally uses a conservative safety model:
#   1) Known functional/protocol/status messages always pass through.
#   2) Tagged logs obey KAOS_LOG_LEVEL.
#   3) Known noisy debug chatter is filtered as DEBUG.
#   4) Unknown untagged messages pass through unchanged.
#
# Why not treat all untagged messages as DEBUG?
#   The Arco extension appears to use RespondInfo as a mixed console/protocol bus.
#   Some untagged messages can affect UI/state behavior. Unknown pass-through is
#   safer for vendor compatibility.
####################################

import json
import re
import time

try:
    from .kaos_translations import kaos_translate_message, kaos_normalize_language
except Exception:
    def kaos_normalize_language(language):
        return "en"
    def kaos_translate_message(message, language="en"):
        return str(message)

# Runtime log verbosity levels
KAOS_LOG_LEVEL_ERROR = 0
KAOS_LOG_LEVEL_WARN = 1
KAOS_LOG_LEVEL_INFO = 2
KAOS_LOG_LEVEL_DEBUG = 3

# Visible marker so we can prove which file Klipper loaded.
KAOS_LOGGING_VERSION = "KAOS-v0.95-2026-05-04"

KAOS_LEVEL_TAGS = ("[ERROR]", "[WARN]", "[INFO]", "[DEBUG]")

# Known Arco / AMS status prefixes that should bypass log filtering.
# Keep this as a conservative allow-list of protocol/status families.
KAOS_PROTOCOL_PREFIXES = (
    "+P114:",
    "+AMSERROR:",
    "+AMSCONNECT:",
    "+Mode:",
    "+PAUSE:",
    "+RESUME:",
    "+P1END:",
    "+P1En:",
    "+P1Gn:",
    "+P1Dn:",
    "+E:",
    "+G:",
    "+H:",
    "+J:",
    "+I:",
    "+B:",
    "+D:",
    "+Cut:",
)

# Keys seen in AMS detail/simple state JSON payloads.
KAOS_AMS_STATE_KEYS = (
    "dev_id",
    "active_dev_id",
    "target_dev_id",
    "end_dev_id",
    "dev_mode",
    "cache_empty",
    "cache_full",
    "cache_exist",
    "mc_state",
    "ma_state",
    "entry_state",
    "park_state",
)


def install_kaos_logging(obj):
    """Install KAOS logging wrapper on a PhrozenDev/Apis instance."""
    obj.KAOS_LogVerbosity = KAOS_LOG_LEVEL_WARN
    obj.KAOS_LogCategoriesEnabled = True
    obj.KAOS_LogTimestampEnabled = False
    obj.KAOS_LogLanguage = "en"

    # Preserve original vendor responder exactly once.
    if not hasattr(obj, "KAOS_OriginalRespondInfo"):
        obj.KAOS_OriginalRespondInfo = obj.G_PhrozenFluiddRespondInfo

    # Attach helper methods to the object so existing class code can call them.
    obj.kaos_strip_level_prefix = _kaos_strip_level_prefix.__get__(obj, obj.__class__)
    obj.kaos_parse_log_level = _kaos_parse_log_level.__get__(obj, obj.__class__)
    obj.kaos_strip_category_prefix = _kaos_strip_category_prefix.__get__(obj, obj.__class__)
    obj.kaos_should_log = _kaos_should_log.__get__(obj, obj.__class__)
    obj.kaos_detect_log_category = _kaos_detect_log_category.__get__(obj, obj.__class__)
    obj.kaos_render_log = _kaos_render_log.__get__(obj, obj.__class__)
    obj.kaos_is_protocol_message = _kaos_is_protocol_message.__get__(obj, obj.__class__)
    obj.kaos_is_ams_state_json = _kaos_is_ams_state_json.__get__(obj, obj.__class__)
    obj.kaos_is_functional_light_message = _kaos_is_functional_light_message.__get__(obj, obj.__class__)
    obj.kaos_is_silenced_serial_noise = _kaos_is_silenced_serial_noise.__get__(obj, obj.__class__)
    obj.kaos_is_known_debug_noise = _kaos_is_known_debug_noise.__get__(obj, obj.__class__)
    obj.kaos_emit_protocol = _kaos_emit_protocol.__get__(obj, obj.__class__)
    obj.kaos_log = _kaos_log.__get__(obj, obj.__class__)
    obj.kaos_filtered_respond_info = _kaos_filtered_respond_info.__get__(obj, obj.__class__)
    obj.KAOS_SetLogLevel = _KAOS_SetLogLevel.__get__(obj, obj.__class__)
    obj.KAOS_SetLogFlags = _KAOS_SetLogFlags.__get__(obj, obj.__class__)
    obj.KAOS_LogStatus = _KAOS_LogStatus.__get__(obj, obj.__class__)
    obj.KAOS_SetLogLanguage = _KAOS_SetLogLanguage.__get__(obj, obj.__class__)

    # Replace vendor responder with KAOS wrapper.
    obj.G_PhrozenFluiddRespondInfo = obj.kaos_filtered_respond_info

    obj.KAOS_OriginalRespondInfo("[WARN] [KAOS] kaos_logging loaded version %s" % KAOS_LOGGING_VERSION)

    # Register KAOS runtime commands if possible.
    try:
        obj.G_PhrozenGCode.register_command(
            "KAOS_LOG_LEVEL",
            obj.KAOS_SetLogLevel,
            desc="Set KAOS log verbosity (0=ERROR,1=WARN,2=INFO,3=DEBUG)",
        )
        obj.G_PhrozenGCode.register_command(
            "KAOS_LOG_FLAGS",
            obj.KAOS_SetLogFlags,
            desc="Set KAOS log flags (CATEGORIES=0/1 TIMESTAMP=0/1)",
        )
        obj.G_PhrozenGCode.register_command(
            "KAOS_LOG_LANGUAGE",
            obj.KAOS_SetLogLanguage,
            desc="Set KAOS message language (LANG=en/fr/zh)",
        )
        obj.G_PhrozenGCode.register_command(
            "KAOS_LOG_STATUS",
            obj.KAOS_LogStatus,
            desc="Show KAOS logging version and current settings",
        )
    except Exception:
        # Do not risk printer startup if command registration fails.
        pass


def _kaos_strip_level_prefix(self, msg):
    """Return (level, clean_message). Untagged messages return (None, msg).

    Standard output format is always:
      [ERROR]/[WARN]/[INFO]/[DEBUG] [SOURCE] message

    KAOS is only a source/category. Output is always standard level tags
    plus a source/category, for example: [WARN] [KAOS] message.

    If an older KAOS module accidentally emits a KAOS-prefixed level-style
    tag, normalize it before output so that tag never appears in console.
    """
    text = str(msg).strip()

    standard_tag_map = (
        ("[ERROR]", "ERROR"),
        ("[WARN]", "WARN"),
        ("[DEBUG]", "DEBUG"),
        ("[INFO]", "INFO"),
    )
    for tag, level in standard_tag_map:
        if text.startswith(tag):
            return level, text[len(tag):].strip()

    # Normalize old KAOS-prefixed level-style input without preserving the
    # original tag text. This prevents old emitters from leaking nonstandard
    # level names into the console while keeping KAOS as a category/source only.
    match = re.match(r"^\[(?:KAOS)_(ERROR|WARN|INFO|DEBUG)\]\s*(.*)$", text, re.IGNORECASE)
    if match:
        level = match.group(1).upper()
        clean = match.group(2).strip()
        if not clean.startswith("["):
            clean = "[KAOS] " + clean
        return level, clean

    return None, text

def _kaos_parse_log_level(self, msg):
    """Parse explicit log level. Untagged legacy messages remain unclassified."""
    return self.kaos_strip_level_prefix(msg)


def _kaos_normalize_category(category):
    """Normalize source/category names for display.

    KAOS is a source/category, not a level prefix. Older categories such as
    KAOS_DEV or KAOS_CONVEYOR are normalized to DEV / CONVEYOR. Exact KAOS is
    preserved so KAOS-owned logger messages can render as [WARN] [KAOS].
    """
    if category is None:
        return None
    clean = str(category).strip().upper().replace(" ", "_")
    if clean.startswith("KAOS_"):
        clean = clean[5:]
    return clean or "KAOS"


def _kaos_strip_category_prefix(self, msg):
    """Allow optional messages like '[AMS] text' after the level tag."""
    text = str(msg).strip()
    match = re.match(r"^\[([A-Za-z0-9_ -]+)\]\s*(.*)$", text)
    if not match:
        return None, text
    category = _kaos_normalize_category(match.group(1))
    clean = match.group(2).strip()
    return category, clean

def _kaos_should_log(self, level):
    level_map = {
        "ERROR": KAOS_LOG_LEVEL_ERROR,
        "WARN": KAOS_LOG_LEVEL_WARN,
        "INFO": KAOS_LOG_LEVEL_INFO,
        "DEBUG": KAOS_LOG_LEVEL_DEBUG,
    }
    return level_map.get(level, KAOS_LOG_LEVEL_DEBUG) <= self.KAOS_LogVerbosity


def _kaos_detect_log_category(self, msg):
    lowered = str(msg).lower()
    if any(token in lowered for token in ["serial", "tty", "uart", "usb", "p28", "p29"]):
        return "SERIAL"
    if any(token in lowered for token in [
        "toolhead", "nozzle", "purge", "spit", "cut", "park",
        "pause_waitingarea", "movement", "move", "hall sensor",
    ]):
        return "TOOLHEAD"
    if any(token in lowered for token in [
        "ams", "filament", "channel", "multicolor", "multi-material",
        "runout", "p0m3", "p114", "mc_state", "ma_state", "chroma",
    ]):
        return "AMS"
    return "DEV"


def _kaos_render_log(self, level, msg, category=None):
    parts = []
    if self.KAOS_LogTimestampEnabled:
        parts.append("[%s]" % time.strftime("%H:%M:%S"))

    # Keep standard level names. KAOS is a source/category, not a level prefix.
    level = str(level).upper()
    if level not in ("ERROR", "WARN", "INFO", "DEBUG"):
        level = "DEBUG"
    parts.append("[%s]" % level)

    if self.KAOS_LogCategoriesEnabled:
        clean_category = _kaos_normalize_category(category or self.kaos_detect_log_category(msg))
        parts.append("[%s]" % clean_category)

    parts.append(str(msg))
    return " ".join(parts)

def _kaos_is_protocol_message(self, msg):
    text = str(msg).strip()
    if text.startswith(KAOS_PROTOCOL_PREFIXES):
        return True

    # Extra conservative fallback: most +NAME: messages are Arco/AMS status.
    # We still avoid treating arbitrary '+' text as protocol unless it looks tokenized.
    if re.match(r"^\+[A-Za-z0-9_]+:", text):
        return True

    return False


def _kaos_is_ams_state_json(self, msg):
    """Detect actual AMS state JSON, not debug strings like json_data['x']=..."""
    text = str(msg).strip()
    if not (text.startswith("{") and text.endswith("}")):
        return False
    try:
        obj = json.loads(text)
    except Exception:
        return False
    if not isinstance(obj, dict):
        return False
    return any(key in obj for key in KAOS_AMS_STATE_KEYS)


def _kaos_is_functional_light_message(self, msg):
    """Detect Arco light-control traffic that looks like debug but is functional.

    On the Arco, P0 LED_* commands are emitted through the same responder path
    as ordinary debug chatter. Suppressing these lines in quiet mode can prevent
    KAOS_LIGHTS_ON/OFF/TOGGLE from working reliably, so they must bypass the
    log-level filter and pass through to the original responder.
    """
    text = str(msg).strip()

    # Common raw vendor trace forms:
    #   [(cmds.py)Cmds_CmdP0]command='P0 LED_SetState=0'
    #   [(cmds.py)Cmds_CmdP0]command='P0 LED_State=0'
    # Also tolerate already-rendered/category-prefixed forms.
    if "Cmds_CmdP0" in text and "P0 LED_" in text:
        return True

    # Future-proof direct P0 LED traces if the vendor changes the wrapper text.
    if re.search(r"\bP0\s+LED_[A-Za-z0-9_]+", text):
        return True

    return False


def _kaos_is_silenced_serial_noise(self, msg):
    """Suppress known harmless missing-tty2 chatter.

    Some Arco units only have/use tty1. The vendor extension periodically tries
    tty2 and emits an ERROR every few minutes when it is absent. This is noisy
    but expected on those machines. Keep tty1 errors visible, and only silence
    the specific missing/open-failed tty2 family.
    """
    text = str(msg).strip()
    lowered = text.lower()

    if "tty2" not in lowered:
        return False

    tty2_missing_markers = (
        "unable to open tty2",
        "ams2/tty2 not available",
        "未能打开tty2口",
        "tty2 not available",
    )
    return any(marker in lowered for marker in tty2_missing_markers)


def _kaos_is_known_debug_noise(self, msg):
    """Only match strings we are confident are human/debug chatter.

    This intentionally remains a known-noise allow-list. Unknown untagged lines
    still pass through for vendor safety. Protocol/status is checked before this
    function, so +P114/+Mode/+AMSCONNECT/+MCM/etc. and AMS JSON stay alive.
    """
    text = str(msg).strip()

    debug_prefixes = (
        # Python/internal variable dumps
        "json_data[",
        "self.G_",
        "=====self.",
        "self.Flag=",
        "command_string=",
        "gcmd is not None:",

        # Phrozen function-entry traces
        "=====[(cmds.python)",
        "===== [(cmds.python)",
        "[(base.python)",
        "[(base.py)",
        "[(cmds.python)",
        "[(cmds.py)",
        "[(dev.python)",
        "[(dev.py)",

        # Chinese vendor command/motion traces. These are human console/debug
        # lines showing commands already being sent through run_script_from_command.
        # They are not the functional +P/+Mode/+T protocol/status bus.
        "外部宏命令-",
        "开始调用外部宏命令-",
        "结束调用外部宏命令",
        "调用外部宏-",
        "调用宏命令:",
        "Z轴临时抬升",
        "Z轴临时下降",
        "Z轴下拉降低",
        "Z轴上拉升高",
        "Z轴上升",
        "恢复结束，开启风扇",

        # English/French translations of the same vendor debug families.
        "External macro command-",
        "External macro command ",
        "Starting external macro",
        "Finished external macro",
        "Z temporary lift",
        "Z temporary lower",
        "Z lowered",
        "Z raised",
        "Commande de macro externe",
        "Appel de la macro externe",
        "Abaissement temporaire de Z",
        "Relèvement temporaire de Z",

        # Serial byte dump chatter
        "byte count",
        "byte stream",
        "Lo_SerialRxBytes[",
        "ASCII character",

        # Local filesystem / image-id debug traces
        "current_directory=",
        "filename=",

        # Pause-state debug traces
        "Current pause state",
        "Lo_PauseStatus",

        # Misc vendor debug text observed during P114/P28/startup
        "has unit AMSalready openserial port=",
        "successfulopenAMSAMShas unit",
        "Applied g_bottom_print_y=",
        "Run Current:",
    )
    if text.startswith(debug_prefixes):
        return True

    debug_contains = (
        "Cmds_P1TnManualChangeChannel",
        "Cmds_P1CnAutoChangeChannel",
        "command_string='",
        "gcode命令=",
        "GCODE命令",
        "G-code command",
        "gcodecommand=",
    )
    if any(token in text for token in debug_contains):
        return True

    # Numeric debug lines emitted while parsing DriveCodeFile.dat, e.g.
    #   1
    #   18
    #   25328
    #   1,18,25328,18,1
    # Keep this conservative: only pure comma-separated integers.
    if re.match(r"^-?\d+(,-?\d+)*$", text):
        return True

    return False


def _kaos_emit_protocol(self, msg):
    self.KAOS_OriginalRespondInfo(msg)


def _kaos_log(self, level, msg, category=None):
    if self.kaos_should_log(level):
        self.KAOS_OriginalRespondInfo(self.kaos_render_log(level, msg, category))


def _kaos_filtered_respond_info(self, msg):
    try:
        raw_text = str(msg).strip()

        # Raw functional protocol/status must bypass translation and logging.
        if self.kaos_is_protocol_message(raw_text) or self.kaos_is_ams_state_json(raw_text):
            self.kaos_emit_protocol(raw_text)
            return

        # Light-control P0 LED traffic looks like debug output but is functional.
        # It must bypass the filter before translation/classification.
        if self.kaos_is_functional_light_message(raw_text):
            self.kaos_emit_protocol(raw_text)
            return

        # Known harmless missing-tty2 noise should be dropped even if tagged ERROR.
        if self.kaos_is_silenced_serial_noise(raw_text):
            return

        # Translate human-facing vendor text before parsing [INFO]/[WARN]/etc.
        translated_text = kaos_translate_message(raw_text, self.KAOS_LogLanguage)
        level, clean_text = self.kaos_strip_level_prefix(translated_text)

        # Functional protocol/status must still bypass logging if a translated
        # line or a manually tagged line wraps it as [INFO] +P114:2, etc.
        if self.kaos_is_protocol_message(clean_text) or self.kaos_is_ams_state_json(clean_text):
            self.kaos_emit_protocol(clean_text)
            return

        # Light-control P0 LED traffic may also appear after level/category parsing.
        if self.kaos_is_functional_light_message(clean_text):
            self.kaos_emit_protocol(clean_text)
            return

        # Known harmless missing-tty2 noise may appear after translation.
        if self.kaos_is_silenced_serial_noise(clean_text):
            return

        # Tagged logs obey KAOS_LOG_LEVEL.
        if level is not None:
            category, message_text = self.kaos_strip_category_prefix(clean_text)
            if self.kaos_is_silenced_serial_noise(message_text):
                return

            # KAOS v13: downgrade known vendor spam that is tagged WARN/ERROR
            # upstream but is routine state chatter on the Arco. Keep it visible
            # only when DEBUG logging is intentionally enabled.
            msg_lower = str(message_text).lower()
            if str(message_text).strip() == "Not currently paused":
                level = "DEBUG"
                category = category or "DEV"
            elif (
                "cmds_usbconnecterrorcheck" in msg_lower
                and "reinitializing serial port" in msg_lower
            ):
                level = "DEBUG"
                category = category or "SERIAL"

            self.kaos_log(level, message_text, category)
            return

        # Known noisy legacy debug chatter is filtered as DEBUG.
        if self.kaos_is_known_debug_noise(clean_text):
            self.kaos_log("DEBUG", clean_text)
            return

        # Unknown untagged messages pass through. If translation changed the text,
        # show the translated text; otherwise preserve the vendor message.
        self.KAOS_OriginalRespondInfo(translated_text)

    except Exception:
        # Fail open to avoid breaking printer behavior if classifier has a bug.
        self.KAOS_OriginalRespondInfo(msg)



def _KAOS_LogStatus(self, gcmd):
    self.KAOS_OriginalRespondInfo(
        self.kaos_render_log(
            "WARN",
            "KAOS logging status version=%s level=%d categories=%d timestamp=%d language=%s" % (
                KAOS_LOGGING_VERSION,
                self.KAOS_LogVerbosity,
                1 if self.KAOS_LogCategoriesEnabled else 0,
                1 if self.KAOS_LogTimestampEnabled else 0,
                self.KAOS_LogLanguage,
            ),
            "KAOS",
        )
    )

def _KAOS_SetLogLevel(self, gcmd):
    level = gcmd.get_int("LEVEL", self.KAOS_LogVerbosity)
    if level < KAOS_LOG_LEVEL_ERROR:
        level = KAOS_LOG_LEVEL_ERROR
    if level > KAOS_LOG_LEVEL_DEBUG:
        level = KAOS_LOG_LEVEL_DEBUG
    self.KAOS_LogVerbosity = level
    self.KAOS_OriginalRespondInfo(
        self.kaos_render_log(
            "INFO",
            "KAOS log verbosity set to %d (0=ERROR, 1=WARN, 2=INFO, 3=DEBUG)" % level,
            "KAOS",
        )
    )


def _KAOS_SetLogLanguage(self, gcmd):
    lang = gcmd.get("LANG", None)
    if lang is None:
        lang = gcmd.get("LANGUAGE", self.KAOS_LogLanguage)
    self.KAOS_LogLanguage = kaos_normalize_language(lang)
    self.KAOS_OriginalRespondInfo(
        self.kaos_render_log(
            "INFO",
            "KAOS log language set to %s (en=English, fr=French, zh=original Chinese)" % self.KAOS_LogLanguage,
            "KAOS",
        )
    )


def _KAOS_SetLogFlags(self, gcmd):
    self.KAOS_LogCategoriesEnabled = bool(
        gcmd.get_int("CATEGORIES", 1 if self.KAOS_LogCategoriesEnabled else 0)
    )
    self.KAOS_LogTimestampEnabled = bool(
        gcmd.get_int("TIMESTAMP", 1 if self.KAOS_LogTimestampEnabled else 0)
    )
    self.KAOS_OriginalRespondInfo(
        self.kaos_render_log(
            "INFO",
            "KAOS log flags updated: CATEGORIES=%d TIMESTAMP=%d" % (
                1 if self.KAOS_LogCategoriesEnabled else 0,
                1 if self.KAOS_LogTimestampEnabled else 0,
            ),
            "KAOS",
        )
    )
