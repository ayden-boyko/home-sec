import socket, time, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

DARK_ON, DARK_OFF = 40, 60
FRAME_RATE = 8

try:
    from gpiozero import LED
    led = LED(17)
except Exception as e:
    print("LED unavailable, continuing without it:", e)
    led = None

last_frame = time.time()

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        ok = self.path == "/health" and time.time() - last_frame < 5
        self.send_response(200 if ok else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}' if ok else b'{"status":"stalled"}')
    def log_message(self, *args):
        pass

threading.Thread(target=HTTPServer(("0.0.0.0", 8000), Health).serve_forever,
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
srv.bind(("0.0.0.0", 5000))
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
    last_frame = time.time()
    if led:
        if brightness < DARK_ON:
            led.on()
        elif brightness > DARK_OFF:
            led.off()
    time.sleep(0.5)