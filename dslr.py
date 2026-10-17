import atexit
import base64
import glob
import os
import shutil
import subprocess
import threading
import time

import cv2
import gpiod
import numpy as np

SONY_VENDOR_ID = "054c"
DSLR_A580_PRODUCT_ID = "048d"
SONY_MOUNT_POINT = "/mnt/sony"
IMAGE_SUBDIR = os.path.join("DCIM", "100MSDCF")
DOWNLOAD_DIR = "/root/astro/images"
# USB power relay: wiringPi GPIO2 = J2 header pin 13 = gpiochip0 line 15
USB_POWER_CHIP = "gpiochip0"
USB_POWER_LINE = 15
# Trigger relay: wiringPi GPIO0 = J2 header pin 11 = gpiochip0 line 23
TRIGGER_CHIP = "gpiochip0"
TRIGGER_LINE = 23

DEFAULT_RESET_CMD = "echo 0 > /sys/bus/usb/devices/2-1:1.0/2-1-port1/disable"


class DSLR:
    # single instance for now
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DSLR, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.mount_point = SONY_MOUNT_POINT
            self.dslr_image_dir = os.path.join(self.mount_point, IMAGE_SUBDIR)
            self.download_dir = DOWNLOAD_DIR
            self._mounted = False
            self._reset_cmd = DEFAULT_RESET_CMD
            self._usb_power_chip = None
            self._usb_power_line = None
            self._trigger_chip = None
            self._trigger_line = None
            self._triggered = False
            self._trigger_timer = None
            self._trigger_end = 0.0
            self._trigger_token = 0
            self._trigger_lock = threading.Lock()
            atexit.register(self._cleanup_on_exit)

    @staticmethod
    def _read_sysfs(path):
        try:
            with open(path) as f:
                return f.read().strip()
        except OSError:
            return None

    def _set_usb_power(self, state):
        """Drive the relay GPIO: True/1 = high, False/0 = low."""
        value = 1 if state else 0
        try:
            if self._usb_power_line is None:
                chip = gpiod.Chip(USB_POWER_CHIP)
                line = chip.get_line(USB_POWER_LINE)
                line.request(consumer="usb-power", type=gpiod.LINE_REQ_DIR_OUT,
                             default_vals=[value])
                self._usb_power_chip = chip
                self._usb_power_line = line
            self._usb_power_line.set_value(value)
            if state:
                # this wakes up sony a580 camera usb connection for some reason.
                print(f"Resetting USB power for Sony camera {self._reset_cmd}")
                subprocess.run(self._reset_cmd, shell=True, check=True)
            return True
        except OSError:
            return False

    def find_usb_port_disable(self):
        """Find the USB hub-port disable control for the connected Sony camera."""
        usb_path = self.find_usb_device()
        if not usb_path:
            return None

        device_name = os.path.basename(usb_path)
        if '.' not in device_name:
            return None

        hub_name, port_number = device_name.rsplit('.', 1)
        port_name = '%s-port%s' % (hub_name, port_number)
        for interface in glob.glob(
                os.path.join('/sys/bus/usb/devices', hub_name + ':*')):
            disable_path = os.path.join(interface, port_name, 'disable')
            if os.path.isfile(disable_path):
                return disable_path
        return None

    def find_usb_device(self):
        """Return the sysfs path of the Sony DSLR-A580 USB device, or None."""
        for dev in glob.glob('/sys/bus/usb/devices/*'):
            if (self._read_sysfs(os.path.join(dev, 'idVendor')) == SONY_VENDOR_ID and
                    self._read_sysfs(os.path.join(dev, 'idProduct')) == DSLR_A580_PRODUCT_ID):
                return os.path.realpath(dev)
        return None

    def find_block_device(self):
        """Return /dev path of the camera's mass storage partition (or disk), or None."""
        usb_path = self.find_usb_device()
        if not usb_path:
            return None
        disks = []
        for block in sorted(glob.glob('/sys/block/sd*')):
            if os.path.realpath(block).startswith(usb_path + os.sep):
                disks.append(os.path.basename(block))
        for disk in disks:
            parts = sorted(glob.glob('/sys/block/%s/%s[0-9]*' % (disk, disk)))
            if parts:
                return '/dev/' + os.path.basename(parts[0])
            return '/dev/' + disk
        return None

    def is_mounted(self):
        return self._mounted

    def mount(self):
        """Mount the camera (USB Mass Storage mode) to /mnt/sony.

        Returns (True, message) on success, (False, error) otherwise.
        """
        if self.is_triggered():
            return False, "Cannot mount while DSLR trigger is active"
        
        if self.is_mounted():
            return True, "Already mounted at %s" % self.mount_point

        self._set_usb_power(True)
        # first give USB power line a chance to stabilize
        time.sleep(5)

        if not self.find_usb_device():
            return False, "Sony DSLR-A580 USB device not found"

        device = self.find_block_device()
        if not device:
            self._set_usb_power(False)
            return False, ("Camera found but no storage device present; "
                           "set camera USB connection to Mass Storage")

        os.makedirs(self.mount_point, exist_ok=True)
        result = subprocess.run(['mount', device, self.mount_point],
                                capture_output=True, text=True)
        if result.returncode != 0:
            self._set_usb_power(False)
            return False, "mount failed: %s" % (result.stderr.strip() or result.returncode)

        reset_path = self.find_usb_port_disable()
        if reset_path:
            self._reset_cmd = "echo 0 > %s" % reset_path

        self._mounted = True
        return True, "Mounted %s at %s" % (device, self.mount_point)

    def unmount(self):
        result = None

        if self.is_triggered():
            return False, "Cannot unmount while DSLR trigger is active"

        if self.is_mounted():
            result = subprocess.run(['umount', self.mount_point], capture_output=True, text=True)
            
        self._set_usb_power(False)
        # first give USB power line a chance to stabilize
        time.sleep(3)

        if result is not None and result.returncode != 0:
            return False, "umount failed: %s" % (result.stderr.strip() or result.returncode)

        self._mounted = False
        return True, "Unmounted %s" % self.mount_point

    def _set_trigger_line(self, state):
        value = 1 if state else 0
        try:
            if self._trigger_line is None:
                chip = gpiod.Chip(TRIGGER_CHIP)
                line = chip.get_line(TRIGGER_LINE)
                line.request(consumer="dslr-trigger", type=gpiod.LINE_REQ_DIR_OUT,
                             default_vals=[value])
                self._trigger_chip = chip
                self._trigger_line = line
            self._trigger_line.set_value(value)
            return True
        except OSError:
            return False

    def is_triggered(self):
        with self._trigger_lock:
            return self._triggered

    def time_remaining(self):
        """Seconds left in the current trigger/exposure, or 0.0 if not triggered."""
        with self._trigger_lock:
            if not self._triggered:
                return 0.0
            return max(0.0, self._trigger_end - time.monotonic())

    def _release_trigger(self, token=None):
        """Timer callback; ignored if the timer was superseded by an abort."""
        with self._trigger_lock:
            if not self._triggered or token != self._trigger_token:
                return
            try:
                self._set_trigger_line(False)
            finally:
                self._triggered = False
                self._trigger_timer = None

    def abort_trigger(self):
        """Cancel a running trigger and set the GPIO low. Returns (ok, message)."""
        with self._trigger_lock:
            if not self._triggered:
                return False, "Not triggered"
            if self._trigger_timer is not None:
                self._trigger_timer.cancel()
                self._trigger_timer = None
            ok = self._set_trigger_line(False)
            self._triggered = False
        return ok, "Trigger aborted" if ok else "Failed to set trigger GPIO low"

    def _cleanup_on_exit(self):
        with self._trigger_lock:
            if self._trigger_timer is not None:
                self._trigger_timer.cancel()
                self._trigger_timer = None
            if self._trigger_line is not None:
                self._set_trigger_line(False)
            self._triggered = False
        self._set_usb_power(False)

    def trigger(self, duration=1, count=1):
        """Hold the trigger relay on for `duration` seconds (non-blocking), then switch it off.

        Returns (ok, message); refuses to start if already triggered.
        """
        if self.is_mounted():
            return False, "Cannot trigger while mounted"
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            return False, "Invalid duration"
        if duration <= 0:
            return False, "Invalid duration"
        with self._trigger_lock:
            if self._triggered:
                return False, "Already triggered"
            if not self._set_trigger_line(True):
                return False, "Failed to set trigger GPIO"
            self._triggered = True
            self._trigger_end = time.monotonic() + duration
            self._trigger_token += 1
            self._trigger_timer = threading.Timer(duration, self._release_trigger,
                                                  args=(self._trigger_token,))
            self._trigger_timer.daemon = True
            self._trigger_timer.start()
        return True, "Triggered for %s s" % duration

    def get_status(self):
        return {
            "mounted": self.is_mounted(),
            "triggered": self.is_triggered(),
            "time_remaining": self.time_remaining() if self.is_triggered() else 0
        }


    @staticmethod
    def _decode_image(name, data):
        """Decode JPEG or raw (ARW) data to a BGR image, or None."""
        buf = np.frombuffer(data, dtype=np.uint8)
        if name.lower().endswith(('.jpg', '.jpeg')):
            return cv2.imdecode(buf, cv2.IMREAD_COLOR)
        # Sony ARW embeds full-size JPEG previews; pick the largest decodable one
        best, best_pixels = None, 0
        pos = data.find(b'\xff\xd8\xff')
        for _ in range(12):
            if pos == -1:
                break
            img = cv2.imdecode(buf[pos:], cv2.IMREAD_COLOR)
            if img is not None and img.shape[0] * img.shape[1] > best_pixels:
                best, best_pixels = img, img.shape[0] * img.shape[1]
            pos = data.find(b'\xff\xd8\xff', pos + 3)
        if best is not None:
            return best
        try:
            import rawpy
            import io
            with rawpy.imread(io.BytesIO(data)) as raw:
                rgb = raw.postprocess(half_size=True, use_camera_wb=True, output_bps=8)
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception:
            return None

    def get_image(self, image_name, max_width=1600):
        """Return a downloaded image converted to a base64 JPEG data URL for display."""
        image_name = os.path.basename(image_name)
        if not self._is_image_in_local(image_name):
            self.download_images([image_name])
            if not self._is_image_in_local(image_name):
                raise ValueError("Failed to download %s" % image_name)
        img = self._decode_image(image_name, self.get_local_image_contents(image_name))
        if img is None:
            raise ValueError("Cannot decode %s" % image_name)
        if img.shape[1] > max_width:
            scale = max_width / img.shape[1]
            img = cv2.resize(img, (max_width, int(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise ValueError("JPEG encoding failed")
        return 'data:image/jpeg;base64,' + base64.b64encode(encoded.tobytes()).decode('ascii')

    def _scan_images(self, directory):
        return sorted(f for f in os.listdir(directory)
                      if os.path.isfile(os.path.join(directory, f)))

    def list_images(self):
        """Read the camera image directory."""
        if not self.is_mounted():
            return set()
        return set(self._scan_images(os.path.join(self.mount_point, IMAGE_SUBDIR)))

    def list_local_images(self):
        """Read the download image directory."""
        return set(self._scan_images(DOWNLOAD_DIR))

    def check_new_images(self):
        """Return full paths of images that arent found in the DOWNLOAD_DIR."""
        current = self.list_images()
        local = self.list_local_images()
        return sorted(current - local)

    def download_images(self, images, dest_dir=DOWNLOAD_DIR):
        """Copy images (file names or full paths) from the camera to dest_dir.

        Returns the list of destination paths.
        """
        os.makedirs(dest_dir, exist_ok=True)
        source_dir = os.path.join(self.mount_point, IMAGE_SUBDIR)
        copied = []
        for image in images:
            src = os.path.join(source_dir, image)
            dst = os.path.join(dest_dir, os.path.basename(src))
            shutil.copy2(src, dst)
            copied.append(dst)
        return copied

    def download_new_images(self, dest_dir=DOWNLOAD_DIR):
        """Download images that are new (not in the DOWNLOAD_DIR) to dest_dir."""
        new_images = self.check_new_images()
        return self.download_images(new_images, dest_dir)

    def get_local_image_contents(self, image_name):
        """Return the contents of a local image in the DOWNLOAD_DIR."""
        path = os.path.join(DOWNLOAD_DIR, image_name)
        with open(path, 'rb') as f:
            return f.read()

    def _is_image_in_local(self, image_name):
        """Check if an image exists in the local download directory."""
        return os.path.exists(os.path.join(DOWNLOAD_DIR, image_name))

    def _is_image_in_camera(self, image_name):
        """Check if an image exists in the camera's image directory."""
        if not self.is_mounted():
            return False
        return os.path.exists(os.path.join(self.mount_point, IMAGE_SUBDIR, image_name))
    
    def get_raw_images(self, imagelist, dest):
        """Zip raw images from local IMAGE_SUBDIR to the specified destination."""
        import zipfile
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with zipfile.ZipFile(dest, 'w') as zipf:
            for image_name in imagelist:
                if self._is_image_in_local(image_name):
                    zipf.write(os.path.join(DOWNLOAD_DIR, image_name), arcname=image_name)
        return os.path.basename(dest)