import socket, time
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
from gpiozero import LED

PIN = 17
DARK_ON, DARK_OFF = 40, 60   # hysteresis thresholds (0-255), tune these
DEFAULT_FRAME_RATE = 8              # frames/sec, tune this
out = LED(PIN)

picam2 = Picamera2()
cfg = picam2.create_video_configuration(
    main={"size": (1280, 720), "format": "YUV420"},
    lores={"size": (320, 240), "format": "YUV420"},
    controls={"FrameRate": DEFAULT_FRAME_RATE},
)
picam2.configure(cfg)

srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", 5000))
srv.listen(1)
conn, _ = srv.accept()

picam2.start_recording(H264Encoder(bitrate=2_000_000, repeat=True),
                       FileOutput(conn.makefile("wb")))

try:
    while True:
        frame = picam2.capture_array("lores")
        y = frame[:240]                 # Y (luma) plane of YUV420
        brightness = y.mean()
        # If “dark” should mean “the room is dim,” read picam2.capture_metadata() instead and use ExposureTime, AnalogueGain, or Lux.
        if brightness < DARK_ON:
            out.on()
        elif brightness > DARK_OFF:
            out.off()
        time.sleep(0.5)                 # you don't need to check 12x/sec
finally:
    picam2.stop_recording()