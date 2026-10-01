#!/usr/bin/env bash
# Dừng riêng web để database và tệp tải lên cùng một thời điểm; luôn mở lại nếu web đã chạy.
set -euo pipefail
umask 077
project=/home/ubuntu/peto-web
output=/home/ubuntu/peto-backups
marker=/run/peto-backup-restart
if [[ "${1:-}" == "--resume" ]]; then
    if [[ -f "$marker" ]]; then
        systemctl start peto-web.service
        rm -- "$marker"
    fi
    exit 0
fi
was_active=0
if systemctl is-active --quiet peto-web.service; then
    was_active=1
    touch "$marker"
fi
restart_web() {
    if [[ "$was_active" == 1 ]]; then
        systemctl start peto-web.service
        rm -f -- "$marker"
    fi
}
trap restart_web EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
systemctl stop peto-web.service
cd "$project/backend"
runuser -u ubuntu -- "$project/.venv/bin/python" -m ops.backup create --offline --output "$output" --keep 7
