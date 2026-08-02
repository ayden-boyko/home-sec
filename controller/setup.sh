#!/bin/bash
set -e

echo "Setting up Pi4B controller..."

# Install dependencies
echo "Installing dependencies..."
sudo apt update
sudo apt install -y nginx
pip install --break-system-packages flask flask-cors requests

# Copy scripts
echo "Installing scripts..."
cp scripts/camera_controller.py ~/camera_controller.py
chmod +x ~/camera_controller.py

# Install systemd service
echo "Installing systemd service..."
sudo cp systemd/camera_controller.service /etc/systemd/system/

# Copy web dashboard
echo "Installing web dashboard..."
sudo mkdir -p /var/www/html
sudo cp web/dashboard.html /var/www/html/dashboard.html

# Enable services
echo "Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable nginx camera_controller.service
sudo systemctl start nginx camera_controller.service

echo "✓ Pi4B setup complete!"
echo ""
echo "Access dashboard at: http://$(hostname -I | awk '{print $1}')/dashboard.html"