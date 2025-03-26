import cv2
import numpy as np
import time
import math
import os
import datetime
from telescope import Telescope
from threading import Thread, Lock
from v412_ctl import get_v4l2_controls
from analyzer import Analyzer
from camera import Camera
from concurrent.futures import ThreadPoolExecutor

null_correction = { "ra": 0 , "dec": 0, "dx": 0, "dy": 0, "ra_arcsec": 0, "dec_arcsec": 0 }



class PIDController:
    def __init__(self, Kp, Ki, Kd, alpha=0.9, dt=1.0):
        self.Kp = Kp        # Proportional gain
        self.Ki = Ki        # Integral gain
        self.Kd = Kd        # Derivative gain
        self.alpha = alpha  # Integral decay factor (0–1)
        self.dt = dt        # Time step (seconds)
        self.integral = 0.0 # Accumulated error
        self.prev_error = 0.0  # Last error

    def compute(self, error):
        # Proportional term
        P = self.Kp * error

        # Integral term with decay
        self.integral = self.alpha * self.integral + error * self.dt
        I = self.Ki * self.integral

        # Derivative term
        derivative = (error - self.prev_error) / self.dt
        D = self.Kd * derivative
        self.prev_error = error  # Update previous error

        # Total output
        output = P + I + D
        return output

    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0

