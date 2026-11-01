#!/usr/bin/env bash
set -euo pipefail

MODE_FILE="/etc/pipitreklocal-mode"
WIFI_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
WPA_PID_FILE="/run/pipitreklocal-wpa.pid"
DHCLIENT_PID_FILE="/run/pipitreklocal-dhclient.pid"
DHCLIENT_LEASE_FILE="/var/lib/dhcp/dhclient-pipitreklocal-wlan0.leases"
WAIT_SECONDS=10

log() {
    echo "wlan-mode: $*"
    logger -t wlan-mode -- "$*" 2>/dev/null || true
}

usage() {
    echo "Usage: $0 {hotspot|wlan|off}"
    echo "       $0 --restore"
}

if [[ "$EUID" -ne 0 ]]; then
    echo "Run as root: sudo $0 {hotspot|wlan|off}" >&2
    exit 1
fi

stop_client() {
    if ip link show dev wlan0 >/dev/null 2>&1; then
        dhclient -r -pf "$DHCLIENT_PID_FILE" -lf "$DHCLIENT_LEASE_FILE" wlan0 >/dev/null 2>&1 || true
    fi

    if [[ -r "$WPA_PID_FILE" ]]; then
        local pid
        pid="$(cat "$WPA_PID_FILE" 2>/dev/null || true)"
        if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
            if [[ "$(ps -p "$pid" -o comm= 2>/dev/null | tr -d ' ')" == "wpa_supplicant" ]]; then
                kill -TERM "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$WPA_PID_FILE"
    fi
    rm -f "$DHCLIENT_PID_FILE"
}

stop_mode_services() {
    systemctl stop hostapd.service 2>/dev/null || true
    systemctl stop dnsmasq.service 2>/dev/null || true
    systemctl stop pipitreklocal-ip.service 2>/dev/null || true
    stop_client
}

remove_hotspot_nat() {
    if command -v iptables >/dev/null 2>&1; then
        iptables -D FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
        iptables -D FORWARD -i wlan0 -o eth0 -j ACCEPT 2>/dev/null || true
        iptables -t nat -D POSTROUTING -s 192.168.42.0/24 -o eth0 -j MASQUERADE 2>/dev/null || true
    fi
    if command -v ip6tables >/dev/null 2>&1; then
        ip6tables -D FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
        ip6tables -D FORWARD -i wlan0 -o eth0 -j ACCEPT 2>/dev/null || true
        ip6tables -t nat -D POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null || true
    fi
}

add_rule_once() {
    local bin="$1"
    shift
    "$bin" -C "$@" >/dev/null 2>&1 || "$bin" -A "$@"
}

add_nat_rule() {
    local bin="$1"
    shift
    "$bin" -t nat -C "$@" >/dev/null 2>&1 || "$bin" -t nat -A "$@"
}

add_hotspot_nat() {
    if ! ip link show dev eth0 >/dev/null 2>&1; then
        log "eth0 is absent; hotspot will work locally, but Ethernet internet sharing is unavailable."
        return 0
    fi

    if command -v iptables >/dev/null 2>&1; then
        add_rule_once iptables FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
        add_rule_once iptables FORWARD -i wlan0 -o eth0 -j ACCEPT
        add_nat_rule iptables POSTROUTING -s 192.168.42.0/24 -o eth0 -j MASQUERADE
        sysctl -w net.ipv4.ip_forward=1 >/dev/null
    else
        log "iptables not found; skipping IPv4 internet sharing rules."
    fi

    if command -v ip6tables >/dev/null 2>&1; then
        add_rule_once ip6tables FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
        add_rule_once ip6tables FORWARD -i wlan0 -o eth0 -j ACCEPT
        add_nat_rule ip6tables POSTROUTING -o eth0 -j MASQUERADE
    fi
}

wait_for_wlan() {
    local n
    for ((n=0; n<WAIT_SECONDS; n++)); do
        if ip link show dev wlan0 >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

save_mode() {
    local mode="$1"
    printf '%s\n' "$mode" > "$MODE_FILE"
    chmod 0644 "$MODE_FILE"
}

apply_mode() {
    local mode="$1"
    local restoring="${2:-no}"

    stop_mode_services
    remove_hotspot_nat

    if [[ "$mode" == "off" ]]; then
        if ip link show dev wlan0 >/dev/null 2>&1; then
            ip -4 addr flush dev wlan0
            ip link set dev wlan0 down
        fi
        log "Wi-Fi mode set to off."
        return 0
    fi

    if ! wait_for_wlan; then
        if [[ "$restoring" == "yes" ]]; then
            log "Saved mode is '$mode', but wlan0 is absent. Leaving Wi-Fi inactive; Ethernet is unaffected."
            return 0
        fi
        log "Saved mode '$mode', but wlan0 is absent. The selection will be restored on boot; connect the USB dongle and rerun this command."
        return 1
    fi

    ip link set dev wlan0 up
    ip -4 addr flush dev wlan0

    case "$mode" in
        hotspot)
            systemctl start pipitreklocal-ip.service
            systemctl start hostapd.service
            systemctl start dnsmasq.service
            add_hotspot_nat
            log "Hotspot mode active (192.168.42.1/24)."
            ;;
        wlan)
            if [[ ! -r "$WIFI_CONF" ]]; then
                log "Wi-Fi client configuration not found: $WIFI_CONF"
                return 1
            fi
            mkdir -p /run/wpa_supplicant /var/lib/dhcp
            wpa_supplicant -B -P "$WPA_PID_FILE" -i wlan0 -c "$WIFI_CONF"
            local n
            for ((n=0; n<20; n++)); do
                if wpa_cli -i wlan0 status 2>/dev/null | grep -q '^wpa_state=COMPLETED$'; then
                    break
                fi
                sleep 1
            done
            dhclient -pf "$DHCLIENT_PID_FILE" -lf "$DHCLIENT_LEASE_FILE" wlan0
            if wpa_cli -i wlan0 status 2>/dev/null | grep -q '^wpa_state=COMPLETED$'; then
                log "Wi-Fi client connected; DHCP requested."
            else
                log "Wi-Fi client has not associated yet; dhclient is running and will retry."
            fi
            ;;
        *)
            log "Invalid mode: $mode"
            usage
            return 2
            ;;
    esac
}

restore_mode() {
    local mode="hotspot"
    if [[ -r "$MODE_FILE" ]]; then
        mode="$(tr -d '[:space:]' < "$MODE_FILE")"
    else
        save_mode "$mode"
    fi
    case "$mode" in
        hotspot|wlan|off) ;;
        *)
            log "Invalid saved mode '$mode' in $MODE_FILE; refusing to guess."
            return 1
            ;;
    esac
    apply_mode "$mode" yes
}

if [[ "${1:-}" == "--restore" ]]; then
    [[ "$#" -eq 1 ]] || { usage >&2; exit 2; }
    restore_mode
    exit $?
fi

if [[ "$#" -ne 1 ]]; then
    usage >&2
    exit 2
fi

case "$1" in
    hotspot|wlan|off)
        save_mode "$1"
        apply_mode "$1" no
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
