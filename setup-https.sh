#!/usr/bin/env bash
# Generate a self-signed TLS cert so getUserMedia works on non-localhost devices.
# Run once on the UNO Q, then install cert.pem on your iPhone:
#   Settings → General → VPN & Device Management → install cert.pem → trust it.
set -e
cd "$(dirname "$0")"

if [ -f cert.pem ] && [ -f key.pem ]; then
  echo "cert.pem and key.pem already exist. Delete them first to regenerate."
  exit 0
fi

openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 3650 -nodes \
  -subj "/CN=erg.local" \
  -addext "subjectAltName=DNS:erg.local,DNS:localhost,IP:192.168.0.224,IP:127.0.0.1"

chmod 600 key.pem
echo ""
echo "Done. Next steps:"
echo "  1. Copy cert.pem to your iPhone (AirDrop or email it to yourself)."
echo "  2. Open the file on iPhone → Settings → General → VPN & Device Management → install → trust."
echo "  3. Run restart.sh — the app will now serve on https://erg.local:8501"
echo "  4. Camera and video recording will work in Safari."
