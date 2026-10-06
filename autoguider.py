import cv2
import numpy as np
import time
import math
import os
import datetime
from telescope import Telescope
from threading import Thread, Lock
import telescope
from v412_ctl import get_v4l2_controls
from analyzer import Analyzer
from camera import Camera
from concurrent.futures import ThreadPoolExecutor


# Autoguider module for PipiMount telescope system
# Provides PID control and guiding methods for RA and DEC axes
# ra : absolute correction in RA axis
# dec : absolute correction in DEC axis
# ra_px : ra error in pixels
# dec_px : dec error in pixels
# ra_axis_arcsec : ra axis error in arcseconds - ra_arcsec = ra_axis_arcsec * cos(declination)
# ra_arcsec : ra error in arcseconds
# dec_arcsec : dec error in arcseconds
# ra_speed : ra speed correction
# dec_speed : dec speed correction
null_correction = { "ra": 0 , "dec": 0, "ra_px": 0, "dec_px": 0, "ra_axis_arcsec": 0, "ra_arcsec": 0, "dec_arcsec": 0 , "ra_speed": 0, "dec_speed": 0,"timestamp": 0, "seeing": 0}

class PIDController:
    def __init__(self, Kp, Ki, Kd, alpha=0.9, dt=1.0):
        self.Kp = Kp        # Proportional gain
        self.Ki = Ki        # Integral gain
        self.Kd = Kd        # Derivative gain
        self.alpha = alpha  # Integral decay factor (0–1)
        self.dt = dt        # Time step (seconds)
        self.integral = 0.0 # Accumulated error
        self.prev_error = 0.0  # Last error
        self.edge_threshold = 20  # Minimum distance from the edge of the frame to consider a star for tracking

    def compute(self, error, dt=None):
        # dt: real time between the frames that produced the previous and current error
        if dt is None or dt <= 0:
            dt = self.dt
        # Proportional term
        P = self.Kp * error

        # Integral term with decay (decay scaled to elapsed time)
        self.integral = (self.alpha ** (dt / self.dt)) * self.integral + error * dt
        I = self.Ki * self.integral

        # Derivative term
        derivative = (error - self.prev_error) / dt
        D = self.Kd * derivative
        self.prev_error = error  # Update previous error

        # Total output
        output = P + I + D
        return output

    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0


