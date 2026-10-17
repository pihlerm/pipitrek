import json
import os
from autoguider import Autoguider
from telescope import Telescope
from camera import Camera

# File path for settings
SETTINGS_FILE = 'settings.json'

class Settings:

    def __init__(self):
        self.settings = {}

    def update_autoguider_settings(self, autoguider: Autoguider):
        
        self.settings["autoguider"] = {}
        self.settings["autoguider"]["max_drift_ra"] = autoguider.max_drift_ra
        self.settings["autoguider"]["max_drift_dec"] = autoguider.max_drift_dec
        self.settings["autoguider"]["star_size"] = autoguider.star_size
        self.settings["autoguider"]["gray_threshold"] = autoguider.gray_threshold
        self.settings["autoguider"]["guide_interval"] = autoguider.guide_interval
        self.settings["autoguider"]["guide_arcsec"] = autoguider.guide_arcsec
        self.settings["autoguider"]["guide_method_ra"] = autoguider.guide_method_ra
        self.settings["autoguider"]["guide_method_dec"] = autoguider.guide_method_dec
        self.settings["autoguider"]["max_star_size"] = autoguider.max_star_size
        self.settings["autoguider"]["auto_threshold"] = autoguider.auto_threshold
        self.settings["autoguider"]["error_filter_tau"] = autoguider.error_filter_tau
        self.settings["autoguider"]["pid"] =  { "ra" : {},"dec": {}}
        self.settings["autoguider"]["pid"]["ra"] = { "p":autoguider.ra_pid.Kp, "i": autoguider.ra_pid.Ki, "d": autoguider.ra_pid.Kd }
        self.settings["autoguider"]["pid"]["dec"] = { "p":autoguider.dec_pid.Kp, "i": autoguider.dec_pid.Ki, "d": autoguider.dec_pid.Kd }
        

    def update_camera_settings(self, camera: Camera):
        
        self.settings["camera"] = {}
        self.settings["camera"]["integrate_frames"] = camera.integrate_frames
        self.settings["camera"]["r_channel"] = camera.r_channel
        self.settings["camera"]["g_channel"] = camera.g_channel
        self.settings["camera"]["b_channel"] = camera.b_channel
        self.settings["camera"]["cam_fps"] = camera.cam_fps
        self.settings["camera"]["width"] = camera.width
        self.settings["camera"]["height"] = camera.height
        self.settings["camera"]["cam_mode"] = camera.cam_mode
        self.settings["camera"]["camera_controls"] = camera.get_direct_control_values()
        self.settings["camera"]["camera_color"] = camera.color
        self.settings["camera"]["rotation_angle"] = camera.rotation_angle
        self.settings["camera"]["pixel_scale"] = camera.pixel_scale

    def update_telescope_settings(self, telescope:Telescope):        
        self.settings["scope_info"] = telescope.scope_info        

    def set_autoguider_settings(self, autoguider: Autoguider):
        try:
            # Integer settings
            ag = self.settings.get("autoguider",{})
            autoguider.gray_threshold = int(ag.get("gray_threshold", 150))
            autoguider.star_size = int(ag.get("star_size", 10))
            autoguider.guide_arcsec = int(ag.get("guide_arcsec", 1))  

            # Float settings
            autoguider.max_drift_ra = float(ag.get("max_drift_ra", 5.0))
            autoguider.max_drift_dec = float(ag.get("max_drift_dec", 5.0))
            autoguider.guide_interval = float(ag.get("guide_interval", 1.0))
            autoguider.guide_method_ra = ag.get("guide_method_ra", "MON")
            autoguider.guide_method_dec = ag.get("guide_method_dec", "MON")
            autoguider.max_star_size = int(ag.get("max_star_size", 200))
            autoguider.auto_threshold = bool(ag.get("auto_threshold", True))
            autoguider.error_filter_tau = float(ag.get("error_filter_tau", 3))

            pid_settings = ag.get("pid")
            if pid_settings is not None:
                autoguider.ra_pid.Kp = float(pid_settings.get("ra", {}).get("p", 0.0))
                autoguider.ra_pid.Ki = float(pid_settings.get("ra", {}).get("i", 0.0))
                autoguider.ra_pid.Kd = float(pid_settings.get("ra", {}).get("d", 0.0))
                autoguider.dec_pid.Kp = float(pid_settings.get("dec", {}).get("p", 0.0))
                autoguider.dec_pid.Ki = float(pid_settings.get("dec", {}).get("i", 0.0))
                autoguider.dec_pid.Kd = float(pid_settings.get("dec", {}).get("d", 0.0))

            autoguider.output_dir = self.settings.get("output_dir")

        except (ValueError, TypeError) as e:
            print(f"Error converting property value: {e}")
        except AttributeError as e:
            print(f"Error setting autoguider attribute/method: {e}")

    def set_camera_settings(self, camera: Camera):
        try:
            # Channel settings (converted to float) with default values
            cams = self.settings.get("camera", {}) 
            camera.r_channel = float(cams.get("r_channel", 1.0))  # Default to 1.0
            camera.g_channel = float(cams.get("g_channel", 1.0))  # Default to 1.0
            camera.b_channel = float(cams.get("b_channel", 1.0))  # Default to 1.0

            # Integer settings with default values
            camera.integrate_frames = int(cams.get("integrate_frames", 10))  # Default to 10

            # Method calls for exposure, gain, and fps with default values
            camera.set_mode(cams.get("cam_mode", "MJPG"))
            camera.set_frame_size(int(cams.get("width", 1280)), int(cams.get("height", 720)))
            camera.setfps(float(cams.get("cam_fps", 30.0)))  # Default to 30.0
            camera.set_direct_controls(cams.get("camera_controls", []))
            camera.set_color(cams.get("camera_color", True))
            camera.rotation_angle = float(cams.get("rotation_angle", 0.0))
            camera.pixel_scale = float(cams.get("pixel_scale", 3.5))
            
            camera.output_dir = self.settings.get("output_dir")

        except (ValueError, TypeError) as e:
            print(f"Error converting property value: {e}")
        except AttributeError as e:
            print(f"Error setting camera attribute/method: {e}")

    def set_telescope_settings(self, telescope:Telescope):
        """Set telescope properties from a dictionary."""
        try:
            # PEC position is best set directly on the telescope if needed
            #telescope.send_PEC_position(int(self.settings["scope_info"]["pec"]["progress"]))

            scope_info = self.settings["scope_info"]
            # make sure certain settings exist
            if "latitude" in self.settings:
                telescope.latitude = self.settings["latitude"]
            if "longitude" in self.settings:
                telescope.longitude = self.settings["longitude"]
            
            if "pier" not in scope_info:
                scope_info["pier"] = "E"
            if "tracking" not in scope_info:
                scope_info["tracking"] = False
            if "slewing" not in scope_info:
                scope_info["slewing"] = False
            if "PEC" not in scope_info:
                scope_info["PEC"] = {}
            if "progress" not in scope_info["PEC"]:
                scope_info["PEC"]["progress"] = 0

            telescope.scope_info = scope_info
            telescope.send_pier(scope_info["pier"])
            telescope.send_tracking(scope_info["tracking"])

        except KeyError as e:
            print(f"Missing property in settings: {e}")
        except (ValueError, TypeError) as e:
            print(f"Error converting property value: {e}")
        except AttributeError as e:
            print(f"Error setting autoguider attribute/method: {e}")


    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    self.settings = json.load(f)
                    if "output_dir" not in self.settings:
                        self.settings["output_dir"] = "/root/astro/images"
                    os.makedirs(self.settings["output_dir"], exist_ok=True)
                print(f"Loaded settings from {SETTINGS_FILE}")
            except json.JSONDecodeError as e:
                print(f"Error decoding {SETTINGS_FILE}: {e}")
            except Exception as e:
                print(f"Error loading settings: {e}")
        else:
            print(f"{SETTINGS_FILE} not found, using defaults")
        

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
            print(f"Saved settings to {SETTINGS_FILE}")
        except Exception as e:
            print(f"Error saving settings: {e}")