import subprocess
import re

def get_v4l2_controls():
    try:
        # Run v4l2-ctl --list-ctrls-menus
        result = subprocess.run(['v4l2-ctl', '--list-ctrls-menus', '-d', '/dev/video0'], 
                               capture_output=True, 
                               text=True, 
                               check=True)
        output = result.stdout

        # Regex patterns with flexible whitespace (tabs/spaces)
        int_pattern = r"^\s*(\w+)\s+0x[0-9a-f]+\s+\(int\)\s*: min=(-?\d+) max=(-?\d+) step=(\d+) default=(-?\d+) value=(-?\d+)"
        bool_pattern = r"^\s*(\w+)\s+0x[0-9a-f]+\s+\(bool\)\s*: default=(\d+) value=(\d+)"
        menu_pattern = r"^\s*(\w+)\s+0x[0-9a-f]+\s+\(menu\)\s*: min=(\d+) max=(\d+) default=(\d+) value=(\d+)(?:\s+\((.*?)\))?"
        menu_item_pattern = r"^\s+(\d+):\s*(.+)$"  # Match indented items

        controls = {}
        current_menu = None

        # Process lines
        lines = output.splitlines()
        for i, line in enumerate(lines):
            # Skip empty lines or headers
            if not line.strip() or line.strip() in ['User Controls', 'Camera Controls']:
                continue

            # Parse integer controls
            int_match = re.match(int_pattern, line)
            if int_match:
                name, min_val, max_val, step, default, value = int_match.groups()
                controls[name] = {
                    'type': 'int',
                    'min': int(min_val),
                    'max': int(max_val),
                    'step': int(step),
                    'default': int(default),
                    'value': int(value)
                }
                current_menu = None
                continue

            # Parse boolean controls
            bool_match = re.match(bool_pattern, line)
            if bool_match:
                name, default, value = bool_match.groups()
                controls[name] = {
                    'type': 'bool',
                    'min': 0,
                    'max': 1,
                    'default': int(default),
                    'value': int(value)
                }
                current_menu = None
                continue

            # Parse menu controls
            menu_match = re.match(menu_pattern, line)
            if menu_match:
                name, min_val, max_val, default, value, label = menu_match.groups()
                controls[name] = {
                    'type': 'menu',
                    'min': int(min_val),
                    'max': int(max_val),
                    'default': int(default),
                    'value': int(value),
                    'label': label if label else '',
                    'options': {}
                }
                current_menu = name
                continue

            # Parse menu items
            item_match = re.match(menu_item_pattern, line)
            if item_match and current_menu:
                idx, text = item_match.groups()
                controls[current_menu]['options'][int(idx)] = text.strip()
                continue

        return controls

    except Exception as e:
        print(f"Error occurred while fetching v4l2 controls: {e}")
        return None


def set_v4l2_control(name, value):
    """
    Set a V4L2 control to a specified value.
    
    Args:
        name (str): Name of the control (e.g., 'brightness', 'auto_exposure').
        value (int): Value to set (must fit control's min/max range).
    
    Returns:
        bool: True if successful, False if failed.
    """
    try:
        # Construct the v4l2-ctl command
        cmd = ['v4l2-ctl', '-d', '/dev/video0', '--set-ctrl', f"{name}={value}"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Check if the command executed without errors
        if result.returncode == 0:
            print(f"Set {name} to {value} successfully")
            return True
        else:
            print(f"Failed to set {name} to {value}: {result.stderr}")
            return False

    except subprocess.CalledProcessError as e:
        print(f"Error setting {name} to {value}: {e.stderr}")
        return False
    except Exception as e:
        print(f"Unexpected error setting {name} to {value}: {e}")
        return False

def set_v4l2_controls(controls_to_set):
    for name, value in controls_to_set.items():
        set_v4l2_control(name, value)

def extract_v4l2_control_values(controls):
    """
    Extract current control values from controls
    
    Returns:
        dict: Dictionary of control names and their current values, or None if failed.
    """
    # Extract name:value pairs
    control_values = {name: info['value'] for name, info in controls.items()}
    return control_values

# Test it
if __name__ == "__main__":
    controls = get_v4l2_controls()
    print(f"Got {len(controls)} controls .. ")
    if controls:
        for name, info in controls.items():
            print(f"{name}: {info}")