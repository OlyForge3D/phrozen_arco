# KAOS_VERSION: v0.95
####################################
# KAOS translation loader for Phrozen Arco AMS Klipper extension
#
# Source strings remain the original vendor Chinese strings.
# Language tables live in a lang subpackage and are lazy-loaded:
#   lang/__init__.py
#   lang/kaos_translations_en.py
#   lang/kaos_translations_fr.py
#   lang/kaos_translations_zh.py
#
# en = English, default
# fr = French
# zh = Chinese/original passthrough
#
# Memory behavior:
#   - No language table is imported at module load time.
#   - Only the selected language table is imported when first used.
#   - There is no fallback to English. If the selected language does not
#     contain a source string, the original vendor text passes through.
####################################

import importlib
import re

KAOS_DEFAULT_LANGUAGE = "en"

KAOS_SUPPORTED_LANGUAGES = ("en", "fr", "zh")

KAOS_LANGUAGE_ALIASES = {
    "en": "en",
    "eng": "en",
    "english": "en",

    "fr": "fr",
    "fre": "fr",
    "fra": "fr",
    "french": "fr",
    "français": "fr",
    "francais": "fr",

    "zh": "zh",
    "cn": "zh",
    "chi": "zh",
    "zho": "zh",
    "chinese": "zh",
    "中文": "zh",
    "original": "zh",
    "vendor": "zh",
}

KAOS_LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "zh": "Chinese/original",
}

# Add future languages here only. The module will not be imported until that
# language is selected. Modules are relative to phrozen_dev.
KAOS_LANGUAGE_MODULES = {
    "en": ("lang.kaos_translations_en", "KAOS_TRANSLATIONS_EN"),
    "fr": ("lang.kaos_translations_fr", "KAOS_TRANSLATIONS_FR"),
    "zh": ("lang.kaos_translations_zh", "KAOS_TRANSLATIONS_ZH"),
}

_LOADED_TABLES = {}
_PLACEHOLDER_RE = re.compile(r"%(?:\([^)]+\))?[#0\- +]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?[diouxXeEfFgGcrs%]")
_TEMPLATE_CACHE = {}


def kaos_normalize_language(language):
    """Normalize user language input to en/fr/zh."""
    key = str(language or KAOS_DEFAULT_LANGUAGE).strip().lower()
    return KAOS_LANGUAGE_ALIASES.get(key, KAOS_DEFAULT_LANGUAGE)


def kaos_get_language_name(language):
    """Return a readable language name for status messages."""
    lang = kaos_normalize_language(language)
    return KAOS_LANGUAGE_NAMES.get(lang, KAOS_LANGUAGE_NAMES[KAOS_DEFAULT_LANGUAGE])


def _import_language_table(lang):
    """Lazy-load a language table. Returns {} if unavailable."""
    lang = kaos_normalize_language(lang)

    if lang in _LOADED_TABLES:
        return _LOADED_TABLES[lang]

    module_info = KAOS_LANGUAGE_MODULES.get(lang)
    if module_info is None:
        _LOADED_TABLES[lang] = {}
        return _LOADED_TABLES[lang]

    module_name, table_name = module_info

    try:
        # Relative import when running as part of klippy.extras.phrozen_dev.
        # Example: .lang.kaos_translations_en
        module = importlib.import_module("." + module_name, __package__)
        table = getattr(module, table_name, {})
    except Exception:
        # Fail open. Translation should never prevent printer startup.
        table = {}

    if not isinstance(table, dict):
        table = {}

    _LOADED_TABLES[lang] = table
    return table


def kaos_get_translation_table(language):
    """Return the selected language table, lazy-loaded on first use."""
    lang = kaos_normalize_language(language)
    if lang == "zh":
        # Original/vendor mode. Do not import any table.
        return {}
    return _import_language_table(lang)


def _apply_percent_template(source_template, target_template, text):
    """Translate already-formatted %-style vendor messages.

    Example:
      source_template = "发送命令: cmd=%s"
      target_template = "Sending command: cmd=%s"
      text            = "发送命令: cmd=E0"
    """
    key = source_template
    compiled = _TEMPLATE_CACHE.get(key)
    if compiled is None:
        parts = []
        last = 0
        placeholders = []
        for match in _PLACEHOLDER_RE.finditer(source_template):
            # Literal %% is not a value placeholder.
            if match.group(0) == "%%":
                parts.append(re.escape(source_template[last:match.end()]))
                last = match.end()
                continue
            parts.append(re.escape(source_template[last:match.start()]))
            parts.append("(.+?)")
            placeholders.append(match.group(0))
            last = match.end()
        parts.append(re.escape(source_template[last:]))
        compiled = re.compile("^" + "".join(parts) + "$"), placeholders
        _TEMPLATE_CACHE[key] = compiled

    pattern, placeholders = compiled
    match = pattern.match(text)
    if not match:
        return None

    result = target_template
    values = match.groups()
    for placeholder, value in zip(placeholders, values):
        result = result.replace(placeholder, value, 1)
    return result


def kaos_translate_message(message, language=KAOS_DEFAULT_LANGUAGE):
    """Return translated console text.

    Language behavior:
      en: lazy-load English table from ./lang/
      fr: lazy-load French table from ./lang/
      zh: original vendor Chinese text

    There is intentionally no fallback to English. If the selected language
    lacks a translation for a source string, the original text passes through.
    """
    text = str(message)
    lang = kaos_normalize_language(language)

    if lang == "zh":
        return text

    table = kaos_get_translation_table(lang)

    if text in table:
        return table[text]

    # Try %-style templates for the selected language only.
    for source, target in table.items():
        if "%" not in source:
            continue
        translated = _apply_percent_template(source, target, text)
        if translated is not None:
            return translated

    return text


def kaos_loaded_languages():
    """Return loaded language-table keys for diagnostics."""
    return tuple(sorted(_LOADED_TABLES.keys()))


def kaos_translation_counts(load_all=False):
    """Return translation-table counts for diagnostics.

    By default this reports only already-loaded tables so diagnostics do not
    accidentally load every language into memory. Pass load_all=True only when
    deliberately auditing all language files.
    """
    if load_all:
        for lang in KAOS_SUPPORTED_LANGUAGES:
            if lang != "zh":
                _import_language_table(lang)

    counts = {}
    for lang in KAOS_SUPPORTED_LANGUAGES:
        if lang == "zh":
            counts[lang] = 0
        elif lang in _LOADED_TABLES:
            counts[lang] = len(_LOADED_TABLES[lang])
        else:
            counts[lang] = None
    return counts
