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

    

    