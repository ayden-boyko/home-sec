import cv2
import numpy as np
import onnxruntime as ort
import time


class ObjectDetector:
    def __init__(self, model_path, provider="CPUExecutionProvider"):
        self.session = ort.InferenceSession(model_path, providers=[provider])
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.streams = {}
        self.last_id = 0
        self.fps = 0

    def set_fps(self, fps):
        self.fps = fps

    def add_stream(self, stream_url):
        
        self.last_id += 1
        self.streams[self.last_id] = {
            # if fps too high and model is slow, we can skip frames]
            # pulls frame from shared variable from reader
            "frame": None, 
            "last_frame_time": time.time()
        }
        return self.last_id

    def remove_stream(self, stream_id):
        if stream_id in self.streams:
            self.streams[stream_id]["cap"].release()
            del self.streams[stream_id]

    