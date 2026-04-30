#!/bin/sh

TARGET_DIR="/home/prz/klipper/klippy/extras/phrozen_dev"
CONFIG_DIR="/home/prz/printer_data/config"
timestamp=$(date +%Y%m%d_%H%M%S)

backup_file() {
    file="$1"
    if [ -f "$file" ]; then
        if [ ! -f "$file.bak" ]; then
            cp -f "$file" "$file.bak" || exit 1
        else
            cp -f "$file" "$file.$timestamp.bak" || exit 1
        fi
    fi
}

# Backup existing files without removing the working copy first.
backup_file "$TARGET_DIR/dev.py"
backup_file "$TARGET_DIR/kaos_logging.py"
backup_file "$TARGET_DIR/kaos_translations.py"

backup_file "$CONFIG_DIR/printer.cfg"
backup_file "$CONFIG_DIR/printer_gcode_macro.cfg"

# Copy only patched Python files.
cp -f /tmp/phrozen_dev/dev.py "$TARGET_DIR/dev.py" || exit 1

#  Copy New KAOS files
cp -f /tmp/phrozen_dev/kaos_logging.py "$TARGET_DIR/kaos_logging.py" || exit 1
cp -f /tmp/phrozen_dev/kaos_translations.py "$TARGET_DIR/kaos_translations.py" || exit 1

# Copy/make lang directory
mkdir -p "$TARGET_DIR/lang" || exit 1
cp -a /tmp/phrozen_dev/lang/. "$TARGET_DIR/lang/" || exit 1

# copy cfg files
cp -f /tmp/phrozen_dev/kaos.cfg "$CONFIG_DIR/" || exit 1
cp -f /tmp/phrozen_dev/kaos_menu.cfg "$CONFIG_DIR/" || exit 1
cp -f /tmp/phrozen_dev/printer.cfg "$CONFIG_DIR/" || exit 1
cp -f /tmp/phrozen_dev/printer_gcode_macro.cfg "$CONFIG_DIR/" || exit 1

chmod 644 "$TARGET_DIR/dev.py" || exit 1
chmod 644 "$TARGET_DIR/cmds.py" || exit 1
chmod 644 "$TARGET_DIR/kaos_logging.py" || exit 1
chmod 644 "$TARGET_DIR/kaos_translations.py" || exit 1

chmod 755 "$TARGET_DIR/lang" || exit 1
chmod 644 "$TARGET_DIR/lang/"*.py || exit 1
chmod 644 "$CONFIG_DIR/kaos.cfg" || exit 1
chmod 644 "$CONFIG_DIR/kaos_menu.cfg" || exit 1
chmod 644 "$CONFIG_DIR/printer.cfg" || exit 1
chmod 644 "$CONFIG_DIR/printer_gcode_macro.cfg" || exit 1



echo "KAOS Created"
exit 0
