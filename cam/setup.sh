#!/bin/bash
set -e

echo "Setting up Pi Zero camera stream..."

# Install dependencies
echo "Installing dependencies..."
pip install --break-system-packages flask

# Copy scripts to correct locations
echo "Installing scripts..."
sudo cp scripts/camera_stream.sh /usr/local/bin/camera_stream.sh
sudo chmod +x /usr/local/bin/camera_stream.sh

cp scripts/health_check.py ~/$USER/health_check.py

# Install systemd services
echo "Installing systemd services..."
sudo cp systemd/camera_stream.service /etc/systemd/system/
sudo cp systemd/health_check.service /etc/systemd/system/

# Enable and start services
echo "Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable camera_stream.service health_check.service
sudo systemctl start camera_stream.service health_check.service

echo "✓ Pi Zero setup complete!"
echo ""
echo "Check status with:"
echo "  sudo systemctl status camera_stream.service"
echo "  sudo systemctl status health_check.service"
