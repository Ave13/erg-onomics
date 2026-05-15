#!/bin/bash
set -e
cd "$(dirname "$0")"
git pull origin main
sudo systemctl restart erg
echo "Done. Running: $(curl -s http://localhost:8501/api/version)"
