import cv2
import numpy as np
import time
import os
from threading import Thread, RLock

STATIC_IMAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "saved_frame.png")
DEFAULT_EXPOSURE = 1000     # exposure units are 100 us (as in camera.py); used when exposure is auto (0)


class _SimulatedCap:
    """Minimal stand-in for cv2.VideoCapture, so code reading camera.cap keeps working."""

    def __init__(self, camera):
        self.camera = camera
        self.opened = True

    def isOpened(self):
        return self.opened

    def release(self):
        self.opened = False

    def get(self, prop):
        if prop == cv2.CAP_PROP_FPS:
            return float(self.camera.cam_fps)
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.camera.width)
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.camera.height)
        if prop == cv2.CAP_PROP_EXPOSURE:
            return float(self.camera.exposure)
        return 0.0

    def set(self, prop, value):
        return True


class Camera:
    """Simulated camera: serves a static image, taking 2 * exposure time per frame."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Camera, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.running = False

            self.camera_index = 0

            self.frame = None
            self.latest = (None, 0)             # (frame, timestamp) published together
            self.last_frame_time = 0
            self.last_frame_timestamp = 0
            self.last_read_time = 0
            self.read_failures_total = 0
            self.last_lock_wait = 0
            self.last_mask_time = 0

            self.color = True
            self.rotation_angle = 0.0
            self.pixel_scale = 3.2
            self.r_channel = 1.0
            self.g_channel = 1.0
            self.b_channel = 1.0
            self.integrate_frames = 1           # kept for API compatibility, not used
            self.width = 1280
            self.height = 720
            self.cam_mode = 'MJPG'
            self.cam_fps = 5

            self.error_x = 0.0                  # persistent image shift in pixels (drift/guiding error)
            self.error_y = 0.0
            self.seeing_arcsec = 0.7            # RMS seeing jitter per frame; 0 = disabled
            self._seeing_x = 0.0                # transient jitter of the current frame (pixels)
            self._seeing_y = 0.0

            self.exposure = DEFAULT_EXPOSURE    # 100 us units
            self.image_path = STATIC_IMAGE_PATH
            self._source = None                 # static image as loaded (BGR)

            self.cap = None
            self.controls = []
            self.lock = RLock()
            self._capture_t = None
            self.output_dir = ""
            self.hot_pixels = None

    def is_initialized(self):
        return self.cap is not None and self.cap.isOpened()
    
    def list_cameras(self):
        return [self.camera_index] if self.is_initialized() else []
    
    def start_capture(self):
        if self._capture_t is not None:
            print("Camera thread already running")
            return
        if not self.is_initialized():
            print("Camera not initialized, cannot run capture")
            return
        self.running = True
        self._capture_t = Thread(target=self.run_single_thread, name="CaptureThread")
        self._capture_t.start()

    def stop_capture(self):
        if self._capture_t is None:
            print("Camera thread already stopped")
            return
        self.running = False
        self._capture_t.join(timeout=10)
        if self._capture_t.is_alive():
            print("Warning: camera capture thread did not stop in time")
        else:
            print("Camera capture thread stopped")
        self._capture_t = None

    def _exposure_seconds(self):
        exposure = self.exposure if self.exposure else DEFAULT_EXPOSURE
        return exposure / 10000.0

    def capture_frame(self, color=None):
        if color is None:
            color = self.color
        t_lock = time.perf_counter()
        with self.lock:
            self.last_lock_wait = time.perf_counter() - t_lock
            t_read = time.perf_counter()
            # simulate exposure + readout
            time.sleep(2 * self._exposure_seconds())
            source = self._source
            if source is None:
                raise ValueError("Simulated camera has no image loaded")
            w, h = int(self.width), int(self.height)
            if source.shape[1] != w or source.shape[0] != h:
                source = cv2.resize(source, (w, h))
            self.dec_drift(0.1)
            self.random_shift()
            dx = self.error_x + self._seeing_x
            dy = self.error_y + self._seeing_y
            if dx or dy:
                m = np.float32([[1, 0, dx], [0, 1, dy]])
                frame = cv2.warpAffine(source, m, (w, h), flags=cv2.INTER_LINEAR,
                                       borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            else:
                frame = source.copy()
            self.last_read_time = time.perf_counter() - t_read
            if color:
                return frame
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    def random_shift(self, sigma_arcsec=None):
        """Simulate atmospheric seeing: new gaussian jitter (arcsec RMS per axis) for the next frame.
        Not accumulated into error_x/error_y. Called per frame using self.seeing_arcsec."""
        if sigma_arcsec is not None:
            self.seeing_arcsec = float(sigma_arcsec)
        sigma_px = self.seeing_arcsec / self.pixel_scale if self.pixel_scale else 0.0
        if sigma_px <= 0:
            self._seeing_x = self._seeing_y = 0.0
        else:
            self._seeing_x, self._seeing_y = np.random.normal(0.0, sigma_px, 2)
        return self._seeing_x, self._seeing_y

    def dec_drift(self, delta_arcsec):
        """Drift the image along the Dec axis by delta_arcsec (accumulates in error_x/error_y)."""
        d = delta_arcsec / self.pixel_scale
        a = np.radians(self.rotation_angle)
        self.error_x += -d * np.sin(a)
        self.error_y += d * np.cos(a)
        return self.error_x, self.error_y

    def correction(self, ra_arcsec, dec_arcsec):
        """Simulate a telescope move: remove ra_arcsec/dec_arcsec of error from error_x/error_y."""
        r = - ra_arcsec / self.pixel_scale
        d = - dec_arcsec / self.pixel_scale
        a = np.radians(self.rotation_angle)
        self.error_x -= r * np.cos(a) - d * np.sin(a)
        self.error_y -= r * np.sin(a) + d * np.cos(a)
        return self.error_x, self.error_y

    def clear_hot_pixel_mask(self):
        pass

    def capture_hot_pixel_mask(self, *args, **kwargs):
        pass

    def load_hot_pixel_mask(self):
        pass

    def apply_hot_pixel_mask(self, frame):
        pass

    def run_single_thread(self):
        self.running = True
        while self.running:
            start_time = time.perf_counter()
            try:
                frame = self.capture_frame()
            except ValueError as e:
                print(f"Simulated camera error: {e}", flush=True)
                time.sleep(1)
                continue
            ts = time.time()
            self.last_frame_timestamp = ts
            self.latest = (frame, ts)
            self.frame = frame
            self.last_frame_time = time.perf_counter() - start_time

    def setfps(self, fps):
        self.cam_fps = fps
        print(f"Set FPS to {fps} (simulated)")

    def set_color(self, color):
        self.color = color

    def set_mode(self, mode):
        self.cam_mode = mode

    def set_frame_size(self, w, h):
        self.width = int(w)
        self.height = int(h)
        print(f"Frame size: {self.width} X {self.height} (simulated)")

    def init_camera(self):
        print("Init simulated camera")
        img = cv2.imread(self.image_path, cv2.IMREAD_COLOR)
        if img is None:
            print(f"Could not load simulated camera image: {self.image_path}")
            return False
        self._source = img
        self.cap = _SimulatedCap(self)
        return True

    def release_camera(self):
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()

    def select_camera(self, index):
        with self.lock:
            self.release_camera()
            self.camera_index = index
            self.init_camera()

    def get_exposure(self):
        with self.lock:
            return self.exposure

    def set_exposure(self, exposure):
        with self.lock:
            self.exposure = int(exposure)

    def set_direct_control(self, name, value):
        return True

    def get_direct_controls(self):
        return self.controls

    def set_direct_controls(self, controls):
        return True

    def get_direct_control_values(self):
        return {}

    def attempt_recovery(self):
        self.init_camera()

    def __del__(self):
        self.release_camera()
