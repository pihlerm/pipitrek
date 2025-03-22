import cv2
import numpy as np
import time
import math


class Analyzer:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Analyzer, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True

#       How It Works
#       Initial Centroid:
#       Uses cv2.findContours() and cv2.moments() on the thresholded image to find the unweighted centroid of the largest or nearest star (same as your original code).
#       Returns None if no valid star is found (area too small or zero moment).
#       Cropping:
#       Defines a square region (crop_size x crop_size, e.g., 50x50 pixels) around the initial centroid (cx, cy).
#       Clamps edges to avoid exceeding image bounds (max, min).
#       Extracts this region from the original grayscale image (gray), not the thresholded one, to preserve brightness data.
#       Weighted Centroid:
#       Applies cv2.moments() to the cropped grayscale region (star_region).
#       Weights pixel positions by their intensity (0–255), giving a centroid skewed toward the brightest part of the star.
#       Falls back to the initial centroid if the weighted moment fails (e.g., m00 == 0).
#       Coordinate Adjustment:
#       Adds the crop’s top-left corner (x0, y0) to the weighted centroid (cx_weighted, cy_weighted) to get full-image coordinates (cx_full, cy_full).
#       Returns as a tuple of floats for sub-pixel precision.

    def detect_star(self, frame, search_near=None, gray_threshold=128, star_size=2):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        _, thresh = cv2.threshold(gray, gray_threshold, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, None, None

        # Find the largest or nearest contour
        if search_near is not None:
            distances = [np.linalg.norm(np.array(c.mean(axis=0)[0]) - np.array(search_near)) 
                        for c in contours if len(c) > 0]
            if distances:
                closest_idx = np.argmin(distances)
                largest = contours[closest_idx]
            else:
                largest = max(contours, key=cv2.contourArea)
        else:
            largest = max(contours, key=cv2.contourArea)

        # Check if contour is large enough
        if cv2.contourArea(largest) <= star_size:
            return None, None, None

        # Initial unweighted centroid and moments
        M = cv2.moments(largest)
        if M["m00"] == 0:
            return None, None, None
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        initial_centroid = (cx, cy)

        # Adaptive crop size based on moments
        area_diameter = np.sqrt(M["m00"])  # Rough diameter from area
        x_spread = np.sqrt(M["mu20"] / M["m00"]) if M["m00"] > 0 else 0  # Std dev in x
        y_spread = np.sqrt(M["mu02"] / M["m00"]) if M["m00"] > 0 else 0  # Std dev in y
        max_spread = max(area_diameter, x_spread, y_spread)
        crop_size = int(max_spread * 3)  # 3x spread for full star + buffer
        crop_size = max(crop_size, 10)   # Minimum size (e.g., 10 pixels)
        crop_size = min(crop_size, 50)   # Maximum size to avoid over-cropping

        # Ensure even crop_size for symmetry
        crop_size = crop_size + (crop_size % 2)  # Round up to even number
        half_size = crop_size // 2

        # Crop grayscale image
        x0 = max(0, cx - half_size)
        y0 = max(0, cy - half_size)
        x1 = min(gray.shape[1], cx + half_size)
        y1 = min(gray.shape[0], cy + half_size)
        star_region = gray[y0:y1, x0:x1]

        # Optional: Background subtraction
        background = np.median(star_region)
        star_region = cv2.subtract(star_region, int(background))
        
        
        # Make a copy of star_region
        enhanced_star_region = star_region.copy()

        # Apply gamma correction with gamma = 3.5
        gamma = 3.5
        inv_gamma = 1.0 / gamma
        lut = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        enhanced_star_region = cv2.LUT(enhanced_star_region, lut)

        # Weighted centroid
        M_weighted = cv2.moments(star_region)
        if M_weighted["m00"] == 0:
            print(f"Found rough centroid: {cx}, {cy}")
            return initial_centroid, enhanced_star_region, thresh  # Fallback
        
        cx_weighted = M_weighted["m10"] / M_weighted["m00"]
        cy_weighted = M_weighted["m01"] / M_weighted["m00"]

        # Adjust for crop origin
        cx_full = round(cx_weighted + x0, 4)  # Round to 4 decimal places
        cy_full = round(cy_weighted + y0, 4)  # Round to 4 decimal places

        print(f"Found precise centroid: {cx_full}, {cy_full}")
        return (cx_full, cy_full), enhanced_star_region, thresh
