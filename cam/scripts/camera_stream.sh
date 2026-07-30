#!/bin/bash
set -e

# Kill any existing processes
pkill -f rpicam-vid || true
pkill -f "ffmpeg.*rtsp" || true
sleep 1

# Stream camera via RTSP
rpicam-vid \
  -t 0 \
  --width 1280 \
  --height 720 \
  --framerate 12 \
  --codec h264 \
  --bitrate 2000k \
  --nopreview \
  -o - | \
ffmpeg \
  -fflags nobuffer \
  -i pipe: \
  -c:v copy \
  -f rtsp \
  rtsp://0.0.0.0:5000/stream