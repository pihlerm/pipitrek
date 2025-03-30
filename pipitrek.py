from flask import Flask, request, redirect, url_for, render_template, Response, jsonify, send_file
from autoguider import Autoguider
from camera import Camera
from comm.telescopeserver import TelescopeServer
from threading import Thread, Event
import time
import numpy as np
from telescope import *
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
import re
import json
import base64

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
global autoguider, autoguider_sett, autoguider_thread
current_process = None
autoguider = None
autoguider_sett  = None
autoguider_thread = None
all_settings = None
telescope = None
camera = None
telescopeserver = None

video_interval = 0.5 # interval for generating video frames

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
    last_yield = time.time()
    try:
        while camera.running:
            start = time.time()
            if start - last_yield > 10:
                print("Timeout from gen_frames", flush=True)
                break            
            frame = camera.frame
            if frame is not last_valid_frame and frame is not None and frame.size > 0:
                #draw_info(frame)
                last_yield = start
                last_valid_frame = frame
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    frame_data = buffer.tobytes()
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
                else:
                    print("Frame encoding failed")
            #else:
                #print("No frame")
            time.sleep(max(video_interval - (time.time()-start),0.01))
    except GeneratorExit:
        print("GeneratorExit from video feed", flush=True)
    except Exception as e:
        print(f"Video feed error: {e}", flush=True)
    finally:
        print("Client disconnected from gen_frames", flush=True)


def gen_thresh_frames():
    if  autoguider_thread is None:
        return
    last_valid_thresh = None
    last_yield = time.time()
    try:
        while autoguider.running:
            start = time.time()
            if start - last_yield > 10:
                print("Timeout from gen_thresh_frames", flush=True)
                break            
            thresh = autoguider.threshold
            if thresh is not last_valid_thresh and thresh is not None :
                last_yield = start
                last_valid_thresh = thresh
                thresh_color = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
                #draw_info(thresh_color)
                ret, buffer = cv2.imencode('.jpg', thresh_color, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    thresh_data = buffer.tobytes()
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + thresh_data + b'\r\n')
                else:
                    print("Threshold encoding failed")
            #else:
                #print("No thresh")
            time.sleep(max(video_interval - (time.time()-start),0.01))
    except GeneratorExit:
        print("GeneratorExit from gen_thresh_frames", flush=True)
        # Cleanup (e.g., stop camera)
    except Exception as e:
        print(f"Video feed error: {e}", flush=True)
    finally:
        print("Client disconnected from gen_thresh_frames", flush=True)

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
    if camera.running:
        return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        return Response(b'', status=503)

