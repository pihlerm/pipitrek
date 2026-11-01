#!/usr/bin/env bash
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
    echo "Run this installer as root: sudo $0" >&2
    exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

require_file() {
    [[ -f "$1" ]] || {
        echo "Required file not found: $1" >&2
        exit 1
    }
}

service_source="$script_dir/pipitrek.service"
service_source_ip="$script_dir/pipitreklocal-ip.service"
service_source_mode="$script_dir/pipitreklocal-mode.service"
dropin_source="$script_dir/pipitreklocal.conf"
dnsmasq_source="$script_dir/pipitreklocal-dnsmasq.conf"
mode_script_source="$script_dir/wlan-mode.sh"

require_file "$service_source"
require_file "$service_source_ip"
require_file "$service_source_mode"
require_file "$dropin_source"
require_file "$dnsmasq_source"
require_file "$mode_script_source"

install -D -m 0644 "$service_source" /etc/systemd/system/pipitrek.service
install -D -m 0644 "$service_source_ip" /etc/systemd/system/pipitreklocal-ip.service
install -D -m 0644 "$service_source_mode" /etc/systemd/system/pipitreklocal-mode.service
install -D -m 0644 "$dropin_source" /etc/systemd/system/hostapd.service.d/pipitreklocal.conf
install -D -m 0644 "$dnsmasq_source" /etc/dnsmasq.d/pipitreklocal.conf
install -D -m 0755 "$mode_script_source" /usr/local/sbin/wlan-mode.sh

# Remove the old dnsmasq systemd drop-in used by an earlier configuration.
rm -f /etc/systemd/system/dnsmasq.service.d/pipitreklocal.conf
rmdir --ignore-fail-on-non-empty /etc/systemd/system/dnsmasq.service.d 2>/dev/null || true

# Remove the Wi-Fi stanza from ifupdown. It made networking.service fail
# whenever the optional USB adapter was absent. Preserve eth0 and all lines
# outside the exact old Wi-Fi/NAT block.
interfaces_file=/etc/network/interfaces
if [[ -f "$interfaces_file" ]] \
   && grep -q '^# WiFi$' "$interfaces_file" \
   && grep -q '^up ip6tables-restore < /etc/iptables.ipv6.nat$' "$interfaces_file"; then
    backup_file=/etc/network/interfaces.pipitreklocal-backup
    if [[ ! -e "$backup_file" ]]; then
        cp -a "$interfaces_file" "$backup_file"
        echo "Backed up original interfaces file to $backup_file"
    fi
    sed -i '/^# WiFi$/,/^up ip6tables-restore < \/etc\/iptables\.ipv6\.nat$/d' "$interfaces_file"
    echo "Removed the old wlan0 ifupdown stanza; eth0 configuration was preserved."
fi

# Default to hotspot only on first install; preserve the user's selected mode.
if [[ ! -e /etc/pipitreklocal-mode ]]; then
    printf 'hotspot\n' > /etc/pipitreklocal-mode
    chmod 0644 /etc/pipitreklocal-mode
fi
case "$(tr -d '[:space:]' < /etc/pipitreklocal-mode)" in
    hotspot|wlan|off) ;;
    *)
        echo "Invalid mode in /etc/pipitreklocal-mode; expected hotspot, wlan, or off." >&2
        exit 1
        ;;
esac

systemctl daemon-reload

# These services are controlled by wlan-mode.sh, not started independently at boot.
systemctl stop hostapd.service dnsmasq.service pipitreklocal-ip.service 2>/dev/null || true
systemctl disable hostapd.service dnsmasq.service pipitreklocal-ip.service 2>/dev/null || true

systemctl enable pipitrek.service
systemctl enable pipitreklocal-mode.service

# Apply the saved mode now. If the optional dongle is absent, this exits
# successfully in restore mode and leaves Ethernet alone.
 /usr/local/sbin/wlan-mode.sh --restore

echo "Pipitrek service installed and enabled."
echo "Wi-Fi mode restore service installed and enabled."
echo "Selected Wi-Fi mode: $(tr -d '[:space:]' < /etc/pipitreklocal-mode)"
echo "Switch modes with: sudo /usr/local/sbin/wlan-mode.sh {hotspot|wlan|off}"
