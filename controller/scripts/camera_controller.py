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

app = Flask(__name__)
CORS(app)

DB_FILE = os.path.expanduser("~/cameras.db")
HLS_BASE = "/var/www/html"

# DATABASE 

def init_db():
    """Create database if it doesn't exist"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cameras (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            ip TEXT NOT NULL UNIQUE,
            port INTEGER DEFAULT 5000,
            enabled INTEGER DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS streams (
            camera_id INTEGER PRIMARY KEY,
            process_id INTEGER,
            FOREIGN KEY(camera_id) REFERENCES cameras(id)
        )
    ''')
    conn.commit()
    conn.close()

def get_cameras():
    """List all cameras"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, name, ip, port, enabled, last_seen FROM cameras')
    cameras = [
        {
            'id': row[0],
            'name': row[1],
            'ip': row[2],
            'port': row[3],
            'enabled': bool(row[4]),
            'last_seen': row[5],
            'status': 'online' if row[5] and (datetime.now() - datetime.fromisoformat(row[5])).total_seconds() < 30 else 'offline'
        }
        for row in c.fetchall()
    ]
    conn.close()
    return cameras

def add_camera(name, ip, port=5000):
    """Add a new camera"""
    try:
        requests.get(f'http://{ip}:8000/health', timeout=2)
    except:
        return False, "Cannot reach camera at this IP"
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO cameras (name, ip, port) VALUES (?, ?, ?)', (name, ip, port))
        conn.commit()
        camera_id = c.lastrowid
        conn.close()
        start_stream(camera_id, ip, port)
        return True, f"Camera added (ID: {camera_id})"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Camera with this IP already exists"

def remove_camera(camera_id):
    """Remove a camera"""
    stop_stream(camera_id)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM cameras WHERE id = ?', (camera_id,))
    conn.commit()
    conn.close()
    return True, "Camera removed"

#  STREAM MANAGEMENT

def start_stream(camera_id, camera_ip, camera_port):
    """Start RTSP→HLS conversion for a camera"""
    hls_dir = f"{HLS_BASE}/cam{camera_id}"
    os.makedirs(hls_dir, exist_ok=True)
    
    cmd = [
        'ffmpeg',
        '-fflags', 'nobuffer',
        '-rtsp_transport', 'tcp',
        '-i', f'rtsp://{camera_ip}:{camera_port}/stream',
        '-c:v', 'copy',
        '-f', 'hls',
        '-hls_time', '2',
        '-hls_list_size', '3',
        f'{hls_dir}/stream.m3u8'
    ]
    
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO streams (camera_id, process_id) VALUES (?, ?)', (camera_id, proc.pid))
    conn.commit()
    conn.close()
    
    print(f"Started stream for camera {camera_id} (PID: {proc.pid})")

def stop_stream(camera_id):
    """Stop RTSP→HLS conversion for a camera"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT process_id FROM streams WHERE camera_id = ?', (camera_id,))
    row = c.fetchone()
    
    if row:
        pid = row[0]
        try:
            os.kill(pid, 15)
            print(f"Stopped stream for camera {camera_id}")
        except:
            pass
        c.execute('DELETE FROM streams WHERE camera_id = ?', (camera_id,))
        conn.commit()
    
    conn.close()

def health_check_loop():
    """Periodically check if cameras are alive"""
    while True:
        time.sleep(15)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, ip FROM cameras WHERE enabled = 1')
        cameras = c.fetchall()
        
        for camera_id, ip in cameras:
            try:
                requests.get(f'http://{ip}:8000/health', timeout=2)
                c.execute('UPDATE cameras SET last_seen = ? WHERE id = ?', 
                         (datetime.now().isoformat(), camera_id))
                conn.commit()
            except:
                pass
        
        conn.close()

# API ROUTES 

@app.route('/api/cameras', methods=['GET'])
def list_cameras():
    """List all cameras"""
    return jsonify(get_cameras())

@app.route('/api/cameras', methods=['POST'])
def create_camera():
    """Add a new camera"""
    data = request.json
    success, msg = add_camera(data['name'], data['ip'], data.get('port', 5000))
    return jsonify({'success': success, 'message': msg}), (200 if success else 400)

@app.route('/api/cameras/<int:camera_id>', methods=['DELETE'])
def delete_camera(camera_id):
    """Remove a camera"""
    success, msg = remove_camera(camera_id)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/health', methods=['GET'])
def health():
    """Server health"""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    init_db()
    health_thread = threading.Thread(target=health_check_loop, daemon=True)
    health_thread.start()
    
    for camera in get_cameras():
        if camera['enabled']:
            start_stream(camera['id'], camera['ip'], camera['port'])
    
    app.run(host='0.0.0.0', port=5001, debug=False)