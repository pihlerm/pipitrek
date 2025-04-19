import cv2
import numpy as np
import logging
import time

# Setup logging
logging.basicConfig(level=logging.DEBUG)

def capture_frame(exposure, format_type="YUYV"):
    """Capture a single frame (YUYV or MJPEG) at the specified exposure."""
    # Set capture properties
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    if not cap.isOpened():
        logging.error(f"Failed to open webcam")
        return 0

    if format_type == "YUYV":
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'))
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)  # Keep raw YUYV
    elif format_type == "MJPG":
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 1)  
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 8)
    cap.set(cv2.CAP_PROP_EXPOSURE, exposure)  # Raw exposure value

    ret, frame = cap.read()
    ret, frame = cap.read()
    ret, frame = cap.read()
    
    start = time.time()
    ret, frame = cap.read()
    elapsed = time.time() - start
    
    if not ret:
        logging.error(f"Failed to capture {format_type} frame at exposure {exposure}")
        cap.release()
        return None, None
    
    # Save frame
    filename = f"exp_{exposure}_{format_type}.jpg"
    if format_type == "YUYV":
        # Convert YUYV to BGR for saving
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_YUYV)
        cv2.imwrite(filename, frame_bgr)
    else:
        # MJPEG frames are already compatible
        cv2.imwrite(filename, frame)
    
    logging.info(f"Captured {format_type} frame at exposure {exposure}, Time: {elapsed:.2f}s")

    cap.release()
    
    return frame, elapsed

def analyze_images(exposures, formats=["YUYV", "MJPG"]):
    """Analyze median pixel intensity in the Y channel of captured images."""
    results = {fmt: [] for fmt in formats}
    
    for fmt in formats:
        for exp in exposures:
            # Load saved image (BGR)
            img = cv2.imread(f"exp_{exp}_{fmt}.jpg")
            if img is None:
                logging.error(f"Failed to load {fmt} image for exposure {exp}")
                continue
            
            # Convert to YUV and extract Y channel
            img_yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV)
            img_y = img_yuv[:, :, 0]  # Y channel (luminance)
            
            # Compute median intensity
            median_intensity = np.median(img_y)
            results[fmt].append(median_intensity)
            logging.info(f"{fmt} Exposure {exp}: Median intensity {median_intensity:.2f}")
    
    # Compute intensity ratios relative to first exposure for each format
    for fmt in formats:
        intensities = results[fmt]
        if intensities:
            base_intensity = intensities[0]
            base_exposure = exposures[0]
            print(f"\n{fmt} Intensity Ratios:")
            for exp, intensity in zip(exposures, intensities):
                measured_ratio = intensity / base_intensity if base_intensity != 0 else 0
                expected_ratio = exp / base_exposure
                print(f"Exposure {exp} vs {base_exposure}: "
                      f"Measured ratio {measured_ratio:.2f}, "
                      f"Expected ratio {expected_ratio:.2f}")
    
    # Compare YUYV vs MJPG intensities
    if results["YUYV"] and results["MJPG"]:
        print("\nYUYV vs MJPG Intensity Comparison:")
        for exp, yuyv_int, mjpg_int in zip(exposures, results["YUYV"], results["MJPG"]):
            ratio = yuyv_int / mjpg_int if mjpg_int != 0 else 0
            print(f"Exposure {exp}: YUYV/MJPG median intensity ratio {ratio:.2f}")
    
    return results

def main():
    # Exposure settings (raw values corresponding to 100ms, 200ms, etc.)
    exposures = [500, 1000, 1500, 2000, 2500]  # Example raw exposure values

    # Capture frames for both YUYV and MJPG
    capture_times = {"YUYV": [], "MJPG": []}
    for fmt in ["YUYV", "MJPG"]:
        for exp in exposures:
            frame, elapsed = capture_frame(exp, fmt)
            if frame is not None:
                capture_times[fmt].append(elapsed)
            else:
                capture_times[fmt].append(None)

    
    # Analyze images
    results = analyze_images(exposures)
    
    # Summarize capture times
    for fmt in ["YUYV", "MJPG"]:
        print(f"\n{fmt} Capture Times:")
        for exp, time in zip(exposures, capture_times[fmt]):
            if time is not None:
                print(f"Exposure {exp}: Capture time {time:.2f}s")
            else:
                print(f"Exposure {exp}: Capture failed")

if __name__ == "__main__":
    main()