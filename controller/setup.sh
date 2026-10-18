#!/bin/bash
set -euo pipefail

# Always run from the script's own folder so relative paths work
cd "$(dirname "$0")"

echo "Setting up Pi4B controller..."

# Install dependencies
echo "Installing dependencies..."
sudo apt update
sudo apt install -y nginx python3-venv

# Create venv and install requirements
python3 -m venv "$HOME/camera_venv"
"$HOME/camera_venv/bin/pip" install -r requirements.txt

# Copy script
echo "Installing scripts..."
install -m 755 scripts/camera_controller.py "$HOME/camera_controller.py"

# Install systemd service
echo "Installing systemd service..."
sudo cp systemd/camera_controller.service /etc/systemd/system/

# Copy web dashboard (nginx only needs to read, so root-owned is fine)
echo "Installing web dashboard..."
sudo install -D -m 644 web/dashboard.html /var/www/html/dashboard.html

sudo mkdir -p /var/www/html/hls
sudo chown "$USER":"$USER" /var/www/html/hls

# Enable services
echo "Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable nginx camera_controller.service
sudo systemctl restart nginx camera_controller.service

echo "✓ Pi4B setup complete!"
echo "Access dashboard at: http://$(hostname -I | awk '{print $1}')/dashboard.html"