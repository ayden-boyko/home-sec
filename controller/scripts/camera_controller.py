import os
import sqlite3
import subprocess
import time
import requests
from datetime import datetime
from flask import Flask, jsonify, request


#TODO: check if ffmpeg proccesses are alive, if not, restart them
class CameraController:
    def __init__(self, db_file, hls_base):
        self.db_file = db_file
        self.hls_base = hls_base
        self.processes = {}  # Store subprocesses for each camera
        self.app = Flask(__name__)
        self.setup_routes()
        self.init_db()

    def setup_routes(self):
        @self.app.route('/api/cameras', methods=['GET'])
        def list_cameras():
            return jsonify(self.get_cameras())

        @self.app.route('/api/cameras', methods=['POST'])
        def create_camera():
            data = request.json
            success, msg = self.add_camera(data['name'], data['ip'], data.get('port', 5000))
            # return 500 if key error, 400 if validation error, 200 if success
            if not success:
                return jsonify({'success': success, 'message': msg}), 400
            return jsonify({'success': success, 'message': msg}), 200
        @self.app.route('/api/cameras/<int:camera_id>', methods=['DELETE'])
        def delete_camera(camera_id):
            success, msg = self.remove_camera(camera_id)
            return jsonify({'success': success, 'message': msg}), (200 if success else 400)

        @self.app.route('/api/health', methods=['GET'])
        def health():
            
            return jsonify({'status': 'ok'})

    def run(self):

        for camera in self.get_cameras():
            if camera['enabled']:
                self.start_stream(camera['id'], camera['ip'], camera['port'])

        # TODO: fine for dev, but not for production, change
        self.app.run(host='0.0.0.0', port=5001)

    def init_db(self):
        conn = sqlite3.connect(self.db_file)
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

    def start_stale_streams(self):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('SELECT id, ip, port FROM cameras WHERE enabled = 1')
        cameras = c.fetchall()
        for camera_id, ip, port in cameras:
            proc = self.processes.get(camera_id)
            if proc is None or proc.poll() is not None:  # Process is not running
                print(f"Starting stale stream for camera {camera_id}")
                self.start_stream(camera_id, ip, port)
        conn.close()

    def get_cameras(self) -> list[dict]:
        conn = sqlite3.connect(self.db_file)
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

    def add_camera(self, name, ip, port=5000) -> tuple[bool, str]:
        try:
            # TODO: SSRF protection: validate IP address format and ensure it's not a private/internal IP
            r = requests.get(f'http://{ip}:8000/health', timeout=2)
            print(f"Health check passed for {ip}: {r.status_code}")
        except Exception as e:
            print(f"Health check failed for {ip}: {e}")
            return False, f"Cannot reach camera at this IP: {e}"

        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        try:
            c.execute('INSERT INTO cameras (name, ip, port) VALUES (?, ?, ?)', (name, ip, port))
            conn.commit()
            camera_id = c.lastrowid
            conn.close()
            print(f"Camera added to DB: {camera_id}")
            self.start_stream(camera_id, ip, port)
            return True, f"Camera added (ID: {camera_id})"
        except sqlite3.IntegrityError as e:
            conn.close()
            print(f"DB error: {e}")
        return False, "Camera with this IP already exists"

    def remove_camera(self, camera_id) -> tuple[bool, str]:
        self.stop_stream(camera_id)
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('DELETE FROM cameras WHERE id = ?', (camera_id,))
        conn.commit()
        conn.close()
        return True, "Camera removed"

    def start_stream(self, camera_id, camera_ip, camera_port) -> bool:
        hls_dir = f"{self.hls_base}/cam{camera_id}"
        os.makedirs(hls_dir, exist_ok=True)
    
        cmd = [
            [
                'ffmpeg',
                '-fflags', 'nobuffer+genpts',  # genpts fixes missing presentation timestamps over raw TCP
                '-reorder_queue_size', '200',  # Buffers packets in Pi 4B RAM to smooth out Wi-Fi jitter
                '-i', f'tcp://{camera_ip}:{camera_port}?listen=0', # Actively connects to the Pi Zero
                '-c:v', 'copy',                # Direct stream copy (uses ~1-2% total CPU on Pi 4B)
                '-an',                         # Drops audio to save network bandwidth (remove if mic is used)
                '-f', 'hls',
                '-hls_time', '2',
                '-hls_list_size', '10',
                '-hls_flags', 'delete_segments+temp_file', # temp_file ensures the playlist doesn't glitch during overwrites
                f'{hls_dir}/stream.m3u8'       # Safely saved directly to your NVMe SSD path
            ]

        ]
        
        #TODO: https://claude.ai/chat/4f84f2f7-8524-4b42-938a-7b03160ed588
        cmd_decode = [
            'ffmpeg', '-i', f'tcp://{camera_ip}:{camera_port}?listen=0',
            '-f', 'rawvideo', '-pix_fmt', 'bgr24',
            '-vf', 'scale=1280:720',
            'pipe:1'
        ]
        
        while True:
            try:
                print(f"Starting ffmpeg: {' '.join(cmd)}")
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.processes[camera_id] = proc
                proc.wait() # Wait for the process to finish (blocking)
                print(f"ffmpeg process for camera {camera_id} exited with code {proc.returncode}")
            except Exception as e:
                print(f"Failed to start ffmpeg for camera {camera_id}: {e}")
                return False
        
        
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO streams (camera_id, process_id) VALUES (?, ?)', (camera_id, proc.pid))
        conn.commit()
        conn.close()
        
        print(f"Started stream for camera {camera_id} (PID: {proc.pid})")
        return True

    def stop_stream(self, camera_id) -> bool:
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('SELECT process_id FROM streams WHERE camera_id = ?', (camera_id,))
        row = c.fetchone()
        if row:
            pid = row[0]
            try:
                proc = self.processes.get(camera_id)
                if proc is None:
                    print(f"No running process found for camera {camera_id}")
                    return False
                else:
                    proc.poll()  # Check if the process is still running
                    if proc.returncode is None:  # Process is still running
                        os.kill(pid, 15)  # Send SIGTERM to the process
                        print(f"Stopped stream for camera {camera_id}")
                    else:
                        print(f"Stream for camera {camera_id} is not running, no need to stop.")
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                print(f"Failed to stop stream for camera {camera_id}: {e}")
                return False
            c.execute('DELETE FROM streams WHERE camera_id = ?', (camera_id,))
            conn.commit()
            del self.processes[camera_id]
        conn.close()
        return True
    
    def health_check_loop(self) -> None:
        while True:
            time.sleep(15)
            self.start_stale_streams()  # Ensure all enabled cameras have running streams
            conn = sqlite3.connect(self.db_file)
            c = conn.cursor()
            c.execute('SELECT id, ip FROM cameras WHERE enabled = 1')
            cameras = c.fetchall()
            
            for camera_id, ip in cameras:
                try:
                    requests.get(f'http://{ip}:8000/health', timeout=2)
                    c.execute('UPDATE cameras SET last_seen = ? WHERE id = ?', 
                            (datetime.now().isoformat(), camera_id))
                    conn.commit()
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:
                    print(f"Health check failed for camera {camera_id}: {e}")
            
            conn.close()

    # returns the processes dictionary for external access (e.g., for monitoring or management)
    # this allows the yolo model to consume from the ffmnpeg pipes, 
    # otherwise the pipes will fill up and block the ffmpeg process, causing the stream to crash
    def get_processes(self):
        # yolo consumes stdout from RWLock within shared memory, stderr gets written to log file, so we don't need to worry about it filling up
        return self.processes