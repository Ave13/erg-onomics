#!/usr/bin/env bash
# install.sh — Erg-onomics setup for Arduino UNO Q (Debian/Ubuntu ARM)
# Run once after cloning the repo:  bash install.sh

set -e
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="$USER"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${YELLOW}→${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }

[[ $EUID -eq 0 ]] && err "Run as your normal user, not root. (sudo is called internally)"

echo ""
echo "  Erg-onomics installer"
echo "  ─────────────────────"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
info "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3-pip python3-dbus python3-gi \
    espeak hostapd dnsmasq
ok "System packages installed"

# ── 2. Python packages ────────────────────────────────────────────────────────
info "Installing Python packages..."
pip install --quiet --break-system-packages \
    bleak bless fastapi "uvicorn[standard]"
ok "Python packages installed"

# ── 3. Bluetooth permission ───────────────────────────────────────────────────
if ! groups "$APP_USER" | grep -q bluetooth; then
    info "Adding $APP_USER to bluetooth group..."
    sudo usermod -aG bluetooth "$APP_USER"
    ok "Added to bluetooth group (takes effect after reboot)"
else
    ok "Already in bluetooth group"
fi

# ── 4. Detect WiFi interface ──────────────────────────────────────────────────
WLAN=$(ip link show | awk -F': ' '/^[0-9]+: w/{print $2; exit}')
[[ -z "$WLAN" ]] && err "No WiFi interface found. Check 'ip link show'."
ok "WiFi interface: $WLAN"

# ── 5. NetworkManager: stop managing the WiFi interface ───────────────────────
info "Configuring NetworkManager..."
sudo mkdir -p /etc/NetworkManager/conf.d
sudo tee /etc/NetworkManager/conf.d/10-erg-ap.conf > /dev/null <<EOF
[keyfile]
unmanaged-devices=interface-name:$WLAN
EOF
sudo systemctl reload NetworkManager 2>/dev/null || true
ok "NetworkManager configured"

# ── 6. Static IP for the WiFi interface ──────────────────────────────────────
info "Setting static IP 10.0.0.1 on $WLAN..."
sudo tee /etc/network/interfaces.d/"$WLAN" > /dev/null <<EOF
auto $WLAN
iface $WLAN inet static
  address 10.0.0.1
  netmask 255.255.255.0
EOF
ok "Static IP configured"

# ── 7. hostapd (WiFi access point) ───────────────────────────────────────────
info "Configuring WiFi access point (SSID: ErgRower)..."
sudo tee /etc/hostapd/hostapd.conf > /dev/null <<EOF
interface=$WLAN
ssid=ErgRower
hw_mode=g
channel=6
wpa=2
wpa_passphrase=rowrow12
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF
sudo sed -i 's|#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
ok "hostapd configured"

# ── 8. dnsmasq (DHCP for phones) ─────────────────────────────────────────────
info "Configuring DHCP server..."
sudo tee /etc/dnsmasq.conf > /dev/null <<EOF
interface=$WLAN
dhcp-range=10.0.0.10,10.0.0.50,255.255.255.0,24h
EOF
sudo systemctl enable dnsmasq
ok "dnsmasq configured"

# ── 9. Systemd service for the app ───────────────────────────────────────────
info "Creating erg systemd service..."
UVICORN_PATH="$(which uvicorn)"
[[ -z "$UVICORN_PATH" ]] && err "uvicorn not found in PATH after install"

sudo tee /etc/systemd/system/erg.service > /dev/null <<EOF
[Unit]
Description=Erg-onomics rowing app
After=network.target bluetooth.target hostapd.service

[Service]
User=$APP_USER
WorkingDirectory=$REPO_DIR
ExecStart=$UVICORN_PATH server:app --host 0.0.0.0 --port 8501
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable erg
ok "erg service enabled"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}  Installation complete!${NC}"
echo ""
echo "  After reboot:"
echo "    WiFi network : ErgRower"
echo "    Password     : rowrow12"
echo "    Open Safari  : http://10.0.0.1:8501"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status erg      # app status"
echo "    sudo journalctl -u erg -f      # live logs"
echo "    sudo systemctl restart erg     # restart after updates"
echo ""
read -rp "  Reboot now? [y/N] " REBOOT
if [[ "$REBOOT" =~ ^[Yy]$ ]]; then
    sudo reboot
else
    echo "  Run 'sudo reboot' when ready."
fi