class Autoguider:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4)  # Create a thread pool with 4 workers
        self.pending_tasks = 0  # Counter for pending tasks
        self.task_lock = Lock()  # Lock to ensure thread-safe updates to the counter

        self.analyzer = Analyzer()
        self.camera = Camera()

        self.dec_guiding = False            # Declination guiding. Make sure that DEC does not disturb RA!!
        self.guiding = False                # Guiding status on/off
        self.threshold = None               # Last threshold image
        self.last_frame_time = 0            # Last frame capture  time
        self.last_loop_time = 0             # Last loop time
        self.last_status = ""               # Last status message
        self.tracked_centroid = None        # Reference point we are tracking
        self.current_centroid = None        # Last position of tracked star
        self.focus_metric = 0               # focus_metric of last detected star
        self.star_locked = False            # If autoguider currently has a guide star locked
        # last error and correction needed
        self.last_correction = null_correction

        # tracking settings
        self.max_drift = 10                 # Integer for max_drift (0–50)
        self.star_size = 100                # Integer for star_size (1–100)
        self.gray_threshold = 150           # Integer for threshold (0–255)
        self.rotation_angle = 0.0           # Float for rotation angle (-180 to 180)
        self.pixel_scale = 3.6              # Float for pixel scale (0.1–10.0)
        self.guide_interval = 1.0           # Time period for tracking in seconds
        self.guide_pulse = 0.4              # Correction length: time between move start and move end (seconds)
        
        self.output_dir = "/root/astro/images"
        os.makedirs(self.output_dir, exist_ok=True)

        self.running = False
        self.lock = Lock()  # Thread lock for frame and threshold

        self.data_ready = False     # set to true when new processing data available for monitoring

    def write_track_log(self, log_entry):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        day = datetime.datetime.now().strftime("%Y-%m-%d")
        with open(f"tracking_{day}.log", "a") as log_file:
            log_file.write(f"{timestamp}, {log_entry}\n")


    def detect_star(self, frame, search_near=None):
        with self.lock:
            centroid, detail, thresh, focus_metric = self.analyzer.detect_star(frame, 
                                                                 search_near=search_near, 
                                                                 gray_threshold = self.gray_threshold,
                                                                 star_size=self.star_size)
            self.centroid_image = detail
            self.threshold = thresh
            self.focus_metric = focus_metric
            return centroid

    def rotate_vector(self, dx, dy):
        """Rotate (dx, dy) vector by rotation_angle (degrees) counterclockwise."""
        angle_rad = math.radians(self.rotation_angle)
        new_dx = round(dx * math.cos(angle_rad) - dy * math.sin(angle_rad), 4)
        new_dy = round(dx * math.sin(angle_rad) + dy * math.cos(angle_rad), 4)
        return new_dx, new_dy
    

    def acquire_star(self, frame=None, centroid=None):
        if frame is None:
            frame = self.camera.frame
        
        centroid = self.detect_star(frame, search_near=centroid)
        if centroid:
            with self.lock:
                self.tracked_centroid = centroid
                self.current_centroid = centroid
                self.last_status = f"ACQUIRED STAR at {self.tracked_centroid}"
                print(self.last_status)
                self.write_track_log(self.last_status)
        else:
            self.last_status = "NO STAR DETECTED"
            #print(self.last_status)
            self.write_track_log(self.last_status)
        

    def guide_scope_abs(self, ra_arcsec_error, dec_arcsec_error):
        trackmsg =  f"move({self.last_correction['ra']}, {self.last_correction['dec']})"
        self.write_track_log(trackmsg)
        print(trackmsg)
        telescope = Telescope()

        if self.last_correction["ra"] == 0 and self.last_correction["dec"] == 0:
            #nothing to do
            return

        # do not add corrections if some still pending
        if self.pending_tasks>0:
            print(f"Guide command cancelled because last correction still in progress!")
            self.last_correction["ra"] = 0
            self.last_correction["dec"] = 0
            return

      # Helper function to decrement the counter when a task finishes
        def task_done_callback(future):
            with self.task_lock:
                self.pending_tasks -= 1

        # RA corrections
        if self.last_correction["ra"] != 0:
            dir = 'w' if self.last_correction["ra"] == 1 else 'e'
            with self.task_lock:
                self.pending_tasks += 1
            future = self.executor.submit(telescope.send_correction, dir, self.guide_pulse)
            future.add_done_callback(task_done_callback)  # Decrement counter when task finishes

        # DEC corrections
        if self.last_correction["dec"] != 0:
            dir = 's' if self.last_correction["dec"] == 1 else 'n'
            with self.task_lock:
                self.pending_tasks += 1
            future = self.executor.submit(telescope.send_correction, dir, self.guide_pulse)
            future.add_done_callback(task_done_callback)  # Decrement counter when task finishes
            

    def guide_scope_rel(self, ra_arcsec_error, dec_arcsec_error):
        # this should be PID controller!        
        ra_speed = int(-1*ra_arcsec_error)
        ra_speed = max(-15, min(ra_speed, 15))
        dec_speed = int(-1*dec_arcsec_error)
        dec_speed = max(-15, min(dec_speed, 15))
        trackmsg =  f"move_speed({ra_speed}, {dec_speed})"
        self.write_track_log(trackmsg)
        print(trackmsg)
        telescope = Telescope()
        if not self.dec_guiding:
            dec_speed = 0

        telescope.send_start_movement_speed(ra_speed, dec_speed)

    def guide_scope_pid(self, ra_arcsec_error, dec_arcsec_error):
        # Initialize PID controllers (persistent across calls)
        if not hasattr(self, 'ra_pid'):
            self.ra_pid = PIDController(Kp=0.5, Ki=0.05, Kd=0.1, dt=1.0)  # Tune these!
        if not hasattr(self, 'dec_pid'):
            self.dec_pid = PIDController(Kp=0.5, Ki=0.05, Kd=0.1, dt=1.0)

        # Compute speeds with PID
        ra_speed = self.ra_pid.compute(-ra_arcsec_error)  # Negative to correct RA
        dec_speed = self.dec_pid.compute(-dec_arcsec_error)

        # Clamp speeds to -15 to 15 (assuming steps/second)
        ra_speed = int(max(-15, min(ra_speed, 15)))
        dec_speed = int(max(-15, min(dec_speed, 15)))
        if not self.dec_guiding:
            dec_speed = 0

        # Log and send command
        trackmsg = f"move_speed({ra_speed:.2f}, {dec_speed:.2f})"
        self.write_track_log(trackmsg)
        print(trackmsg)

        telescope = Telescope()
        telescope.send_start_movement_speed(ra_speed, dec_speed)

    def guide_scope(self, ra_arcsec_error, dec_arcsec_error):
        self.guide_scope_pid(ra_arcsec_error, dec_arcsec_error)

    def calculate_drift(self, centroid):
        if centroid and self.tracked_centroid:
            dx = round(float(centroid[0] - self.tracked_centroid[0]), 4)
            dy = round(float(centroid[1] - self.tracked_centroid[1]), 4)
            dx_rot, dy_rot = self.rotate_vector(dx, dy)
            ra_arcsec = round(dx_rot * self.pixel_scale, 4)
            dec_arcsec = round(dy_rot * self.pixel_scale, 4)
            self.last_correction = {
                "ra": 1 if ra_arcsec > self.max_drift else -1 if ra_arcsec < -self.max_drift else 0,
                "dec": 1 if dec_arcsec > self.max_drift and self.dec_guiding else -1 if dec_arcsec < -self.max_drift and self.dec_guiding else 0,
                "dx": dx, "dy": dy,
                "ra_arcsec": ra_arcsec, "dec_arcsec": dec_arcsec
            }
            self.last_status = f"TRACKING: Star at {centroid}, dx={dx}, dy={dy}"
            #print(self.last_status)
            self.write_track_log(self.last_status)

    def move_and_detect(self, telescope, move_direction, move_time, search_near ):
        print(f" >> moving {move_direction} for {move_time} seconds...")
        telescope.send_correction(move_direction,move_time)  # Move scope west for 10s
        print("settling ... ")
        time.sleep(2)   # settling scope
        frame = self.camera.get_frame()
        centroid = self.detect_star(frame, search_near=search_near)  # Detect star
        if not centroid:
           raise ValueError("Failed to detect centroid")
        return centroid

    def calibrate_angle(self, with_backlash=False):
        #TODO : wait for new frames!
        telescope = Telescope()
        guiding = self.guiding
        self.guiding = False
        quiet = telescope.quiet
        telescope.set_quiet(True)
        telescope.send_speed('G')
        result = True
        
        try:
            if self.tracked_centroid is None:
                raise ValueError("No tracked star, required for calibration.")
            
            telescope.send_backlash_comp_dec(0)
            telescope.send_backlash_comp_ra(0)

            frame = self.camera.get_frame()
            centroid1 = self.detect_star(frame, search_near=self.tracked_centroid)  # Detect star
            print(f"#################1")
            if not centroid1:
                raise ValueError("failed to detect centroid1")

            centroid2 = self.move_and_detect(telescope, 'e', 20, centroid1)
            print(f"#################2")
            
            centroid3 = self.move_and_detect(telescope, 'e', 10, centroid2)
            print(f"#################3")

            centroid4 = self.move_and_detect(telescope, 'w', 10, centroid3)
            print(f"#################4")

            if with_backlash:

                # move north a bit
                centroid5 = self.move_and_detect(telescope, 'n', 20, centroid4)
                print(f"#################5")

                centroid6 = self.move_and_detect(telescope, 'n', 15, centroid5)
                print(f"#################6")

                centroid7 = self.move_and_detect(telescope, 's', 15, centroid6)
                print(f"#################7")

                #return scope
                telescope.send_correction('s',20)

            telescope.send_correction('w',20)
            print(f"#################END")


            if (not with_backlash and centroid1 and centroid2 and centroid3) or ( with_backlash and centroid1 and centroid2 and centroid3 and centroid4 and centroid5 and centroid6 and centroid7):
                dx = float(centroid3[0] - centroid1[0])
                dy = float(centroid3[1] - centroid1[1])
                angle_rad = -math.atan2(dy, dx)
                self.rotation_angle = math.degrees(angle_rad)
                self.last_status = f"Calibrated rotation angle: {self.rotation_angle:.1f} degrees"
                print(self.last_status)
                self.write_track_log(self.last_status)
                
                if with_backlash:
                    dx = float(centroid4[0] - centroid2[0])
                    dy = float(centroid4[1] - centroid2[1])
                    dx_rot, dy_rot = self.rotate_vector(dx, dy)
                    ra_arcsec = round(dx_rot * self.pixel_scale, 0)
                    telescope.send_backlash_comp_ra(abs(ra_arcsec))
                    print(f"#################backlash ra {ra_arcsec} arcsec")
                    
                    dx = float(centroid7[0] - centroid5[0])
                    dy = float(centroid7[1] - centroid5[1])
                    dx_rot, dy_rot = self.rotate_vector(dx, dy)
                    dec_arcsec = round(dy_rot * self.pixel_scale, 0)
                    telescope.send_backlash_comp_dec(abs(dec_arcsec))
                    print(f"#################backlash dec {dec_arcsec} arcsec")
                
        except ValueError as e:
            print(f"Calibration failed {e}.")
            result = False
        finally:
            self.guiding = guiding
            telescope.set_quiet(quiet)
            return result

    def enable_guiding(self, enable):
        if enable:
            self.guiding = True
        else:
            self.guiding=False
            telescope = Telescope()
            telescope.send_stop()

    def enable_dec_guiding(self, enable):
        self.dec_guiding = enable

    def run_autoguider(self):
        
        if not self.camera.is_initialized():
           print(f"Camera not initialized, aborting autoguider")
           return

        self.running = True
        telescope = Telescope()
        time.sleep(2)  # Wait for telescope to initialize
        telescope.get_info()
        last_time = time.perf_counter()
        last_frame = None

        while self.running:
            if time.perf_counter() - last_time >= self.guide_interval:  # Run once per period
                frame = self.camera.frame
                if frame is last_frame or frame is None:
                    time.sleep(0.01)    # frame not ready
                    continue

                self.last_frame_time = round(self.camera.last_frame_time, 2)
                last_frame = frame

                if self.tracked_centroid is None:
                    # Acquisition mode
                    self.acquire_star(frame=frame)
                    self.current_centroid = self.tracked_centroid
                else:
                    # Tracking mode
                    centroid = self.detect_star(frame, search_near=self.current_centroid)
                    #print(f"detect_star took {detect_time - frame_time:.2f} seconds")                    # Get current timestamp
                    if centroid and self.tracked_centroid:
                        self.star_locked = True
                        self.calculate_drift(centroid)
                        self.current_centroid = centroid
                        # Send correction to telescope
                        if self.guiding:
                            self.guide_scope( self.last_correction['ra_arcsec'], self.last_correction['dec_arcsec'])
                        # Log to tracking.log file
                        trackmsg =  f"pixel error({self.last_correction['dx']}, {self.last_correction['dy']}), RaDec error({self.last_correction['ra_arcsec']:.1f}, {self.last_correction['dec_arcsec']:.1f})"
                        self.write_track_log(trackmsg)
                        #print(trackmsg)
                    else:
                        self.star_locked = False
                        self.last_correction = null_correction
                        if self.guiding:
                            self.guide_scope(0,0)
                        if not centroid:
                            self.last_status = "LOST TRACKING: Tracked star not detected."
                            #print(self.last_status)
                            self.write_track_log(self.last_status)
                        else:
                            self.last_status = "NO TRACKING: No star being tracked."
                            #print(self.last_status)
                            self.write_track_log(self.last_status)

                end_time = time.perf_counter()
                self.last_loop_time = round(end_time - last_time, 2)
                self.data_ready = True
                last_time = time.perf_counter()

            time.sleep(0.01)  # Small sleep to prevent busy loop
