import json
import os
from autoguider import Autoguider
from telescope import Telescope

# File path for settings
SETTINGS_FILE = 'settings.json'

class Settings:

    def __init__(self):
        self.settings = []

    def update_autoguider_settings(self, autoguider: Autoguider):
        self.settings["max_drift"] = autoguider.max_drift
        self.settings["star_size"] = autoguider.star_size
        self.settings["gray_threshold"] = autoguider.gray_threshold
        self.settings["rotation_angle"] = autoguider.rotation_angle
        self.settings["pixel_scale"] = autoguider.pixel_scale
        self.settings["exposure"] = autoguider.exposure
        self.settings["gain"] = autoguider.gain
        self.settings["integrate_frames"] = autoguider.integrate_frames
        self.settings["r_channel"] = autoguider.r_channel
        self.settings["g_channel"] = autoguider.g_channel
        self.settings["b_channel"] = autoguider.b_channel
        self.settings["set_fps"] = autoguider.set_fps

    def update_telescope_settings(self, telescope:Telescope):        
        self.settings["scope_info"] = telescope.scope_info        

    def set_autoguider_settings(self, autoguider:Autoguider):
        """Set autoguider properties from a dictionary."""
        try:
            # Channel settings (converted to float)
            autoguider.r_channel = float(self.settings["r_channel"])
            autoguider.g_channel = float(self.settings["g_channel"])
            autoguider.b_channel = float(self.settings["b_channel"])

            # Integer settings
            autoguider.gray_threshold = int(self.settings["gray_threshold"])
            autoguider.star_size = int(self.settings["star_size"])
            autoguider.integrate_frames = int(self.settings["integrate_frames"])

            # Float settings
            autoguider.pixel_scale = float(self.settings["pixel_scale"])
            autoguider.rotation_angle = float(self.settings["rotation_angle"])
            autoguider.max_drift = float(self.settings["max_drift"])

            # Method calls for exposure, gain, and fps
            autoguider.set_exposure(float(self.settings["exposure"]))
            autoguider.set_gain(float(self.settings["gain"]))
            autoguider.setfps(float(self.settings["set_fps"]))  # Corrected to match get_settings

        except KeyError as e:
            print(f"Missing property in settings: {e}")
        except (ValueError, TypeError) as e:
            print(f"Error converting property value: {e}")
        except AttributeError as e:
            print(f"Error setting autoguider attribute/method: {e}")


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