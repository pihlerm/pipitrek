import cv2
import numpy as np
import time
import os
import json
from threading import Thread, Lock
from v412_ctl import get_v4l2_controls, set_v4l2_control, set_v4l2_controls, extract_v4l2_control_values
import gc

class Camera:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Camera, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.running = False

            self.frame = None                   # Last captured frame
            self.last_frame_time = 0
            # camera settings
            self.color = True                   # True for color, False for grayscale
            self.r_channel = 1.0                # Float for R channel (0.0–1.0)
            self.g_channel = 1.0                # Float for G channel (0.0–1.0)
            self.b_channel = 1.0                # Float for B channel (0.0–1.0)
            self.integrate_frames = 5           # no. frames to integrate
            self.width = 1280
            self.height = 720
            #self.cam_mode = 'YUYV'              # set 'MJPG' for compressed
            #self.width = 1920
            #self.height = 1080
            self.cam_mode = 'MJPG'              # set 'MJPG' for compressed
            self.cam_fps = 5

            # camera usb reconnect/retry settings
            self.max_failures = 5               # Number of failures to attept reconnect
            self.failure_count = 0              # Current number of failures
            self.recovery_attempts = 0          # Current number of recovery attempts
            self.max_recovery_attempts = 3      # Max recovery attempts before we quit

            self.cap = None                     # cv2 object
            self.controls = get_v4l2_controls() 
            if self.controls is None:
                raise RuntimeError("Failed to fetch v4l2 controls. Ensure the camera is connected and v4l2-ctl is installed.")

            self.lock = Lock()                  # Thread lock 
            self._capture_t = None        
            self.realloc_lock = Lock()                  # Thread lock 
            self.alloc_buffers(self.color)
            
            self.output_dir = ""
            self.dark_frame_path = "dark_frame_avg.png"
            self.hot_pixel_mask_path = "hot_pixel_mask.npy"
            self.hot_pixels = None

            # Placeholder Bayer mask (to be determined later)
            # Example: Simple bilinear interpolation weights, center = 1
            self.bayer_mask = np.array([
                [0.15, 0.3, 0.15],
                [0.3,  1.0, 0.3 ],
                [0.15, 0.3, 0.15]
            ], dtype=np.float32)

    def alloc_buffers(self, color):
        with self.realloc_lock:
            self.color = color
            if self.color:
                self.frame_accumulator = np.zeros((int(self.height), int(self.width), 3), dtype=np.uint16)  # Preallocate, adjust shape
                self.temp_buffer = np.empty((int(self.height), int(self.width), 3), dtype=np.float32)  # Temp for scaling
            else:
                self.frame_accumulator = np.zeros((int(self.height), int(self.width)), dtype=np.uint16)  # Preallocate, adjust shape
                self.temp_buffer = np.empty((int(self.height), int(self.width)), dtype=np.float32)  # Temp for scaling


    def is_initialized(self):
        return self.cap and self.cap.isOpened()


    def start_capture(self):
        if not self._capture_t is None:
            print(f"Camera thread already running")
            return
        if not self.is_initialized():
            print(f"Camera not initialized, cannot run:capture")
            return
        self.running = True
        self._capture_t = Thread(target=self.run_single_thread, name="CaptureThread")
        self._capture_t.start()


    def stop_capture(self):
        if self._capture_t is None:
            print(f"Camera thread already stopped")
            return
        self.running = False
        self._capture_t.join(timeout=10)
        #self._process_t.join(timeout=10)
        if self._capture_t.is_alive():
        #if self._capture_t.is_alive() or self._process_t.is_alive():
            print("Warning: camera capture thread did not stop in time")
        else:
            print("Camera capture thread stopped")
        self._capture_t = None
        #self._process_t = None


    def capture_frame(self, color = None):
        # get a frame        
        if color is None:
            color = self.color
        with self.lock:
            while True:
                ret, frame = self.cap.read()
                if ret:
                    self.failure_count = 0  # Reset failure counter on success
                    if color:
                        return frame
                    else:
                        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                else:
                    self.failure_count += 1
                    print(f"No frame snapped in capture_frame (Failure #{self.failure_count}).")
                    if self.failure_count >= self.max_failures:
                        print(f"Max failures ({self.max_failures}) reached. Attempting recovery...")
                        self.attempt_recovery()
                    if self.recovery_attempts >= self.max_recovery_attempts:
                        print(f"Max recovery attempts ({self.max_recovery_attempts}) reached. Terminating...")
                        raise ValueError("Camera stopped responding")

    def clear_hot_pixel_mask(self):
        filename = os.path.join(self.output_dir, self.hot_pixel_mask_path)
        if os.path.exists(filename):
            os.remove(filename)
            print(f"Removed hot pixel mask file: {filename}")
        self.hot_pixels = None
            
    def capture_hot_pixel_mask(self, dark_frames_to_avg=10, hot_pixel_threshold=15):
        print("Capturing dark frames...")
        frames = []
        for i in range(dark_frames_to_avg):
            gray = self.capture_frame(False)
            frames.append(gray.astype(np.float32))
        avg_dark = np.mean(frames, axis=0)

        filename = os.path.join(self.output_dir, self.dark_frame_path)
        cv2.imwrite(filename, avg_dark.astype(np.uint8))
        print(f"Saved dark frame to {filename}")

        # Step 1: Threshold to find potential hot pixels
        median_val = np.median(avg_dark)
        threshold = median_val + hot_pixel_threshold
        potential_hot_pixels = avg_dark > threshold
        hot_pixel_coords = np.argwhere(potential_hot_pixels)

        # Step 2: Filter for local maxima in 3x3 neighborhood
        true_hot_pixels = []
        height, width = avg_dark.shape
        for y, x in hot_pixel_coords:
            # Define 3x3 neighborhood boundaries
            y1, y2 = max(y - 1, 0), min(y + 2, height)
            x1, x2 = max(x - 1, 0), min(x + 2, width)
            neighborhood = avg_dark[y1:y2, x1:x2]
            # Check if the center pixel is the maximum
            center_val = avg_dark[y, x]
            if center_val == np.max(neighborhood):
                true_hot_pixels.append([y, x])

        # Convert to numpy array
        self.hot_pixels = np.array(true_hot_pixels, dtype=np.int32) if true_hot_pixels else np.empty((0, 2), dtype=np.int32)

        with open(filename, 'w') as f:
            json.dump(self.hot_pixels.tolist(), f)

        print(f"Saved hot pixel mask to {filename}")

    def load_hot_pixel_mask(self):
        filename = os.path.join(self.output_dir, self.hot_pixel_mask_path)
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                self.hot_pixels = np.array(json.load(f), dtype=np.int32)
            print(f"Loaded hot pixel mask from {filename}")
        else:
            self.hot_pixels = None
            print(f"hot pixel mask file not found: {filename}")

    def apply_hot_pixel_mask(self, frame):
        if self.hot_pixels is None or len(self.hot_pixels) == 0:
            return
        
        if len(frame.shape) == 3:  # Color image
            height, width, colors = frame.shape
        else:
            height, width = frame.shape
            colors = 1

        for c in range(colors):  # for each color channel: R, G, B
            for y, x in self.hot_pixels:

                # Define 3x3 neighborhood boundaries
                y1, y2 = max(y - 1, 0), min(y + 2, height)
                x1, x2 = max(x - 1, 0), min(x + 2, width)

                # Step 1: Extract the central value and 3x3 neighborhood
                # Extract the neighborhood
                if colors>1:
                    central_value = frame[y, x, c]
                    neighborhood = frame[y1:y2, x1:x2, c].astype(np.float32)
                else:
                    central_value = frame[y, x]
                    neighborhood = frame[y1:y2, x1:x2].astype(np.float32)

                # Adjust bayer_mask to match the neighborhood size (in case of edges)
                dy1, dy2 = y - y1, y2 - y - 1
                dx1, dx2 = x - x1, x2 - x - 1
                mask_slice = self.bayer_mask[1 - dy1:2 + dy2, 1 - dx1:2 + dx2]

                # Step 2: Anti-debayer by subtracting central_value * bayer_mask
                correction = central_value * mask_slice
                neighborhood -= correction

                # Ensure values stay within valid range (0-255 for uint8)
                neighborhood = np.clip(neighborhood, 0, 255)

                # Update the neighborhood in the frame
                # Replace the hot pixel with the median of the corrected neighborhood
                if colors>1:
                    frame[y1:y2, x1:x2, c] = neighborhood.astype(np.uint8)
                    median_val = np.median(neighborhood)
                    frame[y, x, c] = int(median_val)
                else:
                    frame[y1:y2, x1:x2] = neighborhood.astype(np.uint8)
                    median_val = np.median(neighborhood)
                    frame[y, x] = int(median_val)
            

    def run_single_thread(self):
        self.running = True
        while self.running:
            capture_time=0
            process_time=0
            start_time = time.perf_counter()
            frame_count = 0
            start = 0

            if self.integrate_frames==1:
                start = time.perf_counter()
                self.frame = self.capture_frame()
                self.apply_hot_pixel_mask(self.frame)
                capture_time+=time.perf_counter() - start
                start = time.perf_counter()
                frame_count = 1
            else:
                # Copy first frame, add rest
                for i in range(self.integrate_frames):
                    start = time.perf_counter()
                    frame = self.capture_frame()
                    start2=time.perf_counter()
                    capture_time+=start2 - start
                    
                    gc.disable()
                    with self.realloc_lock:
                        if frame is None:
                            break
                        if i == 0:
                            self.frame_accumulator[...] = frame  # Copy first frame
                        else:
                            np.add(self.frame_accumulator, frame, out=self.frame_accumulator)  # Add in-place
                        frame_count += 1
                        process_time+=time.perf_counter() - start2
                        gc.enable()
            
                if frame_count == 0:
                    continue

                start = time.perf_counter()
                gc.disable()
                with self.realloc_lock:
                    self.frame_accumulator //= frame_count  # In-place division
                    #multipliers = np.array([self.b_channel, self.g_channel, self.r_channel], dtype=np.float32)
                    #if not np.allclose(multipliers, 1.0):
                        #np.multiply(self.frame_accumulator, multipliers[None, None, :], out=self.temp_buffer)
                        #np.clip(self.temp_buffer, 0, 255, out=self.frame_accumulator)

                    frame = self.frame_accumulator.astype(np.uint8)
                    self.apply_hot_pixel_mask(frame)
                    self.frame=frame
                gc.enable()
    
            end_time = time.perf_counter()
            process_time+=end_time - start
            self.last_frame_time = end_time - start_time
            #print(f"Frame time {end_time - start_time:.2f}s")
            #print(f"Processing time {process_time:.2f}s")
            #print(f"Capturing time {capture_time:.2f}s")
            #print("")

    def apply_gamma_correction(self, image, gamma=1.5):
        inv_gamma = 1.0 / gamma
        lut = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        return cv2.LUT(image, lut)

    def setfps(self, fps):
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        print(f"Set FPS to {fps}, actual FPS: {self.actual_fps}")
        self.cam_fps = self.actual_fps

    def set_color(self, color):
        self.alloc_buffers(color)

    def set_mode(self, mode):
        with self.lock:
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*mode))
            # check mode
            fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))  
            fourcc_str = fourcc.to_bytes(4, 'little').decode('utf-8', errors='replace')
            print(f"Camera mode: {fourcc_str}")
            self.cam_mode = fourcc_str

    def set_frame_size(self, w, h):
        with self.lock:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            actual_width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            print(f"Frame size: {actual_width} X {actual_height}")
            self.width = actual_width
            self.height = actual_height
            self.alloc_buffers(self.color)

    def init_camera(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)  # Force V4L2 backend
        # Check if camera opened successfully
        if not self.cap.isOpened():
            return False            

        self.set_mode(self.cam_mode)
        self.set_frame_size(self.width, self.height)
        if self.cam_fps!=0:     # 0=auto
            self.setfps(self.cam_fps)

        return True

    def get_exposure(self):
        return self.cap.get(cv2.CAP_PROP_EXPOSURE)

    def set_direct_control(self, name, value):
        return set_v4l2_control(name, value)
    
    def get_direct_controls(self):
        self.controls = get_v4l2_controls()
        return self.controls

    def set_direct_controls(self, controls):
        return set_v4l2_controls(controls)

    def get_direct_control_values(self):
        self.get_direct_controls()
        return extract_v4l2_control_values(self.controls)

    def release_camera(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()

    def attempt_recovery(self):
        self.recovery_attempts += 1
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print(f"Recovery attempt #{self.recovery_attempts}: Camera released.")
        time.sleep(1)  # Wait for device to settle
        self.init_camera()
        if self.cap.isOpened():
            print(f"Recovery attempt #{self.recovery_attempts}: Camera reopened successfully.")
            self.failure_count = 0  # Reset if recovery succeeds
            self.recovery_attempts = 0
        else:
            print(f"Recovery attempt #{self.recovery_attempts}: Failed to reopen camera.")

    def __del__(self):
        self.release_camera()
