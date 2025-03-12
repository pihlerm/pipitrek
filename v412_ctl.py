import subprocess
import re

def get_v4l2_controls():
    # Run v4l2-ctl command and capture output
    result = subprocess.run(['v4l2-ctl', '--list-ctrls'], 
                           capture_output=True, 
                           text=True, 
                           check=True)
    output = result.stdout

    # Regex patterns to match control lines
    int_pattern = r"(\w+) 0x[0-9a-f]+ \(int\)\s+: min=(-?\d+) max=(-?\d+) step=(\d+) default=(-?\d+) value=(-?\d+)"
    bool_pattern = r"(\w+) 0x[0-9a-f]+ \(bool\)\s+: default=(\d+) value=(\d+)"
    menu_pattern = r"(\w+) 0x[0-9a-f]+ \(menu\)\s+: min=(\d+) max=(\d+) default=(\d+) value=(\d+)(?: \((.*?)\))?"

    controls = {}

    # Parse integer controls
    for match in re.finditer(int_pattern, output):
        name, min_val, max_val, step, default, value = match.groups()
        controls[name] = {
            'type': 'int',
            'min': int(min_val),
            'max': int(max_val),
            'step': int(step),
            'default': int(default),
            'value': int(value)
        }

    # Parse boolean controls
    for match in re.finditer(bool_pattern, output):
        name, default, value = match.groups()
        controls[name] = {
            'type': 'bool',
            'min': 0,
            'max': 1,
            'default': int(default),
            'value': int(value)
        }

    # Parse menu controls
    for match in re.finditer(menu_pattern, output):
        name, min_val, max_val, default, value, label = match.groups()
        controls[name] = {
            'type': 'menu',
            'min': int(min_val),
            'max': int(max_val),
            'default': int(default),
            'value': int(value),
            'label': label if label else ''
        }

    return controls