from flask import Flask, request, redirect, url_for, render_template, Response, jsonify
from autoguider import Autoguider
from threading import Thread, Event
import time
import numpy as np
from telescope import Telescope
import logging
import cv2
import os
import signal
from settings import Settings
from werkzeug.serving import make_server
import sys
import subprocess
import select
from flask_sock import Sock
import pty
import re

# Disable Flask request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)  # Suppress INFO messages (e.g., requests)
# Alternatively, disable completely:
# log.disabled = True
# Global shutdown event
shutdown_event = Event()

app = Flask(__name__)
sock = Sock(app)

# Global variable to track the current process for terminal
current_process = None

all_settings = Settings()
all_settings.load_settings()

#telescope startup
telescope = Telescope()

all_settings.set_telescope_settings(telescope)
time.sleep(2) # wait arduino
# update PEC position that was loaded from settings since arduino was restarted
telescope.send_PEC_position(telescope.current_pecpos())
telescope.send_pier(telescope.scope_info["pier"])
telescope.send_tracking(True)    #now enable tracking
telescope_thread = Thread(target=telescope.run_serial_bridge)
telescope_thread.start()

autoguider = None
autoguider_sett  = None
autoguider_thread = None


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
    if  autoguider_thread is None:
        return
    last_valid_frame = None
    try:
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
    except GeneratorExit:
        print("Client disconnected from video feed", flush=True)
        # Cleanup (e.g., stop camera)
    except Exception as e:
        print(f"Video feed error: {e}", flush=True)


def gen_thresh_frames():
    if  autoguider_thread is None:
        return
    last_valid_thresh = None
    try:
        while autoguider.running:
            with autoguider.lock:
                thresh = autoguider.threshold
            if thresh is None or thresh.size == 0:
                thresh = last_valid_thresh

            if thresh is not None:
                thresh_color = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
                #draw_info(thresh_color)
                ret, buffer = cv2.imencode('.jpg', thresh_color, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    thresh_data = buffer.tobytes()
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + thresh_data + b'\r\n')
                else:
                    print("Threshold encoding failed")
            else:
                print("No thresh")
            time.sleep(1)
    except GeneratorExit:
        print("Client disconnected from video feed", flush=True)
        # Cleanup (e.g., stop camera)
    except Exception as e:
        print(f"Video feed error: {e}", flush=True)

def gen_detail_frames():
    if  autoguider_thread is None:
        return
    try:
        while autoguider.running:
            with autoguider.lock:
                detail = autoguider.centroid_image
            if detail is None or detail.size == 0:
                continue

            detail_color = cv2.cvtColor(detail, cv2.COLOR_GRAY2BGR)
            ret, buffer = cv2.imencode('.jpg', detail_color, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                detail_data = buffer.tobytes()
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + detail_data + b'\r\n')
            else:
                print("Threshold encoding failed")
            time.sleep(1)
    except GeneratorExit:
        print("Client disconnected from video feed", flush=True)
        # Cleanup (e.g., stop camera)
    except Exception as e:
        print(f"Video feed error: {e}", flush=True)



@app.route('/control')
def control():
    return render_template('control.html')

@app.route('/')
def index():
    return render_template('autoguider.html')
    
@app.route('/terminal')
def terminal():
    return render_template('terminal.html')
    
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

@app.route('/detail_feed')
def detail_feed():
    if autoguider_thread is not None:
        return Response(gen_detail_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        return Response(b'', status=503)


@app.route('/properties', methods=['GET'])
def get_autoguider_properties():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        properties = {
            "tracked_centroid": autoguider.tracked_centroid,
            "current_centroid": autoguider.current_centroid,
            "max_drift": autoguider.max_drift,
            "star_size": autoguider.star_size,
            "gray_threshold": autoguider.gray_threshold,
            "rotation_angle": autoguider.rotation_angle,
            "pixel_scale": autoguider.pixel_scale,
            "exposure": autoguider.exposure,
            "gain": autoguider.gain,
            "integrate_frames": autoguider.integrate_frames,
            "r_channel": autoguider.r_channel,
            "g_channel": autoguider.g_channel,
            "b_channel": autoguider.b_channel,
            "guiding": autoguider.guiding,
            "correction_length" : autoguider.correction_length,
            "last_correction": autoguider.last_correction,
            "star_locked": autoguider.star_locked,
            "last_loop_time": autoguider.last_loop_time,
            "last_status" : autoguider.last_status
        }
    return jsonify(properties)

@app.route('/scope_info', methods=['GET'])
def scope_info():
    return jsonify(telescope.scope_info)

@app.route('/set_channels', methods=['POST'])
def set_autoguider_settings():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        data = request.json
        autoguider.r_channel = float(data.get('r_channel', autoguider.r_channel))
        autoguider.g_channel = float(data.get('g_channel', autoguider.g_channel))
        autoguider.b_channel = float(data.get('b_channel', autoguider.b_channel))
        return jsonify({"status": "success"}), 200

@app.route('/set_threshold', methods=['POST'])
def set_threshold():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        new_threshold = request.form.get('threshold', type=int, default=autoguider.gray_threshold)
        if 0 <= new_threshold <= 255:
            autoguider.gray_threshold = new_threshold
        return jsonify({"status": "success"}), 200

@app.route('/set_max_drift', methods=['POST'])
def set_max_drift():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        new_max_drift = request.form.get('max_drift', type=int, default=autoguider.max_drift)
        if 0 <= new_max_drift <= 50:
            autoguider.max_drift = new_max_drift
        return jsonify({"status": "success"}), 200

@app.route('/set_star_size', methods=['POST'])
def set_star_size():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        new_star_size = request.form.get('star_size', type=int, default=autoguider.star_size)
        if 1 <= new_star_size <= 100:
            autoguider.star_size = new_star_size
        return jsonify({"status": "success"}), 200

@app.route('/set_rotation_angle', methods=['POST'])
def set_rotation_angle():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        new_angle = request.form.get('rotation_angle', type=float, default=autoguider.rotation_angle)
        if -180 <= new_angle <= 180:
            autoguider.rotation_angle = new_angle
        return jsonify({"status": "success"}), 200

@app.route('/set_pixel_scale', methods=['POST'])
def set_pixel_scale():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        new_scale = request.form.get('pixel_scale', type=float, default=autoguider.pixel_scale)
        if 0.1 <= new_scale <= 10.0:
            autoguider.pixel_scale = new_scale
        return jsonify({"status": "success"}), 200

@app.route('/set_exposure', methods=['POST'])
def set_exposure():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        exp = request.form.get('exposure', type=float, default=0.5)  # Default to 0.5 (mid-range)
        if 0.0 <= exp <= 1.0:
            autoguider.set_exposure(exp)
        return jsonify({"status": "success"}), 200

@app.route('/set_gain', methods=['POST'])
def set_gain():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        gain = request.form.get('gain', type=float, default=0.5)  # Default to 0.5 (mid-range)
        if 0.0 <= gain <= 1.0:
            autoguider.set_gain(gain)
        return jsonify({"status": "success"}), 200

@app.route('/set_integrate_frames', methods=['POST'])
def set_integrate_frames():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        integrate_frames = request.form.get('integrate_frames', type=int, default=10)  # Default to 10 (mid-range)
        if 1 <= integrate_frames <= 20:
            autoguider.integrate_frames = integrate_frames
        return jsonify({"status": "success"}), 200

@app.route('/set_guiding', methods=['POST'])
def set_guiding():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        guiding = request.form.get('guiding', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
        autoguider.guiding = guiding
        return jsonify({"status": "success"}), 200

@app.route('/set_tracking', methods=['POST'])
def set_tracking():
    tracking = request.form.get('tracking', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    telescope.scope_info
    telescope.send_tracking(tracking)
    time.sleep(0.1)
    telescope.get_info()
    return jsonify({'status': 'success', 'message': f'Tracking set to {tracking}'})


@app.route('/set_quiet', methods=['POST'])
def set_quiet():
    quiet = request.form.get('quiet', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    telescope.set_quiet(quiet)
    return jsonify({'status': 'success', 'message': f'Quiet mode set to {quiet}'})

@app.route('/set_pier', methods=['POST'])
def set_pier():
    pier = request.form.get('pier')
    bok = telescope.send_pier(pier)
    time.sleep(0.1)
    telescope.get_info()
    if bok:
        return jsonify({'status': 'success', 'message': f'Pier set to {pier}'})
    else:
        return jsonify({'status': 'error', 'message': 'Invalid pier value'}), 400
    
@app.route('/set_camera', methods=['POST'])
def set_camera():
    data = request.json
    shots = data.get('shots')
    exposure = data.get('exposure')
    if telescope.send_camera(shots, exposure):
        return jsonify({'status': 'success', 'message': f'Camera set to shots {shots} and exposure {exposure}'})
    else:
        return jsonify({'status': 'error', 'message': 'Invalid numbers'}), 400

@app.route('/command_camera', methods=['POST'])
def command_camera():
    data = request.json
    action = data.get('action')
    if action=='START':
       telescope.start_camera()
       print(f"camera START")
       return jsonify({'status': 'success', 'message': f'Camera START'})
    elif  action=='STOP':
       telescope.stop_camera()
       print(f"camera STOP")
       return jsonify({'status': 'success', 'message': f'Camera STOP'})
    else:
        return jsonify({'status': 'error', 'message': f'Invalid camera action {action}'}), 400

@app.route('/acquire', methods=['POST'])
def acquire():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        print(f"Request body: {request.get_data().decode('utf-8')}")
        x = request.form.get('x', type=float)
        y = request.form.get('y', type=float)
        print(f"Parsed x: {x}, y: {y}")  # Debug parsed values
        if x is not None and y is not None:
            autoguider.acquire_star((x, y))
            print(f"Acquisition triggered at ({x}, {y})")
            return jsonify({'status': 'success', 'message': f"Acquisition triggered at ({x}, {y})"})
        else:
            print("Failed to parse x or y from request")
            return jsonify({'status': 'error', 'message': "Failed to parse x or y from request"}), 400

@app.route('/calibrate', methods=['POST'])
def calibrate():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        if autoguider.calibrate_angle():
            print(f"Calibration successful")
            return jsonify({'status': 'success', 'message': 'Calibration successful'})
        else:
            print("Failed to calibrate")
            return jsonify({'status': 'error', 'message': "Failed to calibrate"}), 400

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

@app.route('/control_speed', methods=['POST'])
def control_speed():
    speed = request.form.get('speed')
    if speed in ['G', 'C', 'M', 'S']:
        print(f"Received speed: {speed}")
        # You can add code here to send the direction command to the telescope
        telescope.send_speed(speed)
        return jsonify({"status": "success", "speed": speed})
    else:
        return jsonify({"status": "error", "message": "Invalid speed"}), 400

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
        return jsonify({"status": "error", "message": "Failed to receive PEC table"}), 500

@app.route('/command_sendPEC', methods=['POST'])
def command_sendPEC():
    data = request.json
    pec_table = data.get('pec_table', [])
    if pec_table and isinstance(pec_table, list):
        ret = telescope.send_pec_table(pec_table)
        return jsonify({"status": "success", "message": ret})
    else:
        return jsonify({"status": "error", "message": "Invalid PEC table data"}), 500

@app.route('/set_pec_position', methods=['POST'])
def set_pec_position():
    try:
        pec_position = request.form.get('pec_position', type=float)  # Get pec_position as a float
        if pec_position is None:
            raise ValueError("PEC position is missing or invalid")
        
        rounded_position = round(pec_position)  # Round the float to the nearest integer
        print(f"Pec position (rounded): {rounded_position}")
        telescope.send_PEC_position(int(rounded_position))  # Send the rounded position
        return jsonify({'status': 'success', 'message': f'PEC pos set to {rounded_position}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


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
            return jsonify({"status": "error", "message": "Error uploading file."}), 500
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
        print(f"Exception {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/command_goto', methods=['POST'])
def command_goto():
    data = request.json
    ra = data.get('ra')
    dec = data.get('dec')
    # Process the RA and DEC values
    print(f"GOTO command received: RA={ra}, DEC={dec}")
    return jsonify({'status': 'success', 'message': f'GOTO to RA={ra}, DEC={dec}'})

@app.route('/command_set_to', methods=['POST'])
def command_set_to():
    data = request.json
    ra = data.get('ra')
    dec = data.get('dec')
    # Process the RA and DEC values
    print(f"SET TO command received: RA={ra}, DEC={dec}")
    return jsonify({'status': 'success', 'message': f'SET TO RA={ra}, DEC={dec}'})


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

def strip_ansi(text):
    # Remove ANSI escape sequences
    return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\([A-Z0-9])', '', text)

@sock.route('/command_terminal')
def command_terminal(ws):
    global current_process
    while True:
        message = ws.receive()
        if message is None:
            break
        try:
            command = f"/bin/bash -c '. /boot/dietpi/func/dietpi-globals && {message}'"
            current_process = subprocess.Popen(
                command, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True,
                preexec_fn=os.setsid
            )
            
            def read_send(inp):
                line = inp.readline()                
                if line:
                   clean_line = strip_ansi(line.strip())
                   ws.send(clean_line)
                return not line

            while current_process.poll() is None:
                readable, _, _ = select.select([current_process.stdout, current_process.stderr, ws.sock], [], [], 0.1)
                for r in readable:
                    if r == current_process.stdout:
                        read_send(current_process.stdout)
                    elif r == current_process.stderr:
                        read_send(current_process.stderr)
                    elif r == ws.sock:
                        message = ws.receive()
                        if message == "abort":
                            os.killpg(current_process.pid, signal.SIGTERM)
                            try:
                                current_process.wait(timeout=1)
                            except subprocess.TimeoutExpired:
                                os.killpg(current_process.pid, signal.SIGKILL)
                            ws.send("info: Command aborted")
                            break

            # Drain remaining output after process ends
            while not read_send(current_process.stdout):
                pass
            while not read_send(current_process.stderr):
                pass
            
            ws.send(f"exit: {current_process.returncode}")
            current_process = None
        except Exception as e:
            ws.send(f"error: {str(e)}")
            current_process = None



@app.route('/command_autoguider', methods=['POST'])
def command_autoguider():
    data = request.json
    onoff = data.get('start')

    if onoff == True:
        return start_autoguider()
    else:
        stop_autoguider()
        return jsonify({'status': 'OK', 'message': 'Stopped'}), 200


def start_autoguider():
    global autoguider, autoguider_sett, autoguider_thread
    try:
        autoguider = Autoguider()
        all_settings.set_autoguider_settings(autoguider)
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
    all_settings.update_autoguider_settings(autoguider)
    all_settings.save_settings()
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
        telescope.get_PEC_position()
        telescope.send_tracking(False)    #disable tracking to not spoil PEC position
        all_settings.update_telescope_settings(telescope)
        all_settings.save_settings()
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