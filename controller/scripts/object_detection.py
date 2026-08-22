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
        self.last_id = 0
        self.fps = 0

        self.__setup_model()

    def __setup_model(self) -> None:
        net = cv2.dnn.readNetFromONNX(self.model_path) # DNN_TARGET_CPU
        net.setPreferableBackend(cv2.dnn.DNN_TARGET_CPU)  # or cv2.dnn.DNN_TARGET_OPENCL for GPU
        # check performance with different backends cv2.dnn.DNN_BACKEND_INFERENCE_ENGINE (slightly better? more testing needed)
        self.__model = net
        self.input_name = self.__model.getLayerNames()[0]
        self.output_name = self.__model.getLayerNames()[-1]

    def set_fps(self, fps) -> None:
        self.fps = fps

    def test_or(self, frame):
        # 1. Target Classes for Home Security
        TARGET_OBJECTS = ["person", "cat", "knife", "scissors"]

        classes = open("models/coco.names").read().strip().split("\n")
        np.random.seed(42)
        colors = np.random.randint(0, 255, size=(len(classes), 3), dtype="uint8")

        if not os.path.exists(frame):
            print(f"File Error: File does not exist at: {os.path.abspath(frame)}")
            return

        img = cv2.imread(frame)

        # Extract base filename without extension to create unique output names
        base_filename = Path(frame).stem  # e.g., "IMG_4821"

        # 2. AUTO-RESIZE LARGE IPHONE PHOTOS PROPORTIONALLY
        MAX_DISPLAY_DIM = 800
        h_orig, w_orig = img.shape[:2]
        if max(h_orig, w_orig) > MAX_DISPLAY_DIM:
            scale = MAX_DISPLAY_DIM / max(h_orig, w_orig)
            img = cv2.resize(
                img,
                (int(w_orig * scale), int(h_orig * scale)),
                interpolation=cv2.INTER_AREA,
            )

        height, width = img.shape[:2]

        # Ensure output folder exists
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)

        # Save unique raw input file
        cv2.imwrite(os.path.join(output_dir, f"{base_filename}_raw.jpg"), img)

        # 3. Preprocess Frame for YOLO26
        blob = cv2.dnn.blobFromImage(
            img, scalefactor=1 / 255.0, size=(640, 640), swapRB=True, crop=False
        )
        self.__model.setInput(blob)

        t0 = time.time()
        out_layers = self.__model.getUnconnectedOutLayersNames()
        outputs = self.__model.forward(out_layers)
        t1 = time.time()
        inference_time = t1 - t0

        log_path = os.path.join(output_dir, "inference_history.log")
        log_line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | File: {os.path.basename(frame)} | Inference: {inference_time:.3f}s\n"
        with open(log_path, "a") as log_file:
            log_file.write(log_line)

        # 4. Process and Save unique Blob Visualization
        r0 = blob[0].transpose(1, 2, 0)
        r0 = cv2.normalize(r0, None, 0, 255, cv2.NORM_MINMAX).astype("uint8")
        r0 = cv2.cvtColor(r0, cv2.COLOR_RGB2BGR)

        for output in outputs[0][0]:
            if output[4] > 0.50:
                classID = int(output[5])
                if classes[classID] in TARGET_OBJECTS:
                    x1, y1, x2, y2 = output[:4]
                    cv2.rectangle(
                        r0, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2
                    )
        cv2.imwrite(os.path.join(output_dir, f"{base_filename}_blob.jpg"), r0)

        # 5. Native YOLO26 End-to-End Processing
        for detection in outputs[0][0]:
            confidence = float(detection[4])

            if confidence > 0.28:
                classID = int(detection[5])
                class_name = classes[classID]

                if class_name not in TARGET_OBJECTS:
                    continue

                x1 = int((detection[0] / 640.0) * width)
                y1 = int((detection[1] / 640.0) * height)
                x2 = int((detection[2] / 640.0) * width)
                y2 = int((detection[3] / 640.0) * height)

                color = [int(c) for c in colors[classID]]
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

                text = f"{class_name}: {confidence:.2f}"
                cv2.putText(
                    img,
                    text,
                    (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    1,
                )

        final_img_path = os.path.join(output_dir, f"{base_filename}_processed.jpg")
        cv2.imwrite(final_img_path, img)

        print(f"Saved: {final_img_path} and updated log in {log_path}")
        return outputs


if __name__ == "__main__":
    model_path = "models/yolo26n.onnx"  # Update with your model path
    detector = ObjectDetector(model_path)
    #get all files from this folder and test them
    path = Path("Cat-TD") 
    files = [str(f) for f in path.iterdir() if f.is_file()]
    for filepath in files:
        detector.test_or(filepath)
    # detector.test_or("/home/ayden/Documents/Cat-TD/1-cat-IR.png")  # Update with your test image path
    # detector.test_or("/home/ayden/Documents/Cat-TD/1-cat-IR-2.png")
    # detector.test_or("/home/ayden/Documents/Cat-TD/2-cats-IR.png")
    # detector.test_or("/home/ayden/Documents/Cat-TD/bb-lulu-1.jpeg")
    # detector.test_or("/home/ayden/Documents/Cat-TD/bb-lulu-2.jpeg")
