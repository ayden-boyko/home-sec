# Home Security Camera System

A Raspberry Pi-based multi-camera home security system with web dashboard and real-time streaming.

## Architecture

- **Pi Zero 2W (Camera nodes)**: Capture video, encode H.264, stream via RTSP
- **Pi 4B (Controller)**: Aggregate RTSP streams, convert to HLS, serve web dashboard

## Features

- Multi-camera support (add/remove on the fly)
- Web-based dashboard
- Hardware H.264 encoding (efficient)
- Health monitoring (online/offline detection)
- Easy deployment (setup scripts included)

## Quick Start

### Pi Zero 2W Setup

```bash
cd pi-zero
./setup.sh
```

Check status:

```bash
sudo systemctl status camera-stream.service
sudo systemctl status health-endpoint.service
```

### Pi 4B Setup

```bash
cd pi4b
./setup.sh
```

Access dashboard:

http://<pi4b-ip>/dashboard.html

## Directory Structure
  
├── cam/  
│ ├── scripts/  
│ │ ├── camera-stream.sh # RTSP streaming  
│ │ └── health_endpoint.py # Health check endpoint  
│ ├── systemd/  
│ │ ├── camera-stream.service  
│ │ └── health-endpoint.service  
│ └── setup.sh # Automated setup  
├── controller/  
│ ├── scripts/  
│ │ └── camera_controller.py # Main controller (Flask)  
│ ├── systemd/  
│ │ └── camera-controller.service  
│ ├── web/  
│ │ └── dashboard.html # Web UI  
│ └── setup.sh # Automated setup  
└── README.md  
