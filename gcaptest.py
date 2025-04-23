import cv2
cap = cv2.VideoCapture("v4l2src device=/dev/video0 ! video/x-raw,format=YUY2,width=1920,height=1080,framerate=5/1 ! videoconvert ! appsink", cv2.CAP_GSTREAMER)
if not cap.isOpened():
    print("Error: Webcam failed to open")
    exit()
for i in range(10):
    ret, frame = cap.read()
    if not ret:
        print(f"Error: Failed to capture frame {i}")
        break
    cv2.imwrite(f"frame_{i}.jpg", frame)
    print(f"Captured frame {i}")
cap.release()