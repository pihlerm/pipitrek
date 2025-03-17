import json
import os
from autoguider import Autoguider

# File path for settings
SETTINGS_FILE = 'settings.json'

class AutoguiderSettings:

    def get_settings(self, autoguider:Autoguider):
        
        return {
            "max_drift": autoguider.max_drift,
            "star_size": autoguider.star_size,
            "gray_threshold": autoguider.gray_threshold,
            "rotation_angle": autoguider.rotation_angle,
            "pixel_scale": autoguider.pixel_scale,
            "exposure": autoguider.exposure,
            "gain": autoguider.gain,
            "integrate_frames": autoguider.integrate_frames,
            "r_channel": autoguider.r_channel,
            "g_channel": autoguider.g_channel,
            "b_channel": autoguider.b_channel,
            "set_fps": autoguider.set_fps
        }

    def set_settings(self, autoguider:Autoguider, properties):
        """Set autoguider properties from a dictionary."""
        try:
            # Channel settings (converted to float)
            autoguider.r_channel = float(properties["r_channel"])
            autoguider.g_channel = float(properties["g_channel"])
            autoguider.b_channel = float(properties["b_channel"])

            # Integer settings
            autoguider.gray_threshold = int(properties["gray_threshold"])
            autoguider.star_size = int(properties["star_size"])
            autoguider.integrate_frames = int(properties["integrate_frames"])

            # Float settings
            autoguider.pixel_scale = float(properties["pixel_scale"])
            autoguider.rotation_angle = float(properties["rotation_angle"])
            autoguider.max_drift = float(properties["max_drift"])

            # Method calls for exposure, gain, and fps
            autoguider.set_exposure(float(properties["exposure"]))
            autoguider.set_gain(float(properties["gain"]))
            autoguider.setfps(float(properties["set_fps"]))  # Corrected to match get_settings

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
                    settings = json.load(f)
                print(f"Loaded settings from {SETTINGS_FILE}")
                return settings
            except json.JSONDecodeError as e:
                print(f"Error decoding {SETTINGS_FILE}: {e}")
            except Exception as e:
                print(f"Error loading settings: {e}")
        else:
            print(f"{SETTINGS_FILE} not found, using defaults")
        

    def save_settings(self, settings):
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=4)
            print(f"Saved settings to {SETTINGS_FILE}")
        except Exception as e:
            print(f"Error saving settings: {e}")