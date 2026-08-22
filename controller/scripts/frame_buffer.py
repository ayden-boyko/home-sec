import threading


class FrameBuffer:
    def __init__(self):
        self.lock = threading.Lock()
        self.latest_frame = None
        self.frame_id = 0
    
    def put_frame(self, frame_data):
        """Camera thread: writes newest frame (overwrites old)"""
        with self.lock:
            self.latest_frame = frame_data
            self.frame_id += 1
    
    def get_frame(self):
        """Detector thread: reads newest frame"""
        with self.lock:
            frame = self.latest_frame
            frame_id = self.frame_id
        return frame, frame_id