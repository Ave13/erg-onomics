#!/bin/bash
set -e
cd "$(dirname "$0")"
git pull origin main
sudo systemctl restart erg
PROTO=http
[ -f cert.pem ] && PROTO=https
echo "Done. Running: $(curl -sk ${PROTO}://localhost:8501/api/version)"
