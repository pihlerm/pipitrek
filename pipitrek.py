from flask import Flask, request, redirect, url_for, render_template, Response, jsonify
from autoguider import Autoguider
from threading import Thread, Event
import time
import numpy as np
from telescope import Telescope
import logging
import cv2
import os
from settings import AutoguiderSettings
from werkzeug.serving import make_server
import sys
import subprocess
from flask_socketio import SocketIO, emit
import eventlet

eventlet.monkey_patch()

# Disable Flask request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)  # Suppress INFO messages (e.g., requests)
# Alternatively, disable completely:
# log.disabled = True
# Global shutdown event
shutdown_event = Event()

app = Flask(__name__)

telescope = Telescope()
telescope_thread = Thread(target=telescope.run_serial_bridge)
telescope_thread.start()
#telescope.get_info()

autoguider = None
autoguider_sett  = None
autoguider_thread = None

# Initialize Flask-SocketIO
socketio = SocketIO(app)


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
def control():
    return render_template('control.html')

@app.route('/autoguider')
def index():
    if autoguider_thread is not None:
        return render_template('autoguider.html', correction=autoguider.last_correction, threshold=autoguider.gray_threshold,
                           max_drift=autoguider.max_drift, star_size=autoguider.star_size,
                           rotation_angle=autoguider.rotation_angle, pixel_scale=autoguider.pixel_scale, 
                           exposure=autoguider.exposure, gain=autoguider.gain, integrate_frames=autoguider.integrate_frames, 
                           guiding=autoguider.guiding)
    else:
        return Response(b'', status=503)

@app.route('/video_feed')
def video_feed():
    if autoguider_thread is not None:
        return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        return Response(b'', status=503)

@app.route('/thresh_feed')
def thresh_feed():
    if autoguider_thread is not None:
        return Response(gen_thresh_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        return Response(b'', status=503)

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
        "gain": autoguider.gain,
        "integrate_frames": autoguider.integrate_frames,
        "r_channel": autoguider.r_channel,
        "g_channel": autoguider.g_channel,
        "b_channel": autoguider.b_channel,
        "tracked_centroid": autoguider.tracked_centroid,
        "current_centroid": autoguider.current_centroid,
        "guiding": autoguider.guiding,
        "scope_info": telescope.scope_info
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

@app.route('/set_gain', methods=['POST'])
def set_gain():
    gain = request.form.get('gain', type=float, default=0.5)  # Default to 0.5 (mid-range)
    if 0.0 <= gain <= 1.0:
        autoguider.set_gain(gain)
    return '', 204

@app.route('/set_integrate_frames', methods=['POST'])
def set_integrate_frames():
    integrate_frames = request.form.get('integrate_frames', type=int, default=10)  # Default to 10 (mid-range)
    if 1 <= integrate_frames <= 20:
        autoguider.integrate_frames = integrate_frames
    return '', 204

@app.route('/set_guiding', methods=['POST'])
def set_guiding():
    guiding = request.form.get('guiding', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    autoguider.guiding = guiding
    return '', 204

@app.route('/set_tracking', methods=['POST'])
def set_tracking():
    tracking = request.form.get('tracking', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    telescope.send_tracking(tracking)
    return '', 204

@app.route('/set_pier', methods=['POST'])
def set_pier():
    pier = request.form.get('pier')
    if not telescope.send_pier(pier):
        return jsonify({'status': 'error', 'message': 'Invalid pier value'}), 400
    else:
        return jsonify({'status': 'success', 'message': f'Pier set to {pier}'})

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

@app.route('/calibrate', methods=['POST'])
def calibrate():
    if autoguider.calibrate_angle():
        print(f"Calibration successful")
    else:
        print("Failed to calibrate")
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

@app.route('/command_receivePEC', methods=['GET'])
def command_receivePEC():
    pec_table = telescope.receive_pec_table()
    if pec_table:
        return jsonify({"status": "success", "pec_table": pec_table})
    else:
        return jsonify({"status": "error", "message": "Failed to receive PEC table"})

@app.route('/command_sendPEC', methods=['POST'])
def command_sendPEC():
    data = request.json
    pec_table = data.get('pec_table', [])
    if pec_table and isinstance(pec_table, list):
        ret = telescope.send_pec_table(pec_table)
        return jsonify({"status": "success", "message": ret})
    else:
        return jsonify({"status": "error", "message": "Invalid PEC table data"})

@app.route('/command_upload', methods=['POST'])
def control_upload():
    if 'firmware' not in request.files:
        return 'No file part', 400
    file = request.files['firmware']
    if file.filename == '':
        return 'No selected file', 400
    if file and file.filename.endswith('.hex'):
        filename = os.path.join('/root/astro/arduino/', file.filename)
        file.save(filename)
        if telescope.upload_firmware(filename):
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "Error uploading file."})
    return 'Invalid file type', 400

@app.route('/control_correction', methods=['POST'])
def control_correction():
    direction = request.form.get('direction')
    if direction not in ['n', 's', 'e', 'w']:
        return jsonify({'status': 'error', 'message': 'Invalid direction'}), 400

    telescope = Telescope()
    try:
        telescope.send_correction(direction)
        return jsonify({'status': 'success', 'message': f'Moved {direction}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/command_reset', methods=['POST'])
def command_reset():
    telescope = Telescope()
    try:
        telescope.reset_arduino()
        return jsonify({'status': 'success', 'message': 'Arduino reset successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/command_info', methods=['GET'])
def command_info():
    telescope = Telescope()
    try:
        info = telescope.get_info()
        return jsonify({'status': 'success', 'info': info})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    

# Shutdown route
@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Gracefully shut down the Flask app and perform cleanup."""
    if request.method != 'POST':
        return jsonify({"error": "Method not allowed"}), 405

    print("Shutdown requested via /shutdown")
    shutdown_event.set()  # Signal threads to stop

    cleanup()
    # Attempt Werkzeug shutdown
    func = request.environ.get('werkzeug.server.shutdown')
    if func is not None:
        func()
        print("Werkzeug server shutdown initiated")
        return jsonify({"message": "Server shutting down"}), 200
    else:
        print("Not running with Werkzeug server, forcing shutdown")
        # Fallback: Force exit after cleanup
        Thread(target=lambda: [time.sleep(1), os._exit(0)]).start()
        return jsonify({"message": "Shutdown initiated, forcing exit"}), 200

@app.route('/command_autoguider', methods=['POST'])
def command_autoguider():
    data = request.json
    onoff = data.get('start')

    if onoff == True:
        return start_autoguider()
    else:
        stop_autoguider()
        return jsonify({'status': 'OK', 'message': 'Stopped'}), 200


@socketio.on('execute_command')
def handle_execute_command(data):
    command = data.get('command')
    if not command:
        emit('command_output', {'output': 'Error: Command cannot be empty.\n'})
        return

    def stream_command_output():
        try:
            # Run the command and stream output
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for line in process.stdout:
                emit('command_output', {'output': line}, namespace='/')
            for line in process.stderr:
                emit('command_output', {'output': line}, namespace='/')
            process.wait()
            emit('command_output', {'output': f"Command finished with exit code {process.returncode}\n"})
        except Exception as e:
            emit('command_output', {'output': f"Error: {str(e)}\n"})

    # Run the command in a separate thread to avoid blocking
    Thread(target=stream_command_output).start()


def start_autoguider():
    global autoguider, autoguider_sett, autoguider_thread
    try:
        autoguider = Autoguider()
        autoguider_sett  = AutoguiderSettings()
        s = autoguider_sett.load_settings()
        if s:
            autoguider_sett.set_settings(autoguider, s)
        autoguider_thread = Thread(target=autoguider.run_autoguider)
        autoguider_thread.start()
        return jsonify({'status': 'success', 'message': 'Autoguider started successfully'}), 200
    except RuntimeError as e:
        autoguider_thread = None
        print(f"Error starting autoguider: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 200
    except Exception as e:
        autoguider_thread = None
        print(f"Unexpected error: {e}")
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), 200



def stop_autoguider():
    # Stop autoguider
    global autoguider, autoguider_sett, autoguider_thread
    if autoguider_thread is None:
        return

    # Save settings
    autoguider_sett.save_settings(autoguider_sett.get_settings(autoguider))
    print("Settings saved")

    autoguider.running = False
    if not autoguider_thread is None:
        autoguider_thread.join(timeout=10)
        if autoguider_thread.is_alive():
            print("Warning: Autoguider thread did not stop in time")
        else:
            print("Autoguider thread stopped")
    # Release resources
    autoguider.release_camera()
    autoguider_sett  = None
    autoguider_thread = None
    return jsonify({'status': 'success', 'message': 'Autoguider stopped successfully'}), 200


def cleanup():
    # Perform cleanup
    try:
        stop_autoguider()
        # Stop telescope
        telescope.running = False
        telescope_thread.join(timeout=10)
        if telescope_thread.is_alive():
            print("Warning: Telescope thread did not stop in time")
        else:
            print("Telescope thread stopped")

        telescope.close_connection()
        cv2.destroyAllWindows()
        print("Resources released")

    except Exception as e:
        print(f"Error during cleanup: {e}")


class ServerThread(Thread):
    def __init__(self, app):
        Thread.__init__(self)
        self.server = make_server('0.0.0.0', 80, app, threaded=True)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        print("Starting Flask server on 0.0.0.0:80")
        self.server.serve_forever()

    def shutdown(self):
        print("Shutting down Flask server")
        self.server.shutdown()


if __name__ == '__main__':
    
    socketio.run(app, host='0.0.0.0', port=80, debug=True)
    server = ServerThread(app)
    server.start()

    try:
        while server.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("KeyboardInterrupt received")
        shutdown_event.set()

        cleanup()

        server.shutdown()
        server.join(timeout=10)

        print("Application shut down gracefully")
        sys.exit(0)