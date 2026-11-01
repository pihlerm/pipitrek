import cv2
import numpy as np
import time
import os
import json
from threading import Thread, Lock, RLock
from v412_ctl import get_v4l2_controls, set_v4l2_control, set_v4l2_controls, extract_v4l2_control_values,list_cameras
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

            self.camera_index = 0

            self.frame = None                   # Last captured frame
            self.frame_number = 0
            self.latest = (None, 0, 0)             # (frame, timestamp, frame_number) published together
            self.last_frame_time = 0
            self.last_frame_timestamp = 0
            self.last_read_time = 0             # Duration of the last cap.read() (s)
            self.read_failures_total = 0        # Total failed cap.read() calls
            self.raw_yuyv = False               # Reading raw YUYV buffers (set in init_camera)
            self.corrupt_frames = 0             # Total truncated frames detected
            self.duplicate_frames = 0           # Total repeated frames skipped
            self.empty_frames = 0               # Total empty buffers skipped
            self.prev_rows = []                 # Recent raw YUYV frames for stale-row detection
            self.last_lock_wait = 0             # Time waited for the camera lock before the last read (s)
            self.last_mask_time = 0             # Time spent in hot pixel masking for the last frame (s)
            self.detect_stale_rows = True       # Enable stale row detection
            self.stale_percent = 0.6            # Maximum allowed stale row percentage before we discard the whole frame
            # camera settings
            self.color = True                   # True for color, False for grayscale
            self.rotation_angle = 0.0            # Camera orientation in degrees (-180 to 180)
            self.pixel_scale = 3.2               # Arcseconds per pixel at the equator
            self.r_channel = 1.0                # Float for R channel (0.0–1.0)
            self.g_channel = 1.0                # Float for G channel (0.0–1.0)
            self.b_channel = 1.0                # Float for B channel (0.0–1.0)
            self.integrate_frames = 1           # no. frames to integrate
            self.width = 1280
            self.height = 720
            self.cam_mode = 'MJPG'              # set 'MJPG' for compressed
            self.cam_fps = 5

            # camera usb reconnect/retry settings
            self.max_failures = 5               # Number of failures to attept reconnect
            self.failure_count = 0              # Current number of failures
            self.recovery_attempts = 0          # Current number of recovery attempts
            self.max_recovery_attempts = 3      # Max recovery attempts before we quit

            self.cap = None                     # cv2 object
            self.controls = get_v4l2_controls(self.camera_index) 
            if self.controls is None:
                raise RuntimeError("Failed to fetch v4l2 controls. Ensure the camera is connected and v4l2-ctl is installed.")

            self.lock = RLock()                  # Thread lock 
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
                [0.1, 0.2, 0.1],
                [0.2,  1.0, 0.2 ],
                [0.1, 0.2, 0.1]
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

    def list_cameras(self):
        return list_cameras()

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
        t_lock = time.perf_counter()
        with self.lock:
            self.last_lock_wait = time.perf_counter() - t_lock
            while True:
                t_read = time.perf_counter()
                ret, frame = self.cap.read()
                self.last_read_time = time.perf_counter() - t_read
                self.frame_number += 1
                if ret:
                    self.failure_count = 0  # Reset failure counter on success
                    if self.raw_yuyv:
                        decoded = self.decode_raw_yuyv(frame, color)
                        if decoded is None:
                            continue    # empty or duplicate buffer, read the next one
                        return decoded
                    if color:
                        return frame
                    else:
                        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                else:
                    self.failure_count += 1
                    self.read_failures_total += 1
                    print(f"No frame snapped in capture_frame (Failure #{self.failure_count}) after {self.last_read_time:.2f}s.", flush=True)
                    if self.failure_count >= self.max_failures:
                        print(f"Max failures ({self.max_failures}) reached. Attempting recovery...")
                        t_rec = time.perf_counter()
                        self.attempt_recovery()
                        print(f"Recovery took {time.perf_counter() - t_rec:.2f}s", flush=True)
                    if self.recovery_attempts >= self.max_recovery_attempts:
                        # Keep retrying so the camera comes back after being re-plugged
                        print(f"Max recovery attempts ({self.max_recovery_attempts}) reached. Waiting for camera to return...", flush=True)
                        self.recovery_attempts = 0
                        self.failure_count = self.max_failures - 1
                        if not self.running:
                            raise ValueError("Camera stopped responding")
                        time.sleep(2)

    def decode_raw_yuyv(self, raw, color):
        # Raw YUYV buffer sized to bytesused: truncated (corrupted) frames are shorter than w*h*2.
        # Missing bottom rows are filled with black.
        w, h = int(self.width), int(self.height)
        max_stale = h * self.stale_percent
        row_bytes = w * 2
        full = row_bytes * h
        buf = raw.reshape(-1)
        if buf.size < row_bytes:
            self.empty_frames += 1
            print(f"Empty/short buffer #{self.frame_number}: {buf.size} bytes, skipped (total: {self.empty_frames})", flush=True)
            return None
        good_rows = h
        if buf.size < full:
            good_rows = buf.size // row_bytes
            self.corrupt_frames += 1
            print(f"Corrupted frame #{self.frame_number}: got {buf.size}/{full} bytes, "
                  f"{good_rows}/{h} rows valid, bottom filled black (total corrupted: {self.corrupt_frames})", flush=True)
            padded = np.zeros(full, dtype=np.uint8)
            padded[:buf.size] = buf
            buf = padded
        rows = buf[:full].reshape(h, row_bytes)

        # Stale data: with nodrop the driver can deliver a buffer whose rows are left over from an earlier
        # frame in the buffer ring. Sensor noise makes real rows never byte-identical, so rows identical
        # to the same row of any recent frame are stale.
        stale = np.zeros(h, dtype=bool)     # per-row flag: True = stale, blanked at the end of this function
        if self.prev_rows and self.prev_rows[0].shape != (h, row_bytes):
            self.prev_rows = []             # frame size changed, history is no longer comparable
        # Ignore completely flat rows (e.g. black or saturated), which can legitimately match
        valid = np.ptp(rows[:good_rows], axis=1) > 0
        for prev in self.prev_rows:
            same = np.zeros(h, dtype=bool)
            # a row is stale if all its bytes equal the same row in that earlier frame
            same[:good_rows] = (rows[:good_rows] == prev[:good_rows]).all(axis=1) & valid
            stale |= same
        # keep the last 6 raw frames for comparison with future frames
        self.prev_rows.append(rows.copy())
        if len(self.prev_rows) > 6:
            self.prev_rows.pop(0)
        stale_count = int(stale[:good_rows].sum())
        if stale_count > 0:
            self.duplicate_frames += 1
            first = int(np.argmax(stale))
            print(f"Stale frame #{self.frame_number}: {stale_count}/{h} rows identical to a previous frame "
                  f"(first at row {first}), total stale frames: {self.duplicate_frames}", flush=True)
            if stale_count > max_stale:
                return None     # mostly a repeat, read the next buffer

        # Convert the raw YUYV bytes to an image: 2 bytes per pixel (Y + shared U/V)
        yuyv = rows.reshape(h, w, 2)
        if color:
            frame = cv2.cvtColor(yuyv, cv2.COLOR_YUV2BGR_YUY2)
        else:
            frame = yuyv[:, :, 0].copy()   # Y channel is the grayscale image

        # Black out truncated rows (everything below the last row the camera actually delivered)
        if good_rows < h:
            frame[good_rows:] = 0
        # Black out stale rows: boolean row mask, True = row identical to a previous frame
        frame[stale] = 0
        return frame

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

        filename = os.path.join(self.output_dir, self.hot_pixel_mask_path)
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
                frame = self.capture_frame()
                ts = time.time()
                t_mask = time.perf_counter()
                self.apply_hot_pixel_mask(frame)
                self.last_mask_time = time.perf_counter() - t_mask
                # publish frame and its timestamp together so readers never pair them wrongly
                self.last_frame_timestamp = ts
                self.latest = (frame, ts, self.frame_number)
                self.frame = frame
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
                        if frame is None or (self.color and len(frame.shape) != 3) or (not self.color and len(frame.shape) != 2):
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
                    ts = time.time()
                    self.last_frame_timestamp = ts
                    self.latest = (frame, ts, self.frame_number)
                    self.frame=frame
                gc.enable()
    
            end_time = time.perf_counter()
            process_time+=end_time - start
            self.last_frame_time = end_time - start_time
            if self.last_frame_time > 1.5:
                print(f"SLOW CAMERA CYCLE {self.last_frame_time:.2f}s: read={self.last_read_time:.2f}s "
                      f"lock_wait={self.last_lock_wait:.2f}s mask={self.last_mask_time:.2f}s "
                      f"read_failures_total={self.read_failures_total}", flush=True)
            #print(f"Frame time {end_time - start_time:.2f}s")
            #print(f"Processing time {process_time:.2f}s")
            #print(f"Capturing time {capture_time:.2f}s")
            #print("")

    def apply_gamma_correction(self, image, gamma=1.5):
        inv_gamma = 1.0 / gamma
        lut = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        return cv2.LUT(image, lut)

    def setfps(self, fps):
        with self.lock:
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
            self.raw_yuyv = (self.detect_stale_rows and fourcc_str == 'YUYV')
            self.cap.set(cv2.CAP_PROP_CONVERT_RGB, 0 if self.raw_yuyv else 1)
    
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

    def enable_uvc_nodrop(self):
        # Keep damaged frames instead of letting uvcvideo discard them (needs root; read when the device is opened)
        path = "/sys/module/uvcvideo/parameters/nodrop"
        try:
            if os.path.exists(path):
                with open(path) as f:
                    current = f.read().strip()
                if current not in ("1", "Y"):
                    with open(path, "w") as f:
                        f.write("1")
                    print("uvcvideo nodrop enabled")
        except OSError as e:
            print(f"Could not set uvcvideo nodrop: {e}")

    def init_camera(self):
        print(f"Init camera")
        self.enable_uvc_nodrop()
        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)  # Force V4L2 backend
        #self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Check if camera opened successfully
        if not self.cap.isOpened():
            return False            
        self.set_mode(self.cam_mode)
        self.set_frame_size(self.width, self.height)
        if self.cam_fps!=0:     # 0=auto
            self.setfps(self.cam_fps)
        # re-assert after size/fps changes, which may reset it
        self.cap.set(cv2.CAP_PROP_CONVERT_RGB, 0 if self.raw_yuyv else 1)
        print(f"Camera raw YUYV path: {'ON' if self.raw_yuyv else 'OFF'} (mode {self.cam_mode}, {self.width}x{self.height})", flush=True)
        return True

    def release_camera(self):
        print(f"Init camera")
        if self.cap and self.cap.isOpened():
            self.cap.release()

    def select_camera(self, index):
        with self.lock:
            print(f"Selecting camera {index}")
            self.release_camera()
            self.camera_index = index
            self.controls = get_v4l2_controls(self.camera_index)
            self.init_camera()
            self.alloc_buffers(self.color)

    def get_exposure(self):
        with self.lock:
            return self.cap.get(cv2.CAP_PROP_EXPOSURE)
    
    def set_exposure(self, exposure):
        with self.lock:
            if(exposure==0):
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)
            else:
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
                self.cap.set(cv2.CAP_PROP_EXPOSURE, int(exposure))

    def set_direct_control(self, name, value):
        return set_v4l2_control(name, value, self.camera_index)
    
    def get_direct_controls(self):
        self.controls = get_v4l2_controls(self.camera_index)
        return self.controls

    def set_direct_controls(self, controls):
        return set_v4l2_controls(controls, self.camera_index)

    def get_direct_control_values(self):
        self.get_direct_controls()
        return extract_v4l2_control_values(self.controls)

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
            self.set_direct_controls(self.controls)
        else:
            print(f"Recovery attempt #{self.recovery_attempts}: Failed to reopen camera.")

    def __del__(self):
        self.release_camera()
