# Home Security Camera System

A Raspberry Pi-based multi-camera home security system with web dashboard and real-time streaming.
This system has several "smart" features:

- Flagged clips are passed to agents that then react accordingly.
  - Example: Cat is seen throwing up -> execution agent notifies home residents
- Frames with low confidence(50-70%) are saved and presented to the users to help classify, these frames are saved and then used to re-train the existing CV model. Naming people/pets in these frames trains the model to recognize them and not act off of false positives (ex: notifying of an intruder when its really just a friend)

![Home-Sec Workflow](/home-sec-workflow.png)

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

├──agent_hub/
| ├── agents/
| | ├── execution/ # agent that acts off of info from the frames
| ├── profiles/ # home resident's info
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
├── models/ # Where the CV models live, starts with the basic, grows as the model get retrained on data
└── README.md

## Running the Different Components

uv run --project cam python cam/scripts/health_check.py
uv run --project controller python controller/scripts/main.py
uv run --project agent_hub/agents/execution python agent_hub/agents/execution/actions.py
