import cv2
import numpy as np
import time
import math
import os
import datetime
from telescope import Telescope
from threading import Thread, Lock
from v412_ctl import get_v4l2_controls

class Autoguider:
    def __init__(self):
        self.frame = None  # Last captured frame
        self.threshold = None  # Last threshold image
        self.last_thresh = None

        self.tracked_centroid = None  # Reference point
        self.current_centroid = None  # Position of last detect_star
        self.max_drift = 10  # Integer for max_drift (0–50)
        self.star_size = 100  # Integer for star_size (1–100)
        self.gray_threshold = 150  # Integer for threshold (0–255)
        self.rotation_angle = 0.0  # Float for rotation angle (-180 to 180)
        self.pixel_scale = 3.6  # Float for pixel scale (0.1–10.0)
        self.last_correction = {"ra": 0, "dec": 0, "dx": 0, "dy": 0, "ra_arcsec": 0, "dec_arcsec": 0}
        self.exposure = 0  # Float for exposure (0.0–10.0 0=AUTO)

        self.r_channel = 1.0  # Float for R channel (0.0–1.0)
        self.g_channel = 1.0  # Float for G channel (0.0–1.0)
        self.b_channel = 1.0  # Float for B channel (0.0–1.0)

        self.integrate_frames = 5  # no. frames to integrate
        self.time_period = 1  # Time period for tracking in seconds

        self.output_dir = "/root/astro/images"
        os.makedirs(self.output_dir, exist_ok=True)

        self.max_failures = 5  # Increased to allow more recovery attempts
        self.failure_count = 0
        self.recovery_attempts = 0
        self.max_recovery_attempts = 3
        
        self.controls = get_v4l2_controls()

        self.init_camera()
        # Check if camera opened successfully
        if not self.cap.isOpened():
            print("Error: Could not open webcam.")
            exit()

        # check mode
        fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))  
        fourcc_str = fourcc.to_bytes(4, 'little').decode('utf-8', errors='replace')
        print(f"Camera mode: {fourcc_str}")

        # check max esposure
        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
        self.cap.set(cv2.CAP_PROP_EXPOSURE,  0)
        self.max_exposure = self.controls['exposure_time_absolute']['max']
        #self.max_exposure = self.cap.get(cv2.CAP_PROP_EXPOSURE)  # Get current exposure
        print(f"Max exposure: {self.max_exposure}")
        print(f"Frame size: {self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)} X {self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")

        # get gain range
        self.min_gain = 0
        self.cap.set(cv2.CAP_PROP_GAIN, 10000)  # Try setting a high value
        self.max_gain = self.cap.get(cv2.CAP_PROP_GAIN)
        self.gain = 0
        print(f"Gain range: {self.min_gain} - {self.max_gain}")
        self.cap.set(cv2.CAP_PROP_GAIN, self.min_gain)
        
        # set auto exposure to 3 to enable it
        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)
        print(f"Exposure set to AUTO" )

        # disable awb
        self.cap.set(cv2.CAP_PROP_AUTO_WB, 0)  

        #if self.cap.isOpened():
        #    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.running = False
        self.lock = Lock()  # Thread lock for frame and threshold

    def detect_star(self, frame, search_near=None):
        with self.lock:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            #gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, self.gray_threshold, 255, cv2.THRESH_BINARY)
            self.threshold = thresh  # Store last threshold
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            self.current_centroid = None
            return None
        if search_near is not None:
            # Search near the provided centroid
            distances = [np.linalg.norm(np.array(c.mean(axis=0)[0]) - np.array(search_near)) for c in contours if len(c) > 0]
            if distances:
                closest_idx = np.argmin(distances)
                largest = contours[closest_idx]
            else:
                largest = max(contours, key=cv2.contourArea)
        else:
            largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) > self.star_size:
            M = cv2.moments(largest)
            if M["m00"] != 0:
                centroid = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                self.current_centroid = centroid  # Update current_centroid
                return centroid
        self.current_centroid = None
        return None

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
        self.gain = gain
        self.cap.set(cv2.CAP_PROP_GAIN, self.min_gain + (self.max_gain-self.min_gain)*self.gain)
        print(f"Gain set to {self.cap.get(cv2.CAP_PROP_GAIN)}" )

    def set_integrate_frames(self, integrate_frames) :
        self.integrate_frames = integrate_frames

    def rotate_vector(self, dx, dy):
        """Rotate (dx, dy) vector by rotation_angle (degrees) counterclockwise."""
        angle_rad = math.radians(self.rotation_angle)
        new_dx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
        new_dy = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
        return new_dx, new_dy
    
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
                    print(f"No frame snapped in get_frame (Failure #{self.failure_count}).")
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
        while num_frames < self.integrate_frames:
            num_frames+=1
            frame = self.capture_frame()
            # Convert frame to float32 for accumulation
            frame_float = frame.astype(np.float32)
            if frame_accumulator is None:
                frame_accumulator = frame_float
            else:
                frame_accumulator += frame_float  # Summing frames
        
        frame_accumulator /= num_frames
        
        with self.lock:
            # Apply color channel multipliers
            if self.r_channel != 1.0:
                frame_accumulator[:, :, 2] *= self.r_channel
            if self.g_channel != 1.0:
                frame_accumulator[:, :, 1] *= self.g_channel
            if self.b_channel != 1.0:
                frame_accumulator[:, :, 0] *= self.b_channel
            # CLIP summed image and convert back to uint8
            self.frame = np.clip(frame_accumulator, 0, 255).astype(np.uint8)
            #self.frame = cv2.convertScaleAbs(self.frame, alpha=1.5, beta=0)
            #self.frame = self.apply_gamma_correction(self.frame, gamma=3.5)
            return

    def apply_gamma_correction(self, image, gamma=1.5):
        inv_gamma = 1.0 / gamma
        lut = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        return cv2.LUT(image, lut)

    def acquire_star(self, centroid=None, frame=None):
        if frame is None:
            self.get_frame()
            frame = self.frame

        centroid = self.detect_star(frame, search_near=centroid)
        if centroid:
            with self.lock:
                self.tracked_centroid = centroid
                print(f"ACQUIRED STAR at {self.tracked_centroid}")
                self.write_track_log(f"ACQUIRED STAR at {self.tracked_centroid}")
        else:
            print("No star detected.")
            self.write_track_log("NO STAR DETECTED")
        

    def write_track_log(self, log_entry):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        day = datetime.datetime.now().strftime("%Y-%m-%d")
        with open(f"tracking_{day}.log", "a") as log_file:
            log_file.write(f"{timestamp}, {log_entry}\n")

    def run_autoguider(self):
        self.running = True
        last_time = time.perf_counter()
        while self.running:
            start_time = time.perf_counter()
            self.get_frame()  # Capture and integrate frames
            frame_time = time.perf_counter()
            print(f"get_frame took {frame_time - start_time:.2f} seconds")
            current_time = time.perf_counter()
            #if current_time - last_time >= self.time_period:  # Run once per period
            if True:
                if self.tracked_centroid is None:
                    # Acquisition mode
                    self.acquire_star(frame = self.frame)
                else:
                    # Tracking mode
                    centroid = self.detect_star(self.frame, search_near=self.tracked_centroid)
                    detect_time = time.perf_counter()
                    print(f"detect_star took {detect_time - frame_time:.2f} seconds")                    # Get current timestamp
                    if centroid and self.tracked_centroid:
                        dx = centroid[0] - self.tracked_centroid[0]
                        dy = centroid[1] - self.tracked_centroid[1]
                        dx_rot, dy_rot = self.rotate_vector(dx, dy)
                        ra_arcsec = dx_rot * self.pixel_scale
                        dec_arcsec = dy_rot * self.pixel_scale
                        #if abs(ra_arcsec) > self.max_drift or abs(dec_arcsec) > self.max_drift:
                        self.last_correction = {
                            "ra": 1 if ra_arcsec > 0 else -1 if ra_arcsec < 0 else 0,
                            "dec": 1 if dec_arcsec > 0 else -1 if dec_arcsec < 0 else 0,
                            "dx": dx, "dy": dy,
                            "ra_arcsec": ra_arcsec, "dec_arcsec": dec_arcsec
                        }
                        print(f"Tracked correction: RA={self.last_correction['ra']}, DEC={self.last_correction['dec']}, "
                                f"RA(arcsec)={ra_arcsec:.1f}, DEC(arcsec)={dec_arcsec:.1f}, dx={dx}, dy={dy}")
                        # Log to tracking.log file
                        self.write_track_log(f"move({self.last_correction['ra']}, {self.last_correction['dec']}), "
                                    f"pixel error({self.last_correction['dx']}, {self.last_correction['dy']}), "
                                    f"RaDec error({self.last_correction['ra_arcsec']:.1f}, {self.last_correction['dec_arcsec']:.1f})")
                    else:
                        self.last_correction = {
                            "ra": 0 ,
                            "dec": 0,
                            "dx": 0, "dy": 0,
                            "ra_arcsec": 0, "dec_arcsec": 0
                        }
                        if not centroid:
                            print(f"Lost tracking: Star moved out of frame.")
                            # Log to tracking.log file
                            self.write_track_log(f"LOST TRACKING")
                        else:
                            print(f"Lost tracking: no target.")
                            # Log to tracking.log file
                            self.write_track_log("NO TARGET")

                end_time = time.perf_counter()
                total_time = end_time - start_time
                if total_time > 2.0:  # Flag long delays
                    print(f"Loop took {total_time:.2f} seconds")
                last_time = current_time  # Update last time
            time.sleep(0.001)  # Small sleep to prevent busy loop

    def init_camera(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)  # Force V4L2 backend
        # Check if camera opened successfully
        if not self.cap.isOpened():
            return False            
        # Force MJPG pixel format
        #self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        # Force YUYV pixel format
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return True


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
            telescope = Telescope()
            telescope.reset_usb()
            #self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)
            #print(f"Exposure set to AUTO" )
        else:
            print(f"Recovery attempt #{self.recovery_attempts}: Failed to reopen camera.")

    def cleanup_and_exit(self):
            if self.cap and self.cap.isOpened():
                self.cap.release()
                print("Camera released.")
            os._exit(1)  # Forcefully terminate the process

 
    def __del__(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print("Camera released.")
