#!/bin/sh
# KAOS_VERSION: v1.0 2026-06-09

# ARCO System Prep helper: conservative logging optimization for small eMMC systems.
# Includes journald caps, non-overlapping printer log rotation, old rotated-log cleanup, and nginx log-path repair.
# Does not install log2ram.

set -u

Optimize_Journald="${Optimize_Journald:-1}"
Rotate_Printer_Logs="${Rotate_Printer_Logs:-1}"
Rotate_Nginx_Logs="${Rotate_Nginx_Logs:-1}"
Clean_Old_Rotated_Logs="${Clean_Old_Rotated_Logs:-1}"
Journal_System_Max_Use="${Journal_System_Max_Use:-20M}"
Journal_Runtime_Max_Use="${Journal_Runtime_Max_Use:-20M}"
Journal_Max_File_Size="${Journal_Max_File_Size:-5M}"
Journal_Max_Retention="${Journal_Max_Retention:-7day}"

log() { echo "SYSTEM_LOGGING_OPTIMIZE: $*"; }

log_du() {
    path="$1"
    if [ -e "$path" ]; then
        du -sh "$path" 2>/dev/null | sed 's/^/SYSTEM_LOGGING_OPTIMIZE: du /'
    else
        log "du path_missing=$path"
    fi
}

configure_journald() {
    [ "$Optimize_Journald" = "1" ] || { log "journald_status=skipped_disabled"; return 0; }
    mkdir -p /etc/systemd/journald.conf.d 2>/dev/null || { log "journald_status=failed_mkdir_nonfatal"; return 0; }
    cat > /etc/systemd/journald.conf.d/99-arco-system-prep.conf <<EOF_JOURNALD
[Journal]
Storage=persistent
Compress=yes
SystemMaxUse=$Journal_System_Max_Use
RuntimeMaxUse=$Journal_Runtime_Max_Use
SystemMaxFileSize=$Journal_Max_File_Size
RuntimeMaxFileSize=$Journal_Max_File_Size
MaxRetentionSec=$Journal_Max_Retention
MaxLevelStore=warning
MaxLevelSyslog=warning
EOF_JOURNALD
    log "journald_status=config_written"
    log "journald_SystemMaxUse=$Journal_System_Max_Use"
    log "journald_MaxLevelStore=warning"
    if command -v systemctl >/dev/null 2>&1; then
        systemctl restart systemd-journald 2>/dev/null || log "journald_restart_status=failed_nonfatal"
    fi
    if command -v journalctl >/dev/null 2>&1; then
        journalctl --vacuum-size="$Journal_System_Max_Use" 2>/dev/null || log "journal_vacuum_size_status=failed_nonfatal"
        journalctl --vacuum-time="$Journal_Max_Retention" 2>/dev/null || log "journal_vacuum_time_status=failed_nonfatal"
    fi
}

remove_legacy_logrotate_rules() {
    # Older versions created a separate nginx rule that duplicated the stock rule.
    if [ -e /etc/logrotate.d/arco-nginx-logs ]; then
        rm -f /etc/logrotate.d/arco-nginx-logs 2>/dev/null \
            && log "legacy_nginx_logrotate_status=removed path=/etc/logrotate.d/arco-nginx-logs" \
            || log "legacy_nginx_logrotate_status=failed_remove_nonfatal"
    else
        log "legacy_nginx_logrotate_status=not_present"
    fi
}

