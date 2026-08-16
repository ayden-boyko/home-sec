#!/usr/bin/env python3
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import subprocess
import os
import threading
import requests
from datetime import datetime
import time
import camera_controller as CC

app = Flask(__name__)
CORS(app)

DB_FILE = os.path.expanduser("~/cameras.db")
HLS_BASE = "/var/www/html" 

if __name__ == '__main__':
    Cam_Controller: CC.CameraController = CC.CameraController(DB_FILE, HLS_BASE)
    health_thread = threading.Thread(target=Cam_Controller.health_check_loop, daemon=True)
    health_thread.start()

    Cam_Controller.run()


