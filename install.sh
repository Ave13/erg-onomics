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
    espeak avahi-daemon
ok "System packages installed"

# ── 2. Python packages ────────────────────────────────────────────────────────
info "Installing Python packages..."
# Ensure ~/.local/bin is on PATH for this session
export PATH="$HOME/.local/bin:$PATH"
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
WLAN=$(nmcli -t -f DEVICE,TYPE dev 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')
[[ -z "$WLAN" ]] && WLAN=$(ip link show | awk -F': ' '/^[0-9]+: w/{print $2; exit}')
[[ -z "$WLAN" ]] && err "No WiFi interface found."
ok "WiFi interface: $WLAN"

# ── 5. Remove old AP-mode config (hostapd/dnsmasq/static IP) if present ───────
info "Cleaning up old AP config if present..."
sudo systemctl stop  hostapd dnsmasq 2>/dev/null || true
sudo systemctl disable hostapd dnsmasq 2>/dev/null || true
sudo rm -f /etc/NetworkManager/conf.d/10-erg-ap.conf
sudo rm -f /etc/network/interfaces.d/"$WLAN"
# Re-enable NM management of the WiFi interface
sudo systemctl restart NetworkManager
sleep 3
ok "Old config removed"

# ── 6. Set hostname for mDNS (access via http://erg.local:8501) ───────────────
info "Setting hostname to 'erg'..."
sudo hostnamectl set-hostname erg
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon 2>/dev/null || true
ok "Hostname: erg  (access via http://erg.local:8501 on home WiFi)"

# ── 7. ErgRower hotspot — NetworkManager fallback AP ─────────────────────────
# NM tries saved networks first (priority 0); ErgRower AP is last resort (-999).
# When no known network is in range the board starts its own hotspot automatically.
info "Configuring ErgRower hotspot (AP fallback)..."
sudo nmcli con delete ErgRower 2>/dev/null || true
sudo nmcli con add \
    type wifi \
    con-name "ErgRower" \
    ifname "$WLAN" \
    802-11-wireless.ssid "ErgRower" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless-security.key-mgmt wpa-psk \
    802-11-wireless-security.psk "rowrow12" \
    ipv4.method shared \
    ipv4.addresses "10.0.0.1/24" \
    ipv6.method ignore \
    connection.autoconnect yes \
    connection.autoconnect-priority -999
ok "ErgRower hotspot configured (SSID: ErgRower / password: rowrow12)"

# ── 8. Allow app to manage WiFi via nmcli without a password prompt ───────────
info "Configuring WiFi management permissions..."
sudo tee /etc/sudoers.d/erg-wifi > /dev/null <<EOF
$APP_USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli
EOF
sudo chmod 440 /etc/sudoers.d/erg-wifi
ok "WiFi permissions configured"

# ── 9. Systemd service for the app ───────────────────────────────────────────
info "Creating erg systemd service..."
# Use 'python3 -m uvicorn' so the PATH to ~/.local/bin doesn't matter
PYTHON_PATH="$(which python3)"

sudo tee /etc/systemd/system/erg.service > /dev/null <<EOF
[Unit]
Description=Erg-onomics rowing app
After=network.target bluetooth.target

[Service]
User=$APP_USER
WorkingDirectory=$REPO_DIR
Environment="PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PYTHON_PATH -m uvicorn server:app --host 0.0.0.0 --port 8501
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable erg
sudo systemctl restart erg
ok "erg service installed and running"

# Allow the app user to restart the erg service without a password
echo "$APP_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart erg, /bin/systemctl stop erg, /bin/systemctl start erg, /usr/bin/systemctl restart erg, /usr/bin/systemctl stop erg, /usr/bin/systemctl start erg" \
  | sudo tee /etc/sudoers.d/erg-service > /dev/null
sudo chmod 440 /etc/sudoers.d/erg-service
ok "sudoers rule added — 'sudo systemctl restart erg' needs no password"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}  Installation complete!${NC}"
echo ""
echo "  WiFi behaviour after reboot:"
echo "    Known network in range  →  joins it automatically"
echo "    No known network        →  starts ErgRower hotspot"
echo ""
echo "  Connecting:"
echo "    Home WiFi  : http://erg.local:8501"
echo "    ErgRower AP: connect to ErgRower (rowrow12) → http://10.0.0.1:8501"
echo ""
echo "  Add networks via the app: Row → Profile → WiFi"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status erg      # app status"
echo "    sudo journalctl -u erg -f      # live logs"
echo "    sudo systemctl restart erg     # restart after updates"
echo "    nmcli con show                 # saved networks"
echo ""
read -rp "  Reboot now? [y/N] " REBOOT
if [[ "$REBOOT" =~ ^[Yy]$ ]]; then
    sudo reboot
else
    echo "  Run 'sudo reboot' when ready."
fi