@app.route('/thresh_feed')
def thresh_feed():
    if autoguider_thread is not None:
        return Response(gen_thresh_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        return Response(b'', status=503)


@app.route('/save_frame', methods=['POST'])
def save_frame():
    if camera.running:
        frame = camera.frame
        if frame is not None and frame.size > 0:
            # Save the frame as an image file
            save_path = os.path.join(os.getcwd(), 'saved_frame.png')
            cv2.imwrite(save_path, frame, [cv2.IMWRITE_PNG_COMPRESSION, 4])  # Save as PNG with mid compression
            print(f"Frame saved to {save_path}")
            return send_file(save_path, as_attachment=True, mimetype='image/png')
        else:
            return jsonify({"status": "error", "message": "No valid frame available"}), 400
    else:
        return jsonify({"status": "error", "message": "Camera is not running"}), 503


def form_properties():
    properties = {
        "tracked_centroid": (
            autoguider.tracked_centroid[0] / camera.width,
            autoguider.tracked_centroid[1] / camera.height
        ) if autoguider.tracked_centroid else None,
        "current_centroid": (
            autoguider.current_centroid[0] / camera.width,
            autoguider.current_centroid[1] / camera.height
        ) if autoguider.current_centroid else None,
        "max_drift": autoguider.max_drift,
        "star_size": autoguider.star_size,
        "gray_threshold": autoguider.gray_threshold,
        "rotation_angle": autoguider.rotation_angle,
        "pixel_scale": autoguider.pixel_scale,
        "guiding": autoguider.guiding,
        "dec_guiding": autoguider.dec_guiding,
        "guide_interval": autoguider.guide_interval,
        "guide_pulse": autoguider.guide_pulse,
        "last_correction": autoguider.last_correction,
        "star_locked": autoguider.star_locked,
        "focus_metric": autoguider.focus_metric,
        "last_loop_time": autoguider.last_loop_time,
        "last_frame_time": autoguider.last_frame_time,
        "last_status": autoguider.last_status,
        "exposure": camera.get_exposure(),
        "exposure_ms": camera.get_exposure()/10,
        "integrate_frames": camera.integrate_frames,
        "r_channel": camera.r_channel,
        "g_channel": camera.g_channel,
        "b_channel": camera.b_channel,
        "camera_fps": camera.actual_fps,
        "resolution": { "width":camera.width, "height":camera.height },
        "video_mode": camera.cam_mode,
        "pid_p": autoguider.ra_pid.Kp,
        "pid_i": autoguider.ra_pid.Ki,
        "pid_d": autoguider.ra_pid.Kd
    }
    # Encode the centroid_image as Base64
    if autoguider.centroid_image is not None:
        _, buffer = cv2.imencode('.png', autoguider.centroid_image)  # Encode as PNG
        properties["centroid_image"] = base64.b64encode(buffer).decode('utf-8')  # Convert to Base64 string
    else:
        properties["centroid_image"] = None
    return properties

@app.route('/properties', methods=['GET'])
def get_autoguider_properties():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    return jsonify(form_properties())

@sock.route('/autoguider_socket')
def autoguider_socket(ws):
    while True:
        try:
            if autoguider.data_ready:
                autoguider.data_ready = False
                ws.send(json.dumps(form_properties()))
            time.sleep(0.1)
        except Exception as e:  # Catches WebSocketConnectionClosedException
            break
    print("autoguider_socket disconnected")

@app.route('/scope_info', methods=['GET'])
def scope_info():
    return jsonify(telescope.scope_info)

@sock.route('/telescope_socket')
def telescope_socket(ws):
    while True:
        try:
            if telescopeserver.slew_request is not None:
                ra, dec = telescopeserver.slew_request
                telescopeserver.slew_request = None
                properties = {
                    "function": "slew_request",
                    "ra": ra,
                    "dec": dec
                }
                ws.send(json.dumps(properties))
            time.sleep(0.1)
        except Exception as e:  # Catches WebSocketConnectionClosedException
            break
    print("telescope_socket disconnected")

@app.route('/set_pid', methods=['POST'])
def set_pid():
    data = request.json
    autoguider.ra_pid.Kp = float(data.get('pid_p', 0.5))
    autoguider.dec_pid.Kp = float(data.get('pid_p', 0.5))

    autoguider.ra_pid.Ki = float(data.get('pid_i', 0.1))
    autoguider.dec_pid.Ki = float(data.get('pid_i', 0.1))
    
    autoguider.ra_pid.Kd = float(data.get('pid_d', 0.2))
    autoguider.dec_pid.Kd = float(data.get('pid_d', 0.2))
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

@app.route('/get_camera_properties', methods=['GET'])
def get_camera_properties():
    return jsonify(camera.controls)


@app.route('/set_direct_camera_property', methods=['POST'])
def set_direct_camera_property():
    name = request.json.get('name')
    value = request.json.get('value')    
    if camera.set_direct_control(name, value):
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "error", 'message': 'Failed setting '+name+' to '+value}), 200

@app.route('/set_camera_properties', methods=['POST'])
def set_camera_properties():
    width = request.json.get('width')
    height = request.json.get('height')
    if height is not None and width is not None:
        camera.set_frame_size(int(width), int(height))

    video_mode = request.json.get('video_mode')
    if video_mode is not None:
        camera.set_mode(video_mode)

    camera_fps = request.json.get('camera_fps')
    if camera_fps is not None:
        camera.setfps(float(camera_fps))

    r_channel = request.json.get('r_channel')
    if r_channel is not None:
        camera.r_channel = float(r_channel)

    g_channel = request.json.get('g_channel')
    if g_channel is not None:
        camera.g_channel = float(g_channel)

    b_channel = request.json.get('b_channel')
    if b_channel is not None:
        camera.b_channel = float(b_channel)

    integrate_frames = request.json.get('integrate_frames')
    if integrate_frames is not None:
        camera.integrate_frames = int(integrate_frames)

    return jsonify({"status": "success"}), 200


@app.route('/set_guide_interval', methods=['POST'])
def set_guide_interval():
    guide_interval = request.form.get('guide_interval', type=float, default=1)
    autoguider.guide_interval = guide_interval
    return jsonify({"status": "success"}), 200

@app.route('/set_guide_pulse', methods=['POST'])
def set_guide_pulse():
    guide_pulse = request.form.get('guide_pulse', type=float, default=1)
    autoguider.guide_pulse = guide_pulse
    return jsonify({"status": "success"}), 200


@app.route('/set_guiding', methods=['POST'])
def set_guiding():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        guiding = request.form.get('guiding', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
        autoguider.enable_guiding(guiding)
        return jsonify({"status": "success"}), 200

@app.route('/set_dec_guiding', methods=['POST'])
def set_dec_guiding():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        dec_guiding = request.form.get('dec_guiding', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
        autoguider.enable_dec_guiding(dec_guiding)
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

@app.route('/set_backlash', methods=['POST'])
def set_backlash():
    data = request.json
    ra = data.get('ra')
    dec = data.get('dec')
    telescope.send_backlash_comp_ra(int(ra))
    telescope.send_backlash_comp_dec(int(dec))
    return jsonify({'status': 'success', 'message': f'Backlash set'})


@app.route('/command_camera', methods=['POST'])
def command_camera():
    data = request.json
    action = data.get('action')
    if action=='START':
       PTCCameraStart(True).execute(telescope)
       print(f"camera START")
       return jsonify({'status': 'success', 'message': f'Camera START'})
    elif  action=='STOP':
       PTCCameraStart(False).execute(telescope)
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
            autoguider.acquire_star(centroid=(x*camera.width, y*camera.height))
            print(f"Acquisition triggered at ({x*camera.width}, {y*camera.height})")
            return jsonify({'status': 'success', 'message': f"Acquisition triggered at ({x}, {y})"})
        else:
            print("Failed to parse x or y from request")
            return jsonify({'status': 'error', 'message': "Failed to parse x or y from request"}), 400

@app.route('/calibrate', methods=['POST'])
def calibrate():
    if  autoguider_thread is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not active'}), 200
    else:
        with_backlash = request.form.get('with_backlash', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
        if autoguider.calibrate_angle(with_backlash):
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
        dec=0
        ra=0
        if direction == 'n':
            dec = 10
        elif direction == 's':
            dec = -10
        elif direction == 'e':
            ra = 10
        elif direction == 'w':
            ra = -10
        #telescope.send_start_movement_speed(ra,dec)
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
    print(f"GOTO command received: RA={ra}, DEC={dec}")
    telescope.send_go_to(ra,dec)
    return jsonify({'status': 'success', 'message': f'GOTO to RA={ra}, DEC={dec}'})

@app.route('/command_set_to', methods=['POST'])
def command_set_to():
    data = request.json
    ra = data.get('ra')
    dec = data.get('dec')
    print(f"SET TO command received: RA={ra}, DEC={dec}")
    telescope.send_set_to(ra,dec)
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


def cleanup():
    # Perform cleanup
    try:
        
        print("Stopping TCP telescope server..")
        telescopeserver.stop()
    
        print("Stopping autoguider..")
        all_settings.update_autoguider_settings(autoguider)
        autoguider.running = False
        autoguider_thread.join(timeout=10)
        if autoguider_thread.is_alive():
            print("Warning: Autoguider thread did not stop in time")
        else:
            print("Autoguider thread stopped")
        print("autoguider stopped.")
        # Stop telescope

        print("Saving telescope state and cosing connection..")
        telescope.get_PEC_position()
        telescope.send_tracking(False)    #disable tracking to not spoil PEC position
        all_settings.update_telescope_settings(telescope)
        telescope.stop_bridge()
        telescope.close_connection()
        print("telescope closed.")

        print("Stopping autoguider camera..")
        camera.stop_capture()
        camera.release_camera()
        all_settings.update_camera_settings(camera)
        print("camera stopped.")

        cv2.destroyAllWindows()
        all_settings.save_settings()
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
    
    print("PipiTrek commander starting up...")
    all_settings = Settings()
    all_settings.load_settings()

    #telescope startup
    print("Connecting to telescope..")
    telescope = Telescope()

    all_settings.set_telescope_settings(telescope)
    time.sleep(2) # wait arduino
    # update PEC position that was loaded from settings since arduino was restarted
    telescope.send_PEC_position(telescope.current_pecpos())
    telescope.send_pier(telescope.scope_info["pier"])
    telescope.send_tracking(telescope.scope_info["tracking"]=="enabled")    #now enable tracking
    telescope.start_bridge()
    print("telescope started.")

    print("Setting up autoguider camera..")
    camera = Camera()
    camera.init_camera()
    all_settings.set_camera_settings(camera)
    camera.start_capture()
    print("camera set up.")

    print("Setting up autoguider..")
    autoguider = Autoguider()
    all_settings.set_autoguider_settings(autoguider)
    autoguider_thread = Thread(target=autoguider.run_autoguider)
    autoguider_thread.start()
    print("autoguider set up.")

    # TCP telescope server
    telescopeserver = TelescopeServer()
    telescopeserver.start()
    

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