from flask import Flask, Response, render_template, jsonify, request
from autoguider_main import Autoguider
from threading import Thread, Lock
import time
import numpy as np
from telescope import Telescope
import logging
import cv2


# Disable Flask request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)  # Suppress INFO messages (e.g., requests)
# Alternatively, disable completely:
# log.disabled = True

app = Flask(__name__)
autoguider = Autoguider()  # Instantiate outside thread
autoguider_thread = Thread(target=autoguider.run_autoguider)
autoguider_thread.start()

telescope = Telescope()

def draw_info(frame):
    with autoguider.lock:
        fps_text = f"FPS: {autoguider.cap.get(cv2.CAP_PROP_FPS):.1f}"
        cv2.putText(frame, fps_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
        if autoguider.tracked_centroid is not None:
            x, y = autoguider.tracked_centroid
            cv2.circle(frame, (x, y), 5, (0, 255, 0), -1)  # Green for tracked
        if autoguider.current_centroid is not None:
            x, y = autoguider.current_centroid
            cv2.circle(frame, (x, y), 5, (0, 0, 255), -1)  # Red for current
        text = (f"RA: {autoguider.last_correction['ra']}, DEC: {autoguider.last_correction['dec']}\n"
                f"RA(arcsec): {autoguider.last_correction['ra_arcsec']:.1f}, DEC(arcsec): {autoguider.last_correction['dec_arcsec']:.1f}\n"
                f"DX: {autoguider.last_correction['dx']}, DY: {autoguider.last_correction['dy']}")
        cv2.putText(frame, text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

def gen_frames():
    last_valid_frame = None
    while autoguider.running:
        with autoguider.lock:
            frame = autoguider.frame.copy() if autoguider.frame is not None else last_valid_frame

        if frame is not None and frame.size > 0:
            last_valid_frame = frame.copy()  # Store valid frame
            #draw_info(frame)
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                frame_data = buffer.tobytes()
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            else:
                print("Frame encoding failed")
        else:
            print("No frame")
        time.sleep(1)

def gen_thresh_frames():
    last_valid_thresh = None
    while autoguider.running:
        with autoguider.lock:
            thresh = autoguider.threshold
        if thresh is None or thresh.size == 0:
            thresh = last_valid_thresh

        if thresh is not None:
            thresh_color = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
            draw_info(thresh_color)
            ret, buffer = cv2.imencode('.jpg', thresh_color, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                thresh_data = buffer.tobytes()
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + thresh_data + b'\r\n')
            else:
                print("Threshold encoding failed")
        else:
            print("No thresh")
        time.sleep(1)

@app.route('/')
def index():
    return render_template('index.html', correction=autoguider.last_correction, threshold=autoguider.gray_threshold,
                           max_drift=autoguider.max_drift, star_size=autoguider.star_size,
                           rotation_angle=autoguider.rotation_angle, pixel_scale=autoguider.pixel_scale, exposure=autoguider.exposure)

@app.route('/control')
def control():
    return render_template('control.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/thresh_feed')
def thresh_feed():
    return Response(gen_thresh_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/properties', methods=['GET'])
def get_autoguider_properties():
    properties = {
        "tracked_centroid": autoguider.tracked_centroid,
        "current_centroid": autoguider.current_centroid,
        "max_drift": autoguider.max_drift,
        "star_size": autoguider.star_size,
        "gray_threshold": autoguider.gray_threshold,
        "rotation_angle": autoguider.rotation_angle,
        "pixel_scale": autoguider.pixel_scale,
        "last_correction": autoguider.last_correction,
        "exposure": autoguider.exposure,
        "r_channel": autoguider.r_channel,
        "g_channel": autoguider.g_channel,
        "b_channel": autoguider.b_channel,
        "tracked_centroid": autoguider.tracked_centroid,
        "current_centroid": autoguider.current_centroid
    }
    return jsonify(properties)

@app.route('/set_channels', methods=['POST'])
def set_autoguider_settings():
    data = request.json
    autoguider.r_channel = float(data.get('r_channel', autoguider.r_channel))
    autoguider.g_channel = float(data.get('g_channel', autoguider.g_channel))
    autoguider.b_channel = float(data.get('b_channel', autoguider.b_channel))
    return jsonify({"status": "success"})

@app.route('/set_threshold', methods=['POST'])
def set_threshold():
    new_threshold = request.form.get('threshold', type=int, default=autoguider.gray_threshold)
    if 0 <= new_threshold <= 255:
        autoguider.gray_threshold = new_threshold
    return '', 204

@app.route('/set_max_drift', methods=['POST'])
def set_max_drift():
    new_max_drift = request.form.get('max_drift', type=int, default=autoguider.max_drift)
    if 0 <= new_max_drift <= 50:
        autoguider.max_drift = new_max_drift
    return '', 204

@app.route('/set_star_size', methods=['POST'])
def set_star_size():
    new_star_size = request.form.get('star_size', type=int, default=autoguider.star_size)
    if 1 <= new_star_size <= 100:
        autoguider.star_size = new_star_size
    return '', 204

@app.route('/set_rotation_angle', methods=['POST'])
def set_rotation_angle():
    new_angle = request.form.get('rotation_angle', type=float, default=autoguider.rotation_angle)
    if -180 <= new_angle <= 180:
        autoguider.rotation_angle = new_angle
    return '', 204

@app.route('/set_pixel_scale', methods=['POST'])
def set_pixel_scale():
    new_scale = request.form.get('pixel_scale', type=float, default=autoguider.pixel_scale)
    if 0.1 <= new_scale <= 10.0:
        autoguider.pixel_scale = new_scale
    return '', 204

@app.route('/set_exposure', methods=['POST'])
def set_exposure():
    exp = request.form.get('exposure', type=float, default=0.5)  # Default to 0.5 (mid-range)
    if 0.0 <= exp <= 1.0:
        autoguider.set_exposure(exp)
    return '', 204

@app.route('/acquire', methods=['POST'])
def acquire():
    # Debug: Print the raw request body
    print(f"Request body: {request.get_data().decode('utf-8')}")
    x = request.form.get('x', type=float)
    y = request.form.get('y', type=float)
    print(f"Parsed x: {x}, y: {y}")  # Debug parsed values
    if x is not None and y is not None:
        autoguider.acquire_star((x, y))
        print(f"Acquisition triggered at ({x}, {y})")
    else:
        print("Failed to parse x or y from request")
    return '', 204

@app.route('/control_move', methods=['POST'])
def control_move():
    direction = request.form.get('direction')
    if direction in ['n', 's', 'e', 'w']:
        # Handle the direction command here
        print(f"Received direction: {direction}")
        # You can add code here to send the direction command to the telescope
        telescope.send_move(direction)
        return jsonify({"status": "success", "direction": direction})
    else:
        return jsonify({"status": "error", "message": "Invalid direction"}), 400

@app.route('/control_stop', methods=['POST'])
def control_stop():
    direction = request.form.get('direction', default='')
    print(f"Received stop command with direction: {direction}")
    if direction in ['n', 's', 'e', 'w','']:
        # Handle the direction command here
        print(f"Received direction: {direction}")
        telescope.send_stop(direction)
        return jsonify({"status": "success", "direction": direction})
    else:
        return jsonify({"status": "error", "message": "Invalid direction"}), 400



if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True)
    except KeyboardInterrupt:
        autoguider.running = False
        autoguider_thread.join(timeout=10)
        telescope.close_connection()

        del autoguider
        del telescope
        cv2.destroyAllWindows()
        print("Thread and camera released")