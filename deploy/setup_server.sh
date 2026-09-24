#!/bin/bash
# Server Setup Script for 24/7 Investing.com -> Google Sheets Sync

set -e

echo "=================================================="
echo "Installing Dependencies for Investing.com Sync"
echo "=================================================="

# Update package lists
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git curl wget build-essential

# Create Virtual Environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Upgrade pip and install Python requirements
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Install Playwright dependencies & Chromium browser
.venv/bin/python -m playwright install-deps
.venv/bin/python -m playwright install chromium

# Copy and enable Systemd 24/7 Background Service
echo "Setting up 24/7 background systemd service..."
sudo cp deploy/investing-sync.service /etc/systemd/system/investing-sync.service
sudo systemctl daemon-reload
sudo systemctl enable investing-sync.service
sudo systemctl restart investing-sync.service

echo "=================================================="
echo "SUCCESS! 24/7 Investing Sync is running!"
echo "Check logs anytime with: sudo journalctl -u investing-sync.service -f"
echo "=================================================="
