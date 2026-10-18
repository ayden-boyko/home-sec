#!/bin/bash
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

if [ "$EUID" -ne 0 ]; then
  echo "Run with sudo: sudo ./setup.sh" >&2
  exit 1
fi

echo "Setting up Pi Zero camera stream..."

echo "Installing dependencies..."
apt-get update
apt-get install -y python3-flask   # add python3-picamera2 if used

echo "Installing scripts..."
install -m 0755 scripts/camera_stream.py /usr/local/bin/camera_stream.py
install -m 0755 scripts/health_check.py /usr/local/bin/health_check.py

echo "Installing systemd services..."
install -m 0644 systemd/camera_stream.service systemd/health_check.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable camera_stream.service health_check.service
systemctl restart camera_stream.service health_check.service

echo "✓ Pi Zero setup complete!"
echo "Check status with:"
echo "  systemctl status camera_stream.service health_check.service"