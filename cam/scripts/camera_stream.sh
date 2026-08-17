#!/bin/bash
set -e

pkill -f rpicam-vid || true
sleep 1

# Output H.264 to TCP socket that Pi 4B will connect to
rpicam-vid \
  -t 0 \
  --width 1280 \
  --height 720 \
  --framerate 12 \
  --codec h264 \
  --bitrate 2000k \
  --nopreview \
  --inline \
  --listen \
  --output "tcp://0.0.0.0:5000"