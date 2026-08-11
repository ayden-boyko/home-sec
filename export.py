from ultralytics import YOLO

# 1. Load the official pretrained YOLO26n PyTorch model
model = YOLO("yolo26n.pt")

# 2. Export the model to ONNX format
model.export(format="onnx")