#!/usr/bin/env bash

set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
    echo "Run this installer as root: sudo $0" >&2
    exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
service_source="$script_dir/pipitrek.service"
service_destination="/etc/systemd/system/pipitrek.service"

if [[ ! -f "$service_source" ]]; then
    echo "Service file not found: $service_source" >&2
    exit 1
fi

install -D -m 0644 "$service_source" "$service_destination"
systemctl daemon-reload
systemctl enable pipitrek.service

echo "PipiTrek service installed and enabled."
echo "Start it now with: sudo systemctl start pipitrek.service"