import os
from pathlib import Path

import cv2
import numpy as np
import time

from torch import classes


class ObjectDetector:
    def __init__(self, model_path, provider="CPUExecutionProvider"):
        self.model_path = model_path
        self.__model: cv2.dnn.Net = None
        self.input_name = None
        self.output_name = None
        self.streams = {}
        self.last_id = 0
        self.fps = 0

        self.__setup_model()

    def __setup_model(self):
        net = cv2.dnn.readNetFromONNX(self.model_path)
        net.setPreferableBackend(cv2.dnn.DNN_TARGET_CPU)  # or cv2.dnn.DNN_TARGET_OPENCL for GPU
        # check performance with different backends cv2.dnn.DNN_BACKEND_INFERENCE_ENGINE
        self.__model = net
        self.input_name = self.__model.getLayerNames()[0]
        self.output_name = self.__model.getLayerNames()[-1]

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

    def test_or(self, frame):

        TARGET_OBJECTS = ["person", "cat", "knife", "scissors", "gun", "pistol", "handgun"]

        classes = open('models/coco.names').read().strip().split('\n')
        np.random.seed(42)
        colors = np.random.randint(0, 255, size=(len(classes), 3), dtype='uint8')

        if not os.path.exists(frame):
            print(f"File Error: File does not exist at: {os.path.abspath(frame)}")
            return

        img = cv2.imread(frame)

        # 1. AUTO-RESIZE FOR LARGE IPHONE PHOTOS
        MAX_DISPLAY_DIM = 800  # Sets the maximum width or height for your screen
        h_orig, w_orig = img.shape[:2]
        
        if max(h_orig, w_orig) > MAX_DISPLAY_DIM:
            # Calculate the scaling ratio
            scale = MAX_DISPLAY_DIM / max(h_orig, w_orig)
            new_w = int(w_orig * scale)
            new_h = int(h_orig * scale)
            
            # Downsample the image cleanly
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            print(f"🔄 Resized large image from {w_orig}x{h_orig} down to {new_w}x{new_h}")

        # Update your height/width trackers for the new scaled down image size
        height, width = img.shape[:2]
        cv2.imshow("Raw image to scan", img)
        cv2.waitKey(1)
        
        # Preprocess the frame for the model
        blob = cv2.dnn.blobFromImage(img, scalefactor=1/255.0, size=(640, 640), swapRB=True, crop=False)

        self.__model.setInput(blob)
        t0 = time.time()
        out_layers = self.__model.getUnconnectedOutLayersNames()
        outputs = self.__model.forward(out_layers)
        t1 = time.time()

        print("Output tensor shape:", outputs[0].shape)

        # Inner trackbar function for the 640x640 blob visualization
        def trackbar2(x):
            confidence = x / 100
            r = r0.copy()

            for output in outputs[0][0]:
                if output[4] > confidence:

                    classID = int(output[5])
                    class_name = classes[classID]
                    
                    # Filter trackbar preview
                    if class_name not in TARGET_OBJECTS:
                        continue

                    # YOLO26 coordinates are absolute inside the 640x640 blob grid
                    # layout is [xmin, ymin, xmax, ymax]
                    x1, y1, x2, y2 = output[:4]
                    p0 = (int(x1), int(y1))
                    p1 = (int(x2), int(y2))
                    
                    # Bright green box, 2px thick so it's fully visible on the blob
                    cv2.rectangle(r, p0, p1, (0, 255, 0), 2)
                    
            cv2.imshow('blob', r)
            text = f'Bbox confidence={confidence}'
            cv2.displayOverlay('blob', text)

        # Set up blob preview window (Note: convert single channel back to BGR so we can draw green lines)
        r0 = blob[0].transpose(1, 2, 0) # reshape to (640, 640, 3)
        r0 = cv2.normalize(r0, None, 0, 255, cv2.NORM_MINMAX).astype('uint8') # scale to visible spectrum
        
        cv2.imshow('blob', r0)
        cv2.createTrackbar('confidence', 'blob', 50, 101, trackbar2)
        trackbar2(50)

        boxes = []
        confidences = []
        classIDs = []

        actual_predictions = outputs[0][0] # Safely strip down to shape (300, 6)

        # Loop row-by-row through the 300 individual detections
        for detection in actual_predictions:
            confidence = float(detection[4])
            
            if confidence > 0.01:
                classID = int(detection[5])
                class_name = classes[classID]

                if class_name not in TARGET_OBJECTS:
                    continue  # Skip this detection if it's not a target object
                
                # YOLO26 outputs are mapped to a 640x640 box. 
                # We divide by 640 to normalize them, then multiply by true image size to map perfectly.
                x1 = int((detection[0] / 640.0) * width)
                y1 = int((detection[1] / 640.0) * height)
                x2 = int((detection[2] / 640.0) * width)
                y2 = int((detection[3] / 640.0) * height)
                
                # Convert XYXY to XYWH layout for OpenCV NMSBoxes requirement
                w_box = x2 - x1
                h_box = y2 - y1
                
                boxes.append([x1, y1, int(w_box), int(h_box)])
                confidences.append(confidence)
                classIDs.append(classID)

        # Non-Maximum Suppression
        indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.01, 0.4)
        if len(indices) > 0:
            for i in indices.flatten():
                x, y, w_box, h_box = boxes[i]
                color = [int(c) for c in colors[classIDs[i]]]
                
                # Draw on the original size processed image
                cv2.rectangle(img, (x, y), (x + w_box, y + h_box), color, 2)
                text = "{}: {:.4f}".format(classes[classIDs[i]], confidences[i])
                cv2.putText(img, text, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        cv2.imshow('Proccessed image', img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

        return outputs

    
if __name__ == "__main__":
    model_path = "models/yolo26n.onnx"  # Update with your model path
    detector = ObjectDetector(model_path)
    #get all files from this folder and test them
    path = Path("/home/ayden/Documents/Cat-TD")
    files = [str(f) for f in path.iterdir() if f.is_file()]
    for filepath in files:
        detector.test_or(filepath)
    # detector.test_or("/home/ayden/Documents/Cat-TD/1-cat-IR.png")  # Update with your test image path
    # detector.test_or("/home/ayden/Documents/Cat-TD/1-cat-IR-2.png")
    # detector.test_or("/home/ayden/Documents/Cat-TD/2-cats-IR.png")
    # detector.test_or("/home/ayden/Documents/Cat-TD/bb-lulu-1.jpeg")
    # detector.test_or("/home/ayden/Documents/Cat-TD/bb-lulu-2.jpeg")