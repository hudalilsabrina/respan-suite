#!/usr/bin/env bash
set -e

echo "=== Installing Respan Suite Dependencies ==="

# 1. System packages for headless anti-detect Firefox
echo "[1/4] Installing system libraries..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq || true
    sudo apt-get install -y -qq \
        libgtk-3-0 libasound2 libx11-xcb1 libxcomposite1 \
        libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 \
        libpango-1.0-0 libcairo2 libatk1.0-0 libnss3 libnspr4 \
        curl ca-certificates sqlite3 >/dev/null 2>&1 || true
fi

# 2. Python dependencies
echo "[2/4] Installing Python packages..."
python3 -m pip install -q -r requirements.txt

# 3. Camoufox browser binaries
echo "[3/4] Downloading anti-detect browser binaries..."
python3 -m camoufox fetch

# 4. Make scripts executable
echo "[4/4] Setting permissions..."
chmod +x respan_farm.py

echo ""
echo "=== Installation Complete! ==="
echo "Run generator: ./respan_farm.py -n 1"
