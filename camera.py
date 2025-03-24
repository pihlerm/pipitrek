import cv2
import numpy as np
import time
import math
import os
import datetime
from threading import Thread, Lock
from v412_ctl import get_v4l2_controls

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
            self.exposure = 0                   # Float for exposure (0.0–10.0 0=AUTO)
            self.r_channel = 1.0                # Float for R channel (0.0–1.0)
            self.g_channel = 1.0                # Float for G channel (0.0–1.0)
            self.b_channel = 1.0                # Float for B channel (0.0–1.0)
            self.integrate_frames = 5           # no. frames to integrate
            self.width = 1280
            self.height = 720
            self.cam_mode = 'YUYV'              # set 'MJPG' for compressed
            self.cam_fps = 5
            self.gain = 0

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
            self._thread = None

    def is_initialized(self):
        return self.cap and self.cap.isOpened()


    def start_capture(self):
        if not self._thread is None:
            print(f"Camera thread already running")
            return
                    
        self._thread = Thread(target=self.run_capture)
        self._thread.start()

    def stop_capture(self):
        if self._thread is None:
            print(f"Camera thread already stopped")
            return
        self.running = False
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            print("Warning: camera capture thread did not stop in time")
        else:
            print("Camera capture thread stopped")

        self._thread = None


    def run_capture(self):

        if not self.is_initialized():
            print(f"Camera not initialized, cannot run:capture")
            return

        self.running = True
        phase = 0

        while self.running:
            start_time = time.perf_counter()
            self.frame = self.get_frame()
            self.last_frame_time = time.perf_counter() - start_time
            
            #this is the trick for the camera to gain full exposure range..
            if phase==0:              
               self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)  # first set to auto
               phase=1
            elif phase==1:               
               self.set_exposure(self.exposure)             # later set to desired exposure
               phase=2

            #print(f"get_frame took {self.last_frame_time:.2f} seconds")

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
                        self.cleanup_and_exit()        



    def get_frame(self):
        # get a frame by multiple exposures        
        #if(self.integrate_frames==1):
        #    self.frame = self.capture_frame()
        #    return
        frame_accumulator = None
        num_frames = 0
        while num_frames < self.integrate_frames and self.running:
            num_frames+=1
            frame = self.capture_frame()
            # Convert frame to float32 for accumulation
            frame_float = frame.astype(np.float32)
            if frame_accumulator is None:
                frame_accumulator = frame_float
            else:
                frame_accumulator += frame_float  # Summing frames
        
        if num_frames==0:
            return None

        frame_accumulator /= num_frames

        # Apply color channel multipliers
        if self.r_channel != 1.0:
            frame_accumulator[:, :, 2] *= self.r_channel
        if self.g_channel != 1.0:
            frame_accumulator[:, :, 1] *= self.g_channel
        if self.b_channel != 1.0:
            frame_accumulator[:, :, 0] *= self.b_channel
        # CLIP summed image and convert back to uint8
        frame = np.clip(frame_accumulator, 0, 255).astype(np.uint8)
        #self.frame = cv2.convertScaleAbs(self.frame, alpha=1.5, beta=0)
        #frame = self.apply_gamma_correction(frame, gamma=1.5)
        return frame

    def apply_gamma_correction(self, image, gamma=1.5):
        inv_gamma = 1.0 / gamma
        lut = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        return cv2.LUT(image, lut)


    def set_exposure(self, exp) :
        self.exposure = exp
        
        b = math.log(self.max_exposure) 
        exposure = math.exp(b * exp)   
        # Clamp and round to integer range [1, 5000]
        exposure = max(1, min(5000, round(exposure)))

        # set auto exposure to 0.75 to disable it
        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
        # exp range is 0.0 - 1.0 ; stretch to range
        self.cap.set(cv2.CAP_PROP_EXPOSURE,  exposure)
        #self.cap.set(cv2.CAP_PROP_EXPOSURE,  2500*exp)
        if exp==0:
            # set auto exposure to 3 to enable it
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)
            print(f"Exposure set to AUTO" )
        else:
            print(f"Exposure set to {self.cap.get(cv2.CAP_PROP_EXPOSURE)}" )

    def set_gain(self, gain) :
        self.cap.set(cv2.CAP_PROP_GAIN, self.min_gain + (self.max_gain-self.min_gain)*gain)
        print(f"Gain set to {self.cap.get(cv2.CAP_PROP_GAIN)}" )
        self.gain = gain

    def setfps(self, fps):
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        print(f"Set FPS to {fps}, actual FPS: {self.actual_fps}")
        self.cam_fps = self.actual_fps

    def set_mode(self, mode):
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*mode))
        # check mode
        fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))  
        fourcc_str = fourcc.to_bytes(4, 'little').decode('utf-8', errors='replace')
        print(f"Camera mode: {fourcc_str}")
        self.cam_mode = fourcc_str

    def set_frame_size(self, w, h):
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        actual_width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        print(f"Frame size: {actual_width} X {actual_height}")
        self.width = actual_width
        self.height = actual_height

    def init_camera(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)  # Force V4L2 backend
        # Check if camera opened successfully
        if not self.cap.isOpened():
            return False            

        self.set_mode(self.cam_mode)
        self.set_frame_size(self.width, self.height)
        if self.cam_fps!=0:     # 0=auto
            self.setfps(self.cam_fps)

        # get gain range
        self.min_gain = 0
        self.cap.set(cv2.CAP_PROP_GAIN, 10000)  # Try setting a high value
        self.max_gain = self.cap.get(cv2.CAP_PROP_GAIN)
        print(f"Gain range: {self.min_gain} - {self.max_gain}")
        self.cap.set(cv2.CAP_PROP_GAIN, self.min_gain)
        self.set_gain(self.gain)
        
        # disable awb
        self.cap.set(cv2.CAP_PROP_AUTO_WB, 0)  

        # PREPARE EXPOSURE range
        self.max_exposure = 2000
        if 'exposure_time_absolute' in self.controls:
            self.max_exposure = self.controls['exposure_time_absolute']['max']
        print(f"Max exposure: {self.max_exposure}")


        return True

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
