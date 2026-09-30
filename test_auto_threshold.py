import cv2
from analyzer import Analyzer

IMAGE_PATH = "static/img/saved_frame.png"

import time
time_start = time.time()

frame = cv2.imread(IMAGE_PATH)
if frame is None:
    raise FileNotFoundError(f"Could not load image: {IMAGE_PATH}")

analyzer = Analyzer()
best_thresh = analyzer.auto_threshold(frame)
print(f"auto_threshold selected gray_threshold = {best_thresh}")

gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
_, thresh_img = cv2.threshold(gray, best_thresh, 255, cv2.THRESH_BINARY)

time_end = time.time()
print(f"Execution time: {time_end - time_start:.2f} seconds")

cv2.imshow("Original", frame)
cv2.imshow(f"Thresholded (t={best_thresh})", thresh_img)
cv2.waitKey(0)
cv2.destroyAllWindows()
