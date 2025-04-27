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

null_correction = { "ra": 0 , "dec": 0, "ra_px": 0, "dec_px": 0, "ra_arcsec": 0, "dec_arcsec": 0 , "ra_speed": 0, "dec_speed": 0}

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
        try:
            self.camera = Camera()
        except Exception as e:
            print(f"Camera not available")
            self.camera = None

        self.dec_guiding = False            # Declination guiding. Make sure that DEC does not disturb RA!!
        self.guiding = False                # Guiding status on/off
        self.guide_methods = {
            "PID": self.guide_scope_pid,
            "REL": self.guide_scope_rel,
            "ABS": self.guide_scope_abs,
        }
        self.guide_method = "PID"                 # guide method
        self.calibrating = False
        self.threshold = None               # Last threshold image
        self.last_frame_time = 0            # Last frame capture  time
        self.last_loop_time = 0             # Last loop time
        self.last_status = ""               # Last status message
        self.tracked_centroids = []         # Reference points we are tracking
        self.current_centroids = []         # Last position of tracked stars
        self.focus_metric = 0               # focus_metric of last detected star
        self.star_locked = False            # If autoguider currently has a guide star locked
        # last error and correction needed
        self.last_correction = null_correction
        self.centroid_image = None

        # tracking settings
        self.max_drift = 10                 # Integer for max_drift (0–50)
        self.star_size = 100                # Integer for star_size (1–100)
        self.gray_threshold = 150           # Integer for threshold (0–255)
        self.rotation_angle = 0.0           # Float for rotation angle (-180 to 180)
        self.pixel_scale = 3.6              # Float for pixel scale (0.1–10.0)
        self.guide_interval = 1.0           # Time period for tracking in seconds
        self.guide_pulse = 0.4              # Correction length: time between move start and move end (seconds)
        self.max_distance = 10             # Maximum distance to search for stars (pixels)
        
        self.save_frames = False            # Save each frame to disk
        self.output_dir = ""

        self.running = False
        self.lock = Lock()  # Thread lock for frame and threshold

        self.data_ready = False     # set to true when new processing data available for monitoring

        # Initialize PID controllers (persistent across calls)
        self.ra_pid = PIDController(Kp=2.0, Ki=0.5, Kd=0.5, dt=1.0)  # Tune these!
        self.dec_pid = PIDController(Kp=2.0, Ki=0.5, Kd=0.5, dt=1.0)

    def write_track_log(self, log_entry):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        day = datetime.datetime.now().strftime("%Y-%m-%d")
        with open(f"tracking_{day}.log", "a") as log_file:
            log_file.write(f"{timestamp}, {log_entry}\n")


    def detect_stars(self, frame, search_near_centroids, max_distance=None):
        if max_distance is None:
            max_distance = self.max_distance
        if frame is None:
            frame = self.camera.frame
        with self.lock:
            centroids, detail, thresh, focus_metric = self.analyzer.detect_stars(frame, 
                                                                 search_near=search_near_centroids, 
                                                                 gray_threshold = self.gray_threshold,
                                                                 star_size=self.star_size,
                                                                 max_distance=max_distance)
            self.centroid_image = detail
            self.threshold = thresh
            self.focus_metric = focus_metric
            return centroids

    def rotate_vector(self, dx, dy):
        """Rotate (dx, dy) vector by rotation_angle (degrees) counterclockwise."""
        angle_rad = math.radians(self.rotation_angle)
        new_dx = round(dx * math.cos(angle_rad) - dy * math.sin(angle_rad), 4)
        new_dy = round(dx * math.sin(angle_rad) + dy * math.cos(angle_rad), 4)
        return new_dx, new_dy

    def add_tracked_star(self, frame=None, centroid=None):
        found = self.find_nearby_centroid(centroid)
        if found is not None:
            self.last_status = f"Star already tracked at {centroid}"
            print(self.last_status)
            self.write_track_log(self.last_status)
            return None
        
        centroids = self.detect_stars(frame, search_near_centroids=[centroid] if centroid else None)
        if len(centroids)>0 and centroids[0] is not None:
            with self.lock:
                self.tracked_centroids.append(centroids[0])
                self.current_centroids.append(centroids[0])
                self.last_status = f"ADDED STAR at {centroids[0]}"
                print(self.last_status)
                self.write_track_log(self.last_status)
                return centroids
        else:
            self.last_status = f"NO STAR DETECTED at {centroid}"
            print(self.last_status)
            self.write_track_log(self.last_status)
            return None
    
    def find_nearby_centroid(self, centroid):
        for tracked_centroid in self.tracked_centroids:
            distance = math.sqrt((centroid[0] - tracked_centroid[0])**2 + (centroid[1] - tracked_centroid[1])**2)
            if distance < self.max_distance:
                return tracked_centroid
        return None

    def remove_tracked_star(self, centroid):
        found = self.find_nearby_centroid(centroid)
        if found is not None:
            with self.lock:
                index = self.tracked_centroids.index(found)
                del self.tracked_centroids[index]
                del self.current_centroids[index]
                self.last_status = f"REMOVED STAR at {found}"
                print(self.last_status)
                self.write_track_log(self.last_status)
                return True
        else:
            self.last_status = f"STAR NOT FOUND IN TRACKED STARS at {centroid} at distance {self.max_distance}"
            print(self.last_status)
            self.write_track_log(self.last_status)
            return False

    def remove_all_tracked_stars(self):
        with self.lock:
            self.tracked_centroids = []
            self.current_centroids = []
            self.last_status = f"REMOVED ALL TRACKED STARS"
            print(self.last_status)
            self.write_track_log(self.last_status)


    def guide_scope_abs(self, ra_arcsec_error, dec_arcsec_error):
        
        raerr = self.last_correction['ra_arcsec']
        decerr = self.last_correction['dec_arcsec']

        self.last_correction['ra'] = -1 if raerr > self.max_drift else 1 if raerr < -self.max_drift else 0
        if self.dec_guiding:
            self.last_correction['dec']= -1 if decerr > self.max_drift else 1 if decerr < -self.max_drift else 0

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
            dir = 'w' if self.last_correction["ra"] == -1 else 'e'
            with self.task_lock:
                self.pending_tasks += 1
            future = self.executor.submit(telescope.send_correction, dir, self.guide_pulse)
            future.add_done_callback(task_done_callback)  # Decrement counter when task finishes

        # DEC corrections
        if self.last_correction["dec"] != 0:
            dir = 's' if self.last_correction["dec"] == -1 else 'n'
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
        if not self.dec_guiding:
            dec_speed = 0
        self.last_correction['ra_speed']=ra_speed
        self.last_correction['dec_speed']=dec_speed
        telescope = Telescope()
        if not self.dec_guiding:
            dec_speed = 0

        telescope.send_start_movement_speed(ra_speed, dec_speed)

    def guide_scope_pid(self, ra_arcsec_error, dec_arcsec_error):

        # Compute speeds with PID
        ra_speed = self.ra_pid.compute(-ra_arcsec_error)  # Negative to correct RA
        dec_speed = self.dec_pid.compute(-dec_arcsec_error)

        # Clamp speeds to -99 to 99 arcseconds/10 seconds
        ra_speed = int(max(-99, min(ra_speed, 99)))
        dec_speed = int(max(-99, min(dec_speed, 99)))
        if not self.dec_guiding:
            dec_speed = 0

        # Log and send command
        self.last_correction['ra_speed']=ra_speed
        self.last_correction['dec_speed']=dec_speed

        telescope = Telescope()
        telescope.send_start_movement_speed(ra_speed, dec_speed)

    def guide_scope(self, ra_arcsec_error, dec_arcsec_error):
        # Call the appropriate method based on self.method
        guide_methodf = self.guide_methods.get(self.guide_method)
        if guide_methodf:
            guide_methodf(ra_arcsec_error, dec_arcsec_error)
        else:
            raise ValueError(f"Unknown guiding method: {self.guide_method}")

    def calculate_drift(self, centroids):
        # Initialize array to store dx, dy vectors
        if len(self.tracked_centroids)==0 or len(centroids)==0 or len(self.tracked_centroids)!=len(centroids):
            return False
        
        vectors = []
        
        # Calculate dx, dy for each centroid pair
        for i in range(len(centroids)):
            if not centroids[i] is None:
                dxi = round(float(centroids[i][0] - self.tracked_centroids[i][0]), 4)
                dyi = round(float(centroids[i][1] - self.tracked_centroids[i][1]), 4)
                vectors.append([dxi, dyi])
        
        # Convert to numpy array for vector operations
        vectors = np.array(vectors)
        
        # Calculate mean centroid (mean dx, mean dy)
        mean_centroid = np.mean(vectors, axis=0)  # Shape: (2,)
        
        # Calculate distances of each vector from mean centroid
        distances = np.sqrt(np.sum((vectors - mean_centroid) ** 2, axis=1))
        
        # Calculate mean and standard deviation of distances
        mean_distance = np.mean(distances)
        std_distance = np.std(distances)
        
        # Filter vectors within 2 sigma of mean distance
        mask = np.abs(distances - mean_distance) <= 2 * std_distance
        filtered_vectors = vectors[mask]
        
        # Calculate final mean centroid from filtered vectors
        final_mean_centroid = np.mean(filtered_vectors, axis=0) if len(filtered_vectors) > 0 else np.array([0.0, 0.0])
        
        dx = round(float(final_mean_centroid[0]), 4)
        dy = round(float(final_mean_centroid[1]), 4)
        dx_rot, dy_rot = self.rotate_vector(dx, dy)
        telescope = Telescope()
        ra_arcsec, dec_arcsec =self.pixels_to_arcseconds(dx_rot, dy_rot, self.pixel_scale, telescope.dec_deg)
        self.last_correction = {
            "ra_px": dx_rot, "dec_px": dy_rot,
            "ra_arcsec": ra_arcsec, "dec_arcsec": dec_arcsec,
            "ra": 0, "dec": 0,
            "ra_speed": 0, "dec_speed": 0

        }
        pec = telescope.scope_info["pec"]["progress"]
        self.last_status = f"TRACKING stars at:{centroids}, PEC:{pec}, ra px:{dx_rot:.1f}, dec px:{dy_rot:.1f}, ra arcsec:{ra_arcsec:.1f}, dec arcsec:{dec_arcsec:.1f}"
        #print(self.last_status)
        self.write_track_log(self.last_status)
        return True


    def pixels_to_arcseconds(self, dx, dy, pixel_scale, declination):
            """
            Convert pixel offsets to arcseconds, adjusting RA for declination.
            Args:
                dx (float): Pixel offset in x (RA direction).
                dy (float): Pixel offset in y (Dec direction).
                pixel_scale (float): Arcseconds per pixel at equator.
                declination (float): Telescope declination in degrees.
            Returns:
                tuple: (ra_arcsec, dec_arcsec) in arcseconds.
            """
            dec_rad = math.radians(declination)
            cos_dec = math.cos(dec_rad)
            # Avoid division by zero near poles
            ra_scale = pixel_scale / cos_dec if abs(cos_dec) > 1e-6 else pixel_scale / 1e-6
            ra_arcsec = dx * ra_scale
            dec_arcsec = dy * pixel_scale
            return round(ra_arcsec, 2), round(dec_arcsec, 2)

    def move_and_detect(self, telescope, move_direction, move_time, search_near):
        print(f" >> moving {move_direction} for {move_time} seconds...")
        telescope.send_correction(move_direction,move_time)  # Move scope west for 10s
        print("settling ... ")
        time.sleep(2)   # settling scope
        frame = self.camera.frame
        centroids = self.detect_stars(frame, search_near_centroids=[search_near], max_distance=100)  # Detect star
        if len(centroids)==0 or centroids[0] is None:
           raise ValueError("Failed to detect centroid")
        return centroids[0]

    def calibrate_angle(self, with_backlash=False):
        #TODO : wait for new frames!
        telescope = Telescope()
        guiding = self.guiding
        self.guiding = False
        quiet = telescope.quiet
        telescope.set_quiet(True)
        telescope.send_speed('G')
        result = True
        self.calibrating = True
        
        try:
            if len(self.tracked_centroids)==0:
                raise ValueError("No tracked star, required for calibration.")
            
            if with_backlash:
                telescope.send_backlash_comp_dec(0)
                telescope.send_backlash_comp_ra(0)
        
            frame = self.camera.frame

            centroids = self.detect_stars(frame, search_near_centroids=[self.tracked_centroids[0]])  # Detect star
            if len(centroids)==0:
                raise ValueError("Failed to detect centroid")
            centroid1 =  centroids[0]
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
            else:
                raise ValueError("Failed to detect centroids for calibration")
        except ValueError as e:
            print(f"Calibration failed {e}.")
            result = False
        except Exception as e:
            print(f"Calibration failed {e}.")
            result = False                
        finally:
            self.guiding = guiding
            self.calibrating = False
            telescope.set_quiet(quiet)
            return result

    def enable_guiding(self, enable):
        if enable:
            # reset PIDs!
            self.ra_pid.reset()
            self.dec_pid.reset()
            self.guiding = True
        else:
            self.guiding=False
            telescope = Telescope()
            telescope.send_stop()

    def enable_dec_guiding(self, enable):
        self.dec_guiding = enable


    def save_frame(self, frame):
        if frame is not None:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = os.path.join(self.output_dir, f"frame_{timestamp}.jpg")
            cv2.imwrite(filename, frame)
            print(f"Saved frame to {filename}")
        else:
            print("No frame to save.")

    def run_autoguider(self):
        
        if self.camera is None or not self.camera.is_initialized():
           print(f"Camera not initialized, aborting autoguider")
           return

        self.running = True
        telescope = Telescope()
        time.sleep(2)  # Wait for telescope to initialize
        telescope.get_info()
        last_time = time.perf_counter()
        last_frame = None
        last_save_time_counter = 0

        while self.running:
            if time.perf_counter() - last_time >= self.guide_interval:  # Run once per period
                frame = self.camera.frame
                if frame is last_frame or frame is None or self.calibrating:
                    time.sleep(0.01)    # frame not ready or calibrating
                    continue
                self.last_loop_time = round(time.perf_counter() - last_time, 2)
                last_time = time.perf_counter()
                self.last_frame_time = round(self.camera.last_frame_time, 2)
                last_frame = frame

                # Print tracked_centroids and current_centroids
                print(f"Tracked Centroids: {self.tracked_centroids}")
                print(f"Current Centroids: {self.current_centroids}")


                if len(self.tracked_centroids)==0:
                    # Acquisition mode
                    self.add_tracked_star(frame=frame)
                else:
                    # Tracking mode
                    centroids = self.detect_stars(frame, search_near_centroids=self.current_centroids)

                    any_centroid = False
                    for centroid in centroids:
                        if centroid is not None:
                            any_centroid = True
                            break

                    if any_centroid:
                        self.star_locked = True
                        if self.calculate_drift(centroids):
                            # Send correction to telescope
                            if self.guiding:
                                self.guide_scope( self.last_correction['ra_arcsec'], self.last_correction['dec_arcsec'])
                        # remember new currnt centroids; it some were not detected this time, keep the old ones
                        for i in range(len(centroids)):
                            if centroids[i] is not None:
                                self.current_centroids[i] = centroids[i]
                    else:
                        self.star_locked = False
                        self.last_correction = null_correction
                        if self.guiding:
                            self.guide_scope(0,0)

                        self.last_status = "LOST TRACKING: Tracked stars not detected."
                        #print(self.last_status)
                        self.write_track_log(self.last_status)

                self.data_ready = True
                last_save_time_counter += 1
                if self.save_frames and last_save_time_counter>10:
                    self.save_frame(frame)
                    last_save_time_counter = 0
            time.sleep(0.01)  # Small sleep to prevent busy loop