""" Singleton Autoguider class """
class Autoguider:

    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Autoguider, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        self.executor = ThreadPoolExecutor(max_workers=4)  # Create a thread pool with 4 workers
        self.pending_tasks = 0  # Counter for pending tasks
        self.task_lock = Lock()  # Lock to ensure thread-safe updates to the counter

        self.analyzer = Analyzer()
        try:
            self.camera = Camera()
        except Exception as e:
            print(f"Camera not available")
            self.camera = None

        self.guiding = False                # Guiding status on/off

        # Guiding methods - what autoguider does when error is detected in the star position
        # "PID" - Proportional-Integral-Derivative control
        # "REL" - Relative movement: change telescope speed in RA/DEC based on the detected error using telecsope.send_start_movement_speed
        #         PipiTrek command !S
        # "ABS" - Absolute movement: change telescope position (move telescope by the calculated error) using telescope command telescope.send_correction
        #         PipiTrek command LXMove by time pulse
        # "MON" - Monitor only, no actual guiding
        self.guide_methods = {
            "PID": self.guide_scope_pid,
            "REL": self.guide_scope_rel,
            "ABS": self.guide_scope_abs,
            "MON": self.guide_scope_monitor,
        }

        self.guide_method_ra = "PID"        # guide method for RA
        self.guide_method_dec = "MON"       # guide method for DEC
        
        self.calibrating = False
        self.threshold = None               # Last threshold image
        self.last_frame_time = 0            # Last frame capture  time
        self.last_loop_time = 0             # Last loop time
        self.frame_dt = 1.0                 # Real time between the last two processed frames (s)
        self.frame_ts = 0                   # Capture timestamp of the frame being processed
        self.last_status = ""               # Last status message
        self.tracked_centroids = []         # Reference points we are tracking
        self.current_centroids = []         # Last position of tracked stars
        self.focus_metric = 0               # focus_metric of last detected star
        self.star_locked = False            # If autoguider currently has a guide star locked
        # last error and correction needed
        self.last_correction = null_correction
        self.centroid_image = None

        # tracking settings
        self.max_drift_ra = 1               # Integer for max_drift (0–50)
        self.max_drift_dec = 2              # Integer for max_drift (0–50)
        self.min_star_size = 2              # Integer for minimum star_size (1–100)
        self.max_star_size = 20             # Maximum allowed star size (pixels) for auto-finding stars
        self.gray_threshold = 150           # Integer for threshold (0–255)
        self.auto_threshold = True          # Whether to use auto thresholding
        self.last_auto_threshold_time = 0   # Timestamp of the last auto threshold calculation
        self.last_auto_threshold_interval = 60   # Interval in seconds for auto threshold recalculation
        self.auto_threshold_running = False # True while a background auto_threshold computation is in flight

        self.rotation_angle = 0.0           # Float for rotation angle (-180 to 180)
        self.pixel_scale = 3.2              # Float for pixel scale (0.1–10.0)
        self.guide_interval = 1.0           # Time period for tracking in seconds
        self.guide_pulse = 0.4              # Correction length: time between move start and move end (seconds)
        self.max_distance = 20              # Maximum distance to search for stars (pixels)
        self.edge_threshold = 20            # Minimum distance from the edge of the frame to consider a star valid (pixels)
        self.save_frames = False            # Save each frame to disk
        self.output_dir = ""

        self.running = False
        self.lock = Lock()  # Thread lock for frame and threshold

        self.data_ready = False     # set to true when new processing data available for monitoring

        # Initialize PID controllers (persistent across calls)
        self.ra_pid = PIDController(Kp=2.0, Ki=0.5, Kd=0.5, dt=1.0)  # Tune these!
        self.dec_pid = PIDController(Kp=2.0, Ki=0.5, Kd=0.5, dt=1.0)

    def _on_auto_threshold_done(self, future):
        try:
            self.gray_threshold = future.result()
        except Exception as e:
            print(f"auto_threshold failed: {e}")
        finally:
            self.auto_threshold_running = False

    def write_track_log(self, log_entry):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        day = datetime.datetime.now().strftime("%Y-%m-%d")
        with open(f"tracking_{day}.log", "a") as log_file:
            log_file.write(f"{timestamp}, {log_entry}\n")


    def detect_stars(self, frame, search_near_centroids, max_distance=None, max_stars=1):
        if max_distance is None:
            max_distance = self.max_distance
        if frame is None:
            frame = self.camera.frame
        with self.lock:
            centroids, detail, thresh, focus_metric = self.analyzer.detect_stars(frame, 
                                                                 search_near=search_near_centroids, 
                                                                 gray_threshold = self.gray_threshold,
                                                                 star_size=self.min_star_size,
                                                                 max_distance=max_distance,
                                                                 max_stars=max_stars,
                                                                 max_star_size=self.max_star_size)
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
            #print(self.last_status)
            self.write_track_log(self.last_status)
            return None


    # Automatically add tracked stars up to the specified number
    # heuristics: throw away stars larger than 10
    # heuristics: throw away stars that are near the edge of the frame
    def auto_add_tracked_stars(self, number_to_add):
        added_count = 0
        height, width = (self.camera.height, self.camera.width) if self.camera else (1080, 1920)
        print(f"calling detect stars")
        centroids = self.detect_stars(None, None, None, max_stars=number_to_add)
        print(f"Detected centroids: {centroids}")
        if len(centroids)>0 and centroids[0] is not None:
            self.remove_all_tracked_stars()
            with self.lock:
                print(f"Auto adding up to {number_to_add} tracked stars")
                for i in range(min(number_to_add, len(centroids))):
                    # Skip stars that are near the edge of the frame
                    if centroids[i][0] < self.edge_threshold or centroids[i][0] > (width - self.edge_threshold) or centroids[i][1] < self.edge_threshold or centroids[i][1] > (height - self.edge_threshold):
                        continue
                    self.tracked_centroids.append(centroids[i])
                    self.current_centroids.append(centroids[i])
                    self.last_status = f"ADDED STAR at {centroids[i]}"
                    print(self.last_status)
                    self.write_track_log(self.last_status)
                return centroids
        else:
            self.last_status = f"NO STAR DETECTED at auto_add_tracked_stars"
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

    def guide_scope_monitor(self, ra_arcsec_error, dec_arcsec_error, axis):
        # Monitor only, no actual guiding
        pass

    def guide_scope_abs(self, ra_arcsec_error, dec_arcsec_error, axis):
        
        raerr = self.last_correction['ra_axis_arcsec']
        decerr = self.last_correction['dec_arcsec']

        if axis == 'ra':
            self.last_correction['ra'] = -1 if raerr > self.max_drift_ra else 1 if raerr < -self.max_drift_ra else 0
        if axis == 'dec':
            self.last_correction['dec']= -1 if decerr > self.max_drift_dec else 1 if decerr < -self.max_drift_dec else 0

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
            telescope.send_abs_dec_correction(self.last_correction["dec"]) # 1 arcsec correction
            

    def guide_scope_rel(self, ra_arcsec_error, dec_arcsec_error, axis):
        # this should be PID controller!        

        telescope = Telescope()
        if axis == 'ra':
            ra_speed = int(-1*ra_arcsec_error)
            ra_speed = max(-15, min(ra_speed, 15))
            if abs(ra_arcsec_error) < self.max_drift_ra:
                ra_speed = 0
            self.last_correction['ra_speed']=ra_speed
            telescope.send_start_movement_speed_ra(ra_speed)
        
        if axis == 'dec':
            dec_speed = int(-1*dec_arcsec_error)
            dec_speed = max(-15, min(dec_speed, 15))
            if abs(dec_arcsec_error) < self.max_drift_dec:
                dec_speed = 0
            self.last_correction['dec_speed']=dec_speed
            telescope.send_start_movement_speed_dec(dec_speed)


    def guide_scope_pid(self, ra_arcsec_error, dec_arcsec_error, axis):

        # Compute speeds with PID
        # Use the real frame interval, clamped so a burst or a gap cannot spike the D/I terms
        dt = min(max(self.frame_dt, 0.3), 3.0)
        ra_speed = self.ra_pid.compute(-ra_arcsec_error, dt)  # Negative to correct RA
        dec_speed = self.dec_pid.compute(-dec_arcsec_error, dt)

        # Clamp speeds to -99 to 99 arcseconds/10 seconds
        ra_speed = int(max(-99, min(ra_speed, 99)))
        dec_speed = int(max(-99, min(dec_speed, 99)))
        
        # zero if inside max drift
        if abs(ra_arcsec_error) < self.max_drift_ra:
            ra_speed = 0
        if abs(dec_arcsec_error) < self.max_drift_dec:
            dec_speed = 0

        telescope = Telescope()
        # Log and send command
        if axis == 'ra':
            self.last_correction['ra_speed']=ra_speed
            telescope.send_start_movement_speed_ra(ra_speed)
        if axis == 'dec':
            self.last_correction['dec_speed']=dec_speed
            telescope.send_start_movement_speed_dec(dec_speed)


    def guide_scope(self, ra_arcsec_error, dec_arcsec_error):
        # Call the appropriate method based on self.method
        guide_methodf_ra = self.guide_methods.get(self.guide_method_ra)
        guide_methodf_dec = self.guide_methods.get(self.guide_method_dec)
        if guide_methodf_ra:
            guide_methodf_ra(ra_arcsec_error, dec_arcsec_error,'ra')
        else:
            raise ValueError(f"Unknown guiding method: {self.guide_method_ra}")
        if guide_methodf_dec:
            guide_methodf_dec(ra_arcsec_error, dec_arcsec_error,'dec')
        else:
            raise ValueError(f"Unknown guiding method: {self.guide_method_dec}")

    # Measure seeing based on current centroid shifts
    # If tracking multiple stars at the same time, and centroids were reset between frames,
    # this method will still calculate the seeing based on the relative shifts of the centroids
    def measure_static_seeing(self, centroids):
        if len(centroids) == 0:
            return 0.0
        distances = []
        for i in range(min(len(centroids), len(self.tracked_centroids))):
            if centroids[i] is not None and self.tracked_centroids[i] is not None:
                dxi = float(centroids[i][0] - self.tracked_centroids[i][0])
                dyi = float(centroids[i][1] - self.tracked_centroids[i][1])
                distances.append(np.sqrt(dxi**2 + dyi**2))
        # variation needs at least two stars
        if len(distances) < 2:
            return 0.0
        distances = np.array(distances)
        # mean absolute deviation of the per-star distances from their average
        variation = np.mean(np.abs(distances - np.mean(distances)))

        return float(variation)*self.pixel_scale

    # Measure seeing, alt method
    # Stop tracking, observe the drift over time
    # calculate seeing as drift from fitted straight line
    # TODO: implement seeing measurement based on centroid drift over time

    def measure_seeing(self):
        # still need to implement this method
        # stop tracking
        # wait for 1 minute,
        # record centroids during this time
        # fit a straight line to the drift
        # calculate deviations from the fitted line
        # return the mean deviation as the seeing
        return 0.0  # Placeholder return value until method is implemented

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
        #mean_centroid = np.mean(vectors, axis=0)  # Shape: (2,)
        
        # Calculate distances of each vector from mean centroid
        #distances = np.sqrt(np.sum((vectors - mean_centroid) ** 2, axis=1))
        
        # Calculate mean and standard deviation of distances
        #mean_distance = np.mean(distances)
        #std_distance = np.std(distances)
        
        # Filter vectors within 2 sigma of mean distance
        #mask = np.abs(distances - mean_distance) <= 2 * std_distance
        #filtered_vectors = vectors[mask]

        # filter any vectors larger than 20 pixels
        filtered_vectors = [v for v in vectors if abs(v[0]) <= 10 and abs(v[1]) <= 20]

        #filtered_vectors = vectors

        # Calculate final mean centroid from filtered vectors
        final_mean_centroid = np.mean(filtered_vectors, axis=0) if len(filtered_vectors) > 0 else np.array([0.0, 0.0])
        
        dx = round(float(final_mean_centroid[0]), 4)
        dy = round(float(final_mean_centroid[1]), 4)
        dx_rot, dy_rot = self.rotate_vector(dx, dy)
        telescope = Telescope()
        declination = telescope.dec_deg if telescope.dec_deg is not None else 0
        ra_axis_arcsec, dec_arcsec, ra_arcsec =self.pixels_to_arcseconds(dx_rot, dy_rot, self.pixel_scale, declination)
        self.last_correction = {
            "ra_px": dx_rot, "dec_px": dy_rot,
            "ra_axis_arcsec": ra_axis_arcsec, "ra_arcsec": ra_arcsec, "dec_arcsec": dec_arcsec,
            "ra": 0, "dec": 0,
            "ra_speed": 0, "dec_speed": 0,
            "timestamp": self.frame_ts, "seeing": 0
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
            ra_axis_arcsec = dx * ra_scale
            ra_arcsec = dx * pixel_scale
            dec_arcsec = dy * pixel_scale
            return round(ra_axis_arcsec, 2), round(dec_arcsec, 2), round(ra_arcsec, 2),

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

    # Calibrate the telescope's ra axis orientation in the camera frame
    # Rather than moving the telescope and measuring the star positions
    # stop tracking and observe the drift over time. This also allows us to measure seeing.
    # This way we eliminate errors caused by backlash and mechanical imperfections
    def calibrate_angle_with_tracking(self, num_seconds):

        if len(self.tracked_centroids)==0 or self.tracked_centroids[0] is None:
            return False
        
        telescope = Telescope()
        
        guiding = self.guiding
        self.guiding = False
        
        quiet = telescope.quiet
        telescope.set_quiet(True)
        
        telescope.send_stop()

        tracking = telescope.tracking()
        telescope.set_tracking(False)

        result = False
        self.calibrating = True

        start_time = time.time()

        _centroids = []
        _centroids.append(self.tracked_centroids[0])
        last_frame = None


        while time.time() - start_time < num_seconds:  # Run calibration loop for up to num_seconds

            frame, frame_ts = self.camera.latest
            if frame is last_frame or frame is None:
                time.sleep(0.05)    # frame not ready
                continue
            
            last_frame = frame

            centroids = self.detect_stars(frame, search_near_centroids=[_centroids[-1]])  # Detect star
            if len(centroids)==0:
                print("Failed to detect centroid")
                continue

            _centroids.append(centroids[0])


        # now let's analyze the centroids. First, perform linear fit through the detected centroids to determine the overall motion direction.

        if len(_centroids) < 2:
            print("Not enough centroids for calibration")
            result = False
        else:
            x = [c[0] for c in _centroids]
            y = [c[1] for c in _centroids]
            A = np.vstack([x, np.ones(len(x))]).T
            m, c = np.linalg.lstsq(A, y, rcond=None)[0]
            angle_rad = math.atan(m)
            self.rotation_angle = math.degrees(angle_rad)
            print(f"Calibrated rotation angle: {self.rotation_angle:.1f} degrees")
            result = True

        # next, let's calculate mean deviation from the fitted line
        if len(_centroids) >= 2:
            deviations = []
            for c in _centroids:
                y_fit = m * c[0] + c[1] - m * c[0]  
                deviations.append(abs(c[1] - y_fit))
            mean_deviation = np.mean(deviations)
            print(f"Mean deviation from fitted line: {mean_deviation:.2f} pixels")

        telescope.set_quiet(quiet)
        telescope.set_tracking(tracking)
        self.guiding = guiding
        self.calibrating = False
        return result

    # Calibrate the telescope's ra axis orientation in the camera frame
    # TODO: rather than moving the telescope and measuring the star positions
    # stop tracking and observe the drift over time to measure seeing
    # this way we eliminate errors caused by backlash and mechanical imperfections
    # TODO: move backlash calibration to another function

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

    def is_guiding(self):
        return self.guiding

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


    def save_frame(self, frame):
        if frame is not None:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = os.path.join(self.output_dir, f"frame_{timestamp}.jpg")
            cv2.imwrite(filename, frame)
            print(f"Saved frame to {filename}")
        else:
            print("No frame to save.")

    # reset centroids to current star positions
    def reset_centroids(self):
        self.tracked_centroids = self.current_centroids.copy()

    def perform_auto_threshold(self, frame=None):
        if frame is None:
            frame = self.camera.frame

        if frame is not None:
            self.auto_threshold_running = True
            future = self.executor.submit(self.analyzer.auto_threshold, frame.copy())
            future.add_done_callback(self._on_auto_threshold_done)

    def _update_loop_time(self, loop_time,cumulative_loop_time,loop_count,max_loop_time):
        self.last_loop_time = loop_time
        cumulative_loop_time += loop_time
        loop_count += 1
        avg_loop_time = cumulative_loop_time / loop_count if loop_count > 0 else 0
        if self.guide_interval == 0 and loop_count>3 and avg_loop_time > 0:
            max_loop_time = avg_loop_time
        if self.guide_interval > 0:
            max_loop_time = self.guide_interval
        if loop_count>10:
            loop_count = 0
            cumulative_loop_time = 0

        return cumulative_loop_time, loop_count, max_loop_time

    def _pid_watchdog(self, stopped_for_gap, last_time, max_loop_time, max_frame_gap_factor, telescope):
        # Watchdog: speed commands stay active on the mount until replaced, so stop it if frames stop arriving
        if (self.guiding and not stopped_for_gap and not self.calibrating
                and time.perf_counter() - last_time > max_loop_time * max_frame_gap_factor):
            stopped_for_gap = True
            self.last_correction['ra_speed'] = 0
            self.last_correction['dec_speed'] = 0
            self.ra_pid.reset()
            self.dec_pid.reset()
            telescope.send_start_movement_speed_ra(0)
            telescope.send_start_movement_speed_dec(0)
            self.last_status = f"FRAME GAP > {max_loop_time * max_frame_gap_factor}s: guiding paused"
            self.write_track_log(self.last_status)
        return stopped_for_gap

    def _performance_check(self, t_total, t_detect, t_guide):
        if self.frame_dt > 1.5 or t_total > 0.5:
            msg = (f"TIMING frame_gap={self.frame_dt:.2f}s loop={self.last_loop_time:.2f}s "
                    f"proc={t_total:.2f}s detect={t_detect:.2f}s guide={t_guide:.2f}s "
                    f"cam_cycle={self.camera.last_frame_time:.2f}s cam_read={self.camera.last_read_time:.2f}s "
                    f"cam_lock_wait={self.camera.last_lock_wait:.2f}s cam_mask={self.camera.last_mask_time:.2f}s "
                    f"read_failures={self.camera.read_failures_total}")
            print(msg, flush=True)
            self.write_track_log(msg)

    def _save_frame(self, frame, frame_ts, last_save_time_counter):
        last_save_time_counter += 1
        if self.save_frames and last_save_time_counter > 10:
            self.save_frame(frame)
            last_save_time_counter = 0
        return last_save_time_counter


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
        max_frame_gap_factor = 1.5     # seconds without a new frame before the mount is stopped
        stopped_for_gap = False
        max_loop_time = 1.0 if self.guide_interval == 0 else self.guide_interval  # Maximum allowed loop time in seconds
        cumulative_loop_time = 0
        loop_count = 0

        while self.running:
            # Watchdog: speed commands stay active on the mount until replaced, so stop it if frames stop arriving            
            stopped_for_gap = self._pid_watchdog(stopped_for_gap, last_time, max_loop_time, max_frame_gap_factor, telescope)

            # Reject frames arriving before the max_loop_time has elapsed (allow some leeway because auto mode averages loop times)
            if time.perf_counter() - last_time >= max_loop_time*0.75:
                frame, frame_ts = self.camera.latest
                if frame is last_frame or frame is None or self.calibrating:
                    time.sleep(0.01)    # frame not ready or calibrating
                    continue

                if stopped_for_gap:
                    # first frame after a gap: old PID history and dt are meaningless
                    stopped_for_gap = False
                    self.ra_pid.reset()
                    self.dec_pid.reset()
                    self.frame_dt = max_loop_time

                cumulative_loop_time, loop_count, max_loop_time = self._update_loop_time(round(time.perf_counter() - last_time, 2),cumulative_loop_time,loop_count,max_loop_time)

                last_time = time.perf_counter()
                self.last_frame_time = round(self.camera.last_frame_time, 2)
                last_frame = frame
                ts = frame_ts
                if self.frame_ts > 0 and ts > self.frame_ts:
                    self.frame_dt = ts - self.frame_ts
                self.frame_ts = ts
                t_proc = time.perf_counter()
                t_detect = t_guide = 0.0


                # Auto thresholding - run in a background thread to avoid blocking the main loop
                if (self.auto_threshold and not self.auto_threshold_running
                        and time.perf_counter() - self.last_auto_threshold_time >= self.last_auto_threshold_interval):
                    self.perform_auto_threshold(frame)
                    self.last_auto_threshold_time = time.perf_counter()
                
                # Print tracked_centroids and current_centroids
                #print(f"Tracked Centroids: {self.tracked_centroids}")
                #print(f"Current Centroids: {self.current_centroids}")


                if len(self.tracked_centroids)==0:
                    self.star_locked = False
                    self.last_correction = dict(null_correction, timestamp=ts)
                    
                else:
                    # Tracking mode
                    centroids = self.detect_stars(frame, search_near_centroids=self.current_centroids)
                    t_detect = time.perf_counter() - t_proc
                    any_centroid = False
                    for centroid in centroids:
                        if centroid is not None:
                            any_centroid = True
                            break

                    if any_centroid:
                        self.star_locked = True
                        if self.calculate_drift(centroids):
                            # Send correction to telescope
                            seeing = self.measure_static_seeing(centroids)
                            self.last_correction['seeing'] = seeing
                            if self.guiding:
                                t_g = time.perf_counter()
                                self.guide_scope( self.last_correction['ra_axis_arcsec'], self.last_correction['dec_arcsec'])
                                t_guide = time.perf_counter() - t_g
                        # remember new currnt centroids; it some were not detected this time, keep the old ones
                        for i in range(len(centroids)):
                            if centroids[i] is not None and len(self.current_centroids)>i:
                                self.current_centroids[i] = centroids[i]
                    else:
                        self.star_locked = False
                        self.last_correction = dict(null_correction, timestamp=ts)
                        if self.guiding:
                            self.guide_scope(0,0)

                        self.last_status = "LOST TRACKING: Tracked stars not detected."
                        #print(self.last_status)
                        self.write_track_log(self.last_status)

                self.data_ready = True
                t_total = time.perf_counter() - t_proc

                self._performance_check(t_total, t_detect, t_guide)
                last_save_time_counter = self._save_frame(frame, ts, last_save_time_counter)

            time.sleep(0.01)  # Small sleep to prevent busy loop

