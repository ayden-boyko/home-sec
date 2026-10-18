import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from ir_control import IR, SETTLE
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

FRAME_RATE = 8
HEALTH_PORT = 8000
STREAM_PORT = 5000

try:
    from gpiozero import LED
    led = LED(17)
    ir = IR()
except Exception as e:
    led = None
    ir = None
    print("LED UNAVAILABLE, continuing without IR:", e)

brightness = None
last_frame = time.time()

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        ok = self.path == "/health" and time.time() - last_frame < 5
        ir_state = "unavailable" if led is None else ("on" if ir.on else "off")
        body = json.dumps({
            "status": "ok" if ok else "stalled",
            "ir": ir_state,
            "brightness": None if brightness is None else round(brightness),
        }).encode()
        self.send_response(200 if ok else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

threading.Thread(target=HTTPServer(("0.0.0.0", HEALTH_PORT), Health).serve_forever,
                 daemon=True).start()

picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(
    main={"size": (1280, 720), "format": "YUV420"},
    lores={"size": (320, 240), "format": "YUV420"},
    controls={"FrameRate": FRAME_RATE},
))
picam2.start()

srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", STREAM_PORT))
srv.listen(1)

def serve_stream():
    while True:
        conn, _ = srv.accept()
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        enc = H264Encoder(bitrate=2_000_000, repeat=True, iperiod=FRAME_RATE)
        try:
            picam2.start_encoder(enc, FileOutput(conn.makefile("wb")))
            while True:
                time.sleep(1)
                try:
                    if conn.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) == b"":
                        break
                except BlockingIOError:
                    pass
                except OSError:
                    break
        except Exception as e:
            print("stream error:", e)
        finally:
            try:
                picam2.stop_encoder()
            except Exception:
                pass
            conn.close()

threading.Thread(target=serve_stream, daemon=True).start()

while True:
    brightness = picam2.capture_array("lores")[:240].mean()
    if ir is not None:
        action = ir.decide(time.time(), brightness)
        if action == "on":
            led.on()
        elif action == "recheck":
            # Only a reading taken with IR off says whether the room is truly
            # dark; while IR is on its own light washes the image out.
            led.off()
            time.sleep(SETTLE)
            brightness = picam2.capture_array("lores")[:240].mean()
            if ir.apply_recheck(time.time(), brightness) == "on":
                led.on()
        else:
            led.off()
    last_frame = time.time()
    time.sleep(0.5)