import cv2
import numpy as np
import time
import math
import queue
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
            self.alloc_buffers()
            

    def alloc_buffers(self):
        with self.realloc_lock:
            self.frame_accumulator = np.zeros((int(self.height), int(self.width), 3), dtype=np.uint16)  # Preallocate, adjust shape
            self.temp_buffer = np.empty((int(self.height), int(self.width), 3), dtype=np.float32)  # Temp for scaling


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


    def capture_frame(self):
        # get a frame        
        with self.lock:
            while True:
                ret, frame = self.cap.read()
                if ret:
                    self.failure_count = 0  # Reset failure counter on success
                    #gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)  # Convert to grayscale
                    return frame
                else:
                    self.failure_count += 1
                    print(f"No frame snapped in capture_frame (Failure #{self.failure_count}).")
                    if self.failure_count >= self.max_failures:
                        print(f"Max failures ({self.max_failures}) reached. Attempting recovery...")
                        self.attempt_recovery()
                    if self.recovery_attempts >= self.max_recovery_attempts:
                        print(f"Max recovery attempts ({self.max_recovery_attempts}) reached. Terminating...")
                        raise ValueError("Camera stopped responding")


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
                    multipliers = np.array([self.b_channel, self.g_channel, self.r_channel], dtype=np.float32)
                    if not np.allclose(multipliers, 1.0):
                        np.multiply(self.frame_accumulator, multipliers[None, None, :], out=self.temp_buffer)
                        np.clip(self.temp_buffer, 0, 255, out=self.frame_accumulator)

                    self.frame = self.frame_accumulator.astype(np.uint8)
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
            self.alloc_buffers()

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
