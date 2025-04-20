import subprocess
import re


def list_cameras():
    """
    List all connected cameras with their names, indices, and USB ports using v4l2-ctl.
    :return: A list of dictionaries containing camera names, indices, and USB ports.
    """
    try:
        # Run v4l2-ctl to list devices
        result = subprocess.run(['v4l2-ctl', '--list-devices'], capture_output=True, text=True, check=True)
        output = result.stdout
        # Parse the output
        cameras = []
        lines = output.splitlines()
        current_camera = None

        for line in lines:
            if not line.strip():
                continue

            # Match camera name (e.g., "USB Camera (usb-c90c0000.usb-1.3):")
            if not line.startswith('\t'):
                name = line.split(':')[0]
                # Extract USB port (e.g., "usb-1.3") using regex
                port_match = re.search(r'usb-[^\s)]+-([\d\.]+)', name)
                port = port_match.group(1) if port_match else None
                current_camera = {'name': name, 'index': None, 'port': port}
                cameras.append(current_camera)
            else:
                # Match device node (e.g., "/dev/video0")
                match = re.match(r'\t(/dev/video\d+)', line)
                if match and current_camera:
                    device_path = match.group(1)
                    index = int(device_path.split('video')[-1])  # Extract index from /dev/videoX
                    if current_camera['index'] is None:
                        current_camera['index'] = index
        
        for camera in cameras:
            print(f"Found camera: {camera['name']}, Index: {camera['index']}, Port: {camera['port']}")

        return cameras

    except subprocess.CalledProcessError as e:
        print(f"Error running v4l2-ctl: {e.stderr}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []
    
def get_v4l2_controls(camera_index):
    try:
        # Run v4l2-ctl --list-ctrls-menus
        result = subprocess.run(['v4l2-ctl', '--list-ctrls-menus', '-d', '/dev/video' + str(camera_index)], 
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


def set_v4l2_control(name, value, camera_index):
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
        cmd = ['v4l2-ctl', '-d', '/dev/video'+str(camera_index), '--set-ctrl', f"{name}={value}"]
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

def set_v4l2_controls(controls_to_set, camera_index):
    for name, value in controls_to_set.items():
        set_v4l2_control(name, value, camera_index)

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