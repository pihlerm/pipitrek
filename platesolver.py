
import subprocess
import os
import re

class PlateSolver:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PlateSolver, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True


    def solve(self, image_path, downsample=2, scale_low=50, scale_high=110, timeout=60):
        """
        Solves an image using astrometry.net and returns (RA, Dec, rotation in degrees).
        
        Parameters:
            image_path (str): Path to the input image (e.g., .png, .jpg, .fits).
        
        Returns:
            (ra_deg, dec_deg, rotation_deg) if solved, or raises Exception.
        """
        base = os.path.splitext(image_path)[0]
        args = [
            "solve-field", image_path,
            "--scale-units", "arcminwidth",
            "--scale-low", str(scale_low),
            "--scale-high", str(scale_high),
            "--downsample", str(downsample),
            "--cpulimit", str(timeout),
            "--overwrite",
            "--no-plots",
            "--dir", ".",  # Output to current dir
        ]

        print("Solving image:", image_path)
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            print(f"Solve failed:\n{result.stderr}")
            raise RuntimeError(f"Solve failed:\n{result.stderr}")

        # Check if solve succeeded
        if "Field 1: solved" not in result.stdout:
            raise RuntimeError("Image was not solved")

        # Parse stdout for center and rotation
        ra_match = re.search(r'Field center: \(RA,Dec\) = \(([+\-]?\d+\.\d+), ([+\-]?\d+\.\d+)\)', result.stdout)
        rot_match = re.search(r'Field rotation angle: up is ([+\-]?\d+\.\d+) degrees', result.stdout)
        scale_match = re.search(r'pixel scale ([\d.]+) arcsec/pix', result.stdout)

        if not ra_match or not rot_match or not scale_match:
            raise RuntimeError("Failed to parse RA/Dec/rotation/scale from output")

        ra = float(ra_match.group(1))
        dec = float(ra_match.group(2))
        rotation = 180 - float(rot_match.group(1))
        if rotation> 180:
            rotation = rotation-360
        if rotation< -180:
            rotation = rotation+360

        pixel_scale = float(scale_match.group(1))

        print(ra, dec, rotation, pixel_scale)

        return ra, dec, rotation, pixel_scale