quarantine_logrotate_rule() {
    rule_name="$1"
    reason="$2"
    src="/etc/logrotate.d/$rule_name"

    case "$rule_name" in
        ''|*/*|.*)
            log "logrotate_repair_status=skipped_unsafe_rule_name rule=$rule_name reason=$reason"
            return 0
            ;;
    esac

    if [ ! -f "$src" ]; then
        log "logrotate_repair_status=skipped_rule_not_found rule=$rule_name reason=$reason"
        return 0
    fi

    backup_dir="/etc/logrotate.d/kaos-disabled"
    mkdir -p "$backup_dir" 2>/dev/null || {
        log "logrotate_repair_status=failed_backup_dir_nonfatal rule=$rule_name reason=$reason"
        return 0
    }

    ts=$(date +%Y%m%d_%H%M%S)
    dst="$backup_dir/${rule_name}.${ts}.$$"
    if mv -f "$src" "$dst" 2>/dev/null; then
        log "logrotate_repair_status=quarantined rule=$rule_name reason=$reason backup=$dst"
    else
        log "logrotate_repair_status=failed_quarantine_nonfatal rule=$rule_name reason=$reason"
    fi
}

repair_logrotate_config_errors() {
    if ! command -v logrotate >/dev/null 2>&1; then
        log "logrotate_repair_status=skipped_not_installed"
        return 0
    fi

    pass=1
    repaired_any=0
    while [ "$pass" -le 6 ]; do
        validation_output="$(logrotate --debug /etc/logrotate.conf 2>&1)"
        validation_status=$?

        if [ "$validation_status" -eq 0 ] && ! printf '%s\n' "$validation_output" | grep -q '^error:'; then
            if [ "$repaired_any" -eq 1 ]; then
                log "logrotate_repair_status=completed_after_repairs passes=$pass"
            else
                log "logrotate_repair_status=no_repairs_needed"
            fi
            return 0
        fi

        error_rules="$(printf '%s\n' "$validation_output" \
            | sed -n 's/^error: \([^:/][^:]*\):[0-9][0-9]* .*$/\1/p' \
            | sort -u)"

        if [ -z "$error_rules" ]; then
            log "logrotate_repair_status=unhandled_errors_nonfatal pass=$pass"
            printf '%s\n' "$validation_output" | grep '^error:' | sed 's/^/SYSTEM_LOGGING_OPTIMIZE: logrotate_repair_unhandled_/'
            return 0
        fi

        repaired_this_pass=0
        for rule in $error_rules; do
            if [ -f "/etc/logrotate.d/$rule" ]; then
                # Prefer a working global logrotate run over keeping one broken
                # stock/vendor rule. The original file is preserved under
                # /etc/logrotate.d/kaos-disabled for audit/recovery.
                quarantine_logrotate_rule "$rule" "validation_error_pass_$pass"
                repaired_any=1
                repaired_this_pass=1
            else
                log "logrotate_repair_status=skipped_no_file_for_error rule=$rule pass=$pass"
            fi
        done

        if [ "$repaired_this_pass" -eq 0 ]; then
            log "logrotate_repair_status=no_actionable_rules_nonfatal pass=$pass"
            printf '%s\n' "$validation_output" | grep '^error:' | sed 's/^/SYSTEM_LOGGING_OPTIMIZE: logrotate_repair_remaining_/'
            return 0
        fi

        pass=$((pass + 1))
    done

    log "logrotate_repair_status=max_passes_reached_nonfatal"
    return 0
}

configure_printer_logrotate() {
    [ "$Rotate_Printer_Logs" = "1" ] || { log "printer_logrotate_status=skipped_disabled"; return 0; }
    mkdir -p /etc/logrotate.d 2>/dev/null || { log "printer_logrotate_status=failed_mkdir_nonfatal"; return 0; }

    tmp_file="/etc/logrotate.d/.arco-printer-logs.tmp.$$"
    cat > "$tmp_file" <<'EOF_ROTATE_PRINTER'
/home/*/printer_data/logs/klippy.log
/home/*/printer_data/logs/moonraker.log
/home/*/printer_data/logs/KlipperScreen.log
/home/*/printer_data/logs/moonraker-obico.log
{
    size 5M
    rotate 2
    missingok
    notifempty
    compress
    delaycompress
    copytruncate
}
EOF_ROTATE_PRINTER

    chmod 644 "$tmp_file" 2>/dev/null || true
    mv -f "$tmp_file" /etc/logrotate.d/arco-printer-logs 2>/dev/null || {
        rm -f "$tmp_file" 2>/dev/null || true
        log "printer_logrotate_status=failed_write_nonfatal"
        return 0
    }

    log "printer_logrotate_status=config_written path=/etc/logrotate.d/arco-printer-logs"
}

repair_nginx_log_paths() {
    [ "$Rotate_Nginx_Logs" = "1" ] || { log "nginx_log_path_status=skipped_disabled"; return 0; }

    mkdir -p /var/log/nginx 2>/dev/null || { log "nginx_log_path_status=failed_mkdir_nonfatal"; return 0; }
    chmod 755 /var/log/nginx 2>/dev/null || log "nginx_log_dir_chmod_status=failed_nonfatal"

    for logfile in access.log error.log; do
        touch "/var/log/nginx/$logfile" 2>/dev/null || {
            log "nginx_log_file_status=failed_create_nonfatal file=$logfile"
            continue
        }
        chmod 640 "/var/log/nginx/$logfile" 2>/dev/null || log "nginx_log_file_chmod_status=failed_nonfatal file=$logfile"
    done

    if id www-data >/dev/null 2>&1 && getent group adm >/dev/null 2>&1; then
        chown www-data:adm /var/log/nginx 2>/dev/null || log "nginx_log_dir_chown_status=failed_nonfatal"
        chown www-data:adm /var/log/nginx/access.log /var/log/nginx/error.log 2>/dev/null || log "nginx_log_file_chown_status=failed_nonfatal"
        log "nginx_log_owner=www-data:adm"
    else
        log "nginx_log_owner_status=unchanged_www-data_or_adm_missing"
    fi

    log "nginx_log_path_status=ready path=/var/log/nginx"
}

validate_logrotate_config() {
    if ! command -v logrotate >/dev/null 2>&1; then
        log "logrotate_validation_status=skipped_not_installed"
        return 0
    fi

    validation_output="$(logrotate --debug /etc/logrotate.conf 2>&1)"
    validation_status=$?

    if [ "$validation_status" -ne 0 ] || printf '%s\n' "$validation_output" | grep -q '^error:'; then
        # "destination ... already exists, skipping rotation" is logrotate's
        # standard same-day-double-rotation notice, not a malformed rule --
        # it shows up whenever this validation step (or the helper itself)
        # runs more than once on the same calendar day after an earlier
        # rotation already produced today's dateext-named file. Distinguish
        # it from genuine config errors so the log doesn't read as a defect
        # every time someone re-runs this helper same-day. Only downgrade
        # when EVERY error: line is this benign type -- a real error mixed
        # in alongside it must still surface as failed_nonfatal.
        error_lines="$(printf '%s\n' "$validation_output" | grep '^error:')"
        if [ -n "$error_lines" ] && ! printf '%s\n' "$error_lines" | grep -qv '^error: destination .* already exists, skipping rotation$'; then
            log "logrotate_validation_status=warning_same_day_rotation_already_present"
            printf '%s\n' "$error_lines" | sed 's/^/SYSTEM_LOGGING_OPTIMIZE: logrotate_validation_/'
            return 0
        fi
        log "logrotate_validation_status=failed_nonfatal"
        printf '%s\n' "$validation_output" | grep '^error:' | sed 's/^/SYSTEM_LOGGING_OPTIMIZE: logrotate_validation_/'
        return 0
    fi

    log "logrotate_validation_status=passed"
    return 0
}

clean_old_logs() {
    [ "$Clean_Old_Rotated_Logs" = "1" ] || { log "old_rotated_log_cleanup_status=skipped_disabled"; return 0; }
    for base in /home/mks/printer_data/logs /home/prz/printer_data/logs; do
        if [ -d "$base" ]; then
            find "$base" -type f \( -name '*.gz' -o -name '*.old' -o -name '*.1' -o -name '*.2' -o -name '*.3' \) -mtime +14 -print -delete 2>/dev/null | sed 's/^/SYSTEM_LOGGING_OPTIMIZE: old_log_deleted=/'
        fi
    done
    log "old_rotated_log_cleanup_status=completed"
}

log "script_started_at=$(date)"
log "disk_before_begin"
df -h / 2>/dev/null || true
log_du /var/log
log_du /home/mks/printer_data/logs
log_du /home/prz/printer_data/logs
log "disk_before_end"

configure_journald
remove_legacy_logrotate_rules
configure_printer_logrotate
repair_nginx_log_paths
clean_old_logs
repair_logrotate_config_errors

validate_logrotate_config

log "disk_after_begin"
df -h / 2>/dev/null || true
log_du /var/log
log_du /home/mks/printer_data/logs
log_du /home/prz/printer_data/logs
log "disk_after_end"
log "log2ram_status=not_used"
log "script_finished_at=$(date)"
exit 0
