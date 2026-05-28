# Phrozen virtual_sdcard extensions for Arco touchscreen
#
# Patches mainline Klipper's virtual_sdcard to add:
#   - SDCARD_SELECT_FILE command (select without starting print)
#   - Subdirectory navigation via path parameter on get_file_list()
#
# These features are required by the Arco touchscreen (voronFDM) which
# browses subdirectories via Moonraker's gcode API.
#
# Copyright (C) 2024-2026  OlyForge3D
# This file may be distributed under the terms of the GNU GPLv3 license.
import os, logging

VALID_GCODE_EXTS = ["gcode", "g", "gco"]


def install(printer):
    """Patch the virtual_sdcard instance with Phrozen touchscreen features.

    Must be called after virtual_sdcard is loaded (i.e., from phrozen_dev init).
    """
    vsd = printer.lookup_object("virtual_sdcard", None)
    if vsd is None:
        logging.warning(
            "phrozen_sdcard_ext: [virtual_sdcard] not configured, skipping"
        )
        return

    # Store the base path for subdirectory navigation
    vsd._phrozen_base_path = vsd.sdcard_dirname
    vsd._phrozen_subdir = ""

    # Save reference to the original get_file_list
    _original_get_file_list = vsd.get_file_list

    def _enhanced_get_file_list(check_subdirs=False, path=""):
        """Extended get_file_list with subdirectory navigation.

        path="system" resets to the base gcodes directory.
        path="/subdir" changes the active directory for listing/loading.
        """
        if path == "system":
            vsd._phrozen_subdir = ""
            vsd.sdcard_dirname = vsd._phrozen_base_path
        elif path != "":
            target = vsd._phrozen_base_path + path
            if os.path.exists(target):
                vsd._phrozen_subdir = path
                vsd.sdcard_dirname = target
            else:
                return []

        # Delegate to mainline implementation for actual file listing
        return _original_get_file_list(check_subdirs)

    vsd.get_file_list = _enhanced_get_file_list

    # Register SDCARD_SELECT_FILE command (select without starting print)
    gcode = printer.lookup_object("gcode")

    def cmd_SDCARD_SELECT_FILE(gcmd):
        if vsd.work_timer is not None:
            raise gcmd.error("SD busy")
        vsd._reset_file()
        filename = gcmd.get("FILENAME")
        if filename[0] == "/":
            filename = filename[1:]
        vsd._load_file(gcmd, filename, check_subdirs=True)

    gcode.register_command(
        "SDCARD_SELECT_FILE",
        cmd_SDCARD_SELECT_FILE,
        desc="Select a SD file. May include files in subdirectories.",
    )

    logging.info("phrozen_sdcard_ext: patched virtual_sdcard with "
                 "subdirectory browsing and SDCARD_SELECT_FILE")
