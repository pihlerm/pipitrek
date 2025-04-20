import cv2
import numpy as np
from photutils import CircularAperture, CircularAnnulus, aperture_photometry
from photutils.detection import DAOStarFinder
from photutils.background import MedianBackground
from astropy.stats import sigma_clipped_stats
from astropy.io import fits
from skimage.feature import blob_log
from skimage.color import rgb2gray
from skimage.util import img_as_float
from scipy.ndimage import gaussian_filter

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

    def detect_stars(self, frame, search_near=None, gray_threshold=128, star_size=2):
        result = []
        enhanced_with_profile = None
        thresh = None
        focus_metric = 0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        _, thresh = cv2.threshold(gray, gray_threshold, 255, cv2.THRESH_BINARY)
        # Pre-filter small contours with morphological opening
        #kernel_size = int(np.sqrt(star_size) / 2) * 2 + 1  # Rough estimate, ensure odd
        #kernel = np.ones((kernel_size, kernel_size), np.uint8)
        #thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            if search_near is None:
                # Find the largest contour if no search_near provided
                centroid, enhanced_with_profile, thresh, focus_metric = self._detect_star(frame, thresh, gray, contours, search_near=None, gray_threshold=gray_threshold, star_size=star_size)
                result.append(centroid)
            else:
                for near in search_near:
                    if enhanced_with_profile is None:
                        centroid, enhanced_with_profile, thresh, focus_metric = self._detect_star(frame, thresh, gray, contours, search_near=near, gray_threshold=gray_threshold, star_size=star_size)
                    else:
                        centroid, _, _, _ = self._detect_star(frame, thresh, gray, contours, search_near=near, gray_threshold=gray_threshold, star_size=star_size)
                    result.append(centroid)
        
        return result, enhanced_with_profile, thresh, focus_metric

    def _detect_star(self, frame, thresh, gray, contours, search_near=None, gray_threshold=128, star_size=2, max_dist=10):
        
        # Find the largest or nearest contour with size > star_size
        largest = None
        if search_near is not None:
            # Calculate all distances first
            distance_data = []
            search_near = np.array(search_near)
            for c in contours:
                if len(c) > 0:
                    mean_pos = np.mean(c, axis=0)[0]
                    distance = np.linalg.norm(mean_pos - search_near)
                    distance_data.append((distance, c))
            
            if distance_data:
                # Sort by distance
                distance_data.sort(key=lambda x: x[0])
                # Check areas in order until we find one > star_size
                for distance, contour in distance_data:
                    area = cv2.contourArea(contour)
                    if area > star_size and distance < max_dist:
                        largest = contour
                        break
        else:
            largest = max(contours, key=cv2.contourArea)

        if largest is None:
            #print("No valid star found")
            return None, None, thresh, 0
        
        # Check if contour is large enough
        size = cv2.contourArea(largest)
        if size <= star_size:
            #print(f"Size too small {size}, elements={len(contours)}")
            return None, None, thresh, 0

        # Initial unweighted centroid and moments
        M = cv2.moments(largest)
        if M["m00"] == 0:
            return None, None, thresh, size
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        initial_centroid = (cx, cy)

        # Adaptive crop size based on moments
        area_diameter = np.sqrt(M["m00"])  # Rough diameter from area
        x_spread = np.sqrt(M["mu20"] / M["m00"]) if M["m00"] > 0 else 0  # Std dev in x
        y_spread = np.sqrt(M["mu02"] / M["m00"]) if M["m00"] > 0 else 0  # Std dev in y
        max_spread = max(area_diameter, x_spread, y_spread)
        crop_size = int(max_spread * 3)  # 3x spread for full star + buffer
        crop_size = max(crop_size, 20)   # Minimum size (e.g., 10 pixels)
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

        # Weighted centroid
        M_weighted = cv2.moments(star_region)
        if M_weighted["m00"] == 0:
            #print(f"Found rough centroid: {cx}, {cy}")
            return initial_centroid, enhanced_star_region, thresh, 0  # Fallback
        
        cx_weighted = M_weighted["m10"] / M_weighted["m00"]
        cy_weighted = M_weighted["m01"] / M_weighted["m00"]

        # Adjust for crop origin
        cx_full = round(cx_weighted + x0, 4)  # Round to 4 decimal places
        cy_full = round(cy_weighted + y0, 4)  # Round to 4 decimal places

        # Calculate profile and focus metric
        focus_metric = float(np.std(enhanced_star_region))  # Standard deviation as focus metric
        enhanced_with_profile = self.calculate_profile(enhanced_star_region, cx_weighted, cy_weighted)
        #print(f"Found precise centroid: {cx_full}, {cy_full}")

        return (cx_full, cy_full), enhanced_with_profile, thresh, focus_metric


    def calculate_profile(self, enhanced_star_region, cx_weighted, cy_weighted):
        # Calculate horizontal intensity profile (left to right)
        h, w = enhanced_star_region.shape
        profile = np.zeros(w, dtype=np.float32)  # One value per column

        # Average intensity across each column
        for x in range(w):
            column = enhanced_star_region[:, x]
            profile[x] = np.mean(column) if column.size > 0 else 0

        # Normalize profile to fit image height (0 to h-1)
        profile_max = np.max(profile)
        profile_min = np.min(profile)
        if profile_max > profile_min:  # Avoid division by zero
            profile_normalized = (profile - profile_min) / (profile_max - profile_min) * (h - 1)
        else:
            profile_normalized = np.zeros_like(profile)  # Flat line if no variation

        # Convert to BGR for yellow plotting
        # Apply gamma correction with gamma = 3.5
        gamma = 3.5
        inv_gamma = 1.0 / gamma
        lut = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        enhanced_star_region = cv2.LUT(enhanced_star_region, lut)

        enhanced_star_region_bgr = cv2.cvtColor(enhanced_star_region, cv2.COLOR_GRAY2BGR)
        yellow = (0, 255, 255)  # BGR: Yellow

        # Plot profile as a line graph from left to right
        for x in range(w - 1):
            y1 = int(h - 1 - profile_normalized[x])  # Invert y (0 at bottom)
            y2 = int(h - 1 - profile_normalized[x + 1])
            cv2.line(enhanced_star_region_bgr, (x, y1), (x + 1, y2), yellow, 1)

        return enhanced_star_region_bgr
    

    def analyze_snr(self, img, snr_threshold=1.5, detection_threshold_sigma=4, fwhm = 3):
        
        print(f"analyze_snr start")
        #ensure frame is black and white
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

        snr_threshold = float(snr_threshold)
        fwhm = float(fwhm)
        detection_threshold_sigma = float(detection_threshold_sigma)

        gaussian_sigma = 1.0
        image = img.astype(np.float32)

        # === BACKGROUND STATISTICS ===
        mean, median, std = sigma_clipped_stats(image, sigma=3.0)
        #print(f"Background: mean={mean:.2f}, median={median:.2f}, std={std:.2f}")

        smoothed = gaussian_filter(image, sigma=gaussian_sigma)
        #sigma_clip = SigmaClip(sigma=3.)
        bkg_estimator = MedianBackground()
        bkg = bkg_estimator(smoothed)
        #std = np.std(smoothed - bkg)
        #print(f"std={std:.2f}")

        # === STAR DETECTION ===
        daofind = DAOStarFinder(fwhm=fwhm, threshold=detection_threshold_sigma * std)
        sources = daofind(smoothed - bkg)
        #sources = daofind(image - median)

        if sources is None or len(sources) == 0:
            print("No stars found!")
            exit()

        # === PHOTOMETRY ===
        results = []

        for row in sources:
            snr_info = self.estimate_star_snr(image, (row['xcentroid'], row['ycentroid']))
            if snr_info is not None and snr_info['snr'] > snr_threshold:
                results.append(snr_info)

        for star in results:
            print(f"Star at ({star['x']:.2f}, {star['y']:.2f}): SNR={star['snr']:.2f}, Signal={star['signal']:.2f}, Background={star['background']:.2f}, Noise={star['noise']:.2f}")
        
        print(f"analyze_snr found {len(results)} stars")        
        return results
        
    # === SNR ESTIMATION ===
    def estimate_star_snr(self,image, position, cutout_size=30, smooth_sigma=1.0, threshold_sigma=3.0):
        
        height, width = image.shape
        x, y = int(position[0]), int(position[1])
        half = cutout_size // 2

        if y - half < 0 or y + half >= image.shape[0] or x - half < 0 or x + half >= image.shape[1]:
            return None  # skip edge stars

        cutout = image[y - half:y + half + 1, x - half:x + half + 1]
        mean, median, std = sigma_clipped_stats(cutout, sigma=3.0)

        smoothed = gaussian_filter(cutout, sigma=smooth_sigma)
        star_mask = smoothed > (median + threshold_sigma * std)

        if not np.any(star_mask):
            return None

        star_pixels = cutout[star_mask]
        n_pix = star_pixels.size

        signal = np.sum(star_pixels - median)
        noise = np.sqrt(np.sum(star_pixels) + n_pix * std ** 2)

        if noise <= 0:
            snr = 0
        else:
            snr = signal / noise

        return {
            'x': float(x),
            'y': float(y),
            'xrel': float(x/width),
            'yrel': float(y/height),
            'signal': float(signal),
            'noise': float(noise),
            'background': float(mean),
            'snr': float(snr),
            'n_pixels': int(n_pix)
        }
