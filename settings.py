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
        self.settings["max_drift"] = autoguider.max_drift
        self.settings["star_size"] = autoguider.star_size
        self.settings["gray_threshold"] = autoguider.gray_threshold
        self.settings["rotation_angle"] = autoguider.rotation_angle
        self.settings["pixel_scale"] = autoguider.pixel_scale
        self.settings["guide_interval"] = autoguider.guide_interval
        self.settings["guide_pulse"] = autoguider.guide_pulse
        self.settings["dec_guiding"] = autoguider.dec_guiding
        self.settings["pid"] =  { "ra" : {},"dec": {}}
        self.settings["pid"]["ra"] = { "p":autoguider.ra_pid.Kp, "i": autoguider.ra_pid.Ki, "d": autoguider.ra_pid.Kd }
        self.settings["pid"]["dec"] = { "p":autoguider.ra_pid.Kp, "i": autoguider.ra_pid.Ki, "d": autoguider.ra_pid.Kd }
        

    def update_camera_settings(self, camera: Camera):
        self.settings["integrate_frames"] = camera.integrate_frames
        self.settings["r_channel"] = camera.r_channel
        self.settings["g_channel"] = camera.g_channel
        self.settings["b_channel"] = camera.b_channel
        self.settings["cam_fps"] = camera.cam_fps
        self.settings["width"] = camera.width
        self.settings["height"] = camera.height
        self.settings["cam_mode"] = camera.cam_mode
        self.settings["camera_controls"] = camera.get_direct_control_values()
        self.settings["camera_color"] = camera.color

    def update_telescope_settings(self, telescope:Telescope):        
        self.settings["scope_info"] = telescope.scope_info        

    def set_autoguider_settings(self, autoguider: Autoguider):
        try:
            # Integer settings
            autoguider.gray_threshold = int(self.settings.get("gray_threshold", 150))
            autoguider.star_size = int(self.settings.get("star_size", 10))
            autoguider.guide_pulse = float(self.settings.get("guide_pulse", 0.4))  

            # Float settings
            autoguider.pixel_scale = float(self.settings.get("pixel_scale", 3.5))
            autoguider.rotation_angle = float(self.settings.get("rotation_angle", 0.0))
            autoguider.max_drift = float(self.settings.get("max_drift", 5.0))
            autoguider.guide_interval = float(self.settings.get("guide_interval", 1.0))
            autoguider.dec_guiding = bool(self.settings.get("dec_guiding", False))
            autoguider.output_dir = self.settings.get("output_dir")

            pid_settings = self.settings.get("pid")
            if pid_settings is not None:
                autoguider.ra_pid.Kp = float(pid_settings.get("ra", {}).get("p", 0.0))
                autoguider.ra_pid.Ki = float(pid_settings.get("ra", {}).get("i", 0.0))
                autoguider.ra_pid.Kd = float(pid_settings.get("ra", {}).get("d", 0.0))
                autoguider.dec_pid.Kp = float(pid_settings.get("dec", {}).get("p", 0.0))
                autoguider.dec_pid.Ki = float(pid_settings.get("dec", {}).get("i", 0.0))
                autoguider.dec_pid.Kd = float(pid_settings.get("dec", {}).get("d", 0.0))

        except (ValueError, TypeError) as e:
            print(f"Error converting property value: {e}")
        except AttributeError as e:
            print(f"Error setting autoguider attribute/method: {e}")

    def set_camera_settings(self, camera: Camera):
        try:
            # Channel settings (converted to float) with default values
            camera.r_channel = float(self.settings.get("r_channel", 1.0))  # Default to 1.0
            camera.g_channel = float(self.settings.get("g_channel", 1.0))  # Default to 1.0
            camera.b_channel = float(self.settings.get("b_channel", 1.0))  # Default to 1.0

            # Integer settings with default values
            camera.integrate_frames = int(self.settings.get("integrate_frames", 10))  # Default to 10

            # Method calls for exposure, gain, and fps with default values
            camera.set_mode(self.settings.get("cam_mode", "MJPG"))
            camera.set_frame_size(int(self.settings.get("width", 1280)), int(self.settings.get("height", 720)))
            camera.setfps(float(self.settings.get("cam_fps", 30.0)))  # Default to 30.0
            camera.set_direct_controls(self.settings.get("camera_controls", []))
            camera.set_color(self.settings.get("camera_color", True))
            camera.output_dir = self.settings.get("output_dir")

        except (ValueError, TypeError) as e:
            print(f"Error converting property value: {e}")
        except AttributeError as e:
            print(f"Error setting camera attribute/method: {e}")

    def set_telescope_settings(self, telescope:Telescope):
        """Set telescope properties from a dictionary."""
        try:
            # Channel settings (converted to float)
            telescope.scope_info = self.settings["scope_info"]
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