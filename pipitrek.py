from flask import Flask, request, redirect, url_for, render_template, Response, jsonify, send_file
from analyzer import Analyzer
from autoguider import Autoguider
from camera import Camera
from comm.telescopeserver import TelescopeServer
from platesolver import PlateSolver
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
import ssl
from v412_ctl import list_cameras

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
global_server = None

video_interval = 0.5 # interval for generating video frames
frame_timeout = 30 # seconds before timeout


# PAGES

@app.route('/control')
def control():
    return render_template('control.html')

@app.route('/')
def index():
    cameras = list_cameras()
    return render_template('autoguider.html', cameras=cameras)
    
@app.route('/terminal')
def terminal():
    return render_template('terminal.html')


@app.route('/scopevr')
def scopevr():
    return render_template('scopevr.html')

# SOCKETS

def draw_info(frame, nframe):
    fps_text = f"FPS: {camera.cap.get(cv2.CAP_PROP_FPS):.1f} frame no: {nframe}"
    cv2.putText(frame, fps_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

@sock.route('/video_feed_ws')
def video_feed_ws(ws):
    last_valid_frame = None
    last_yield = time.time()
    nframe = 0
    try:
        while camera is not None and camera.running:
            start = time.time()
            if start - last_yield > frame_timeout:
                print("Timeout from video_feed_ws", flush=True)
                break            
            frame = camera.frame
            if frame is not last_valid_frame and frame is not None and frame.size > 0:
                #draw_info(frame, nframe)
                #print(f"video frame {nframe} sent")
                nframe += 1
                last_yield = start
                last_valid_frame = frame
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    # Send the frame as a Base64-encoded string
                    frame_data = base64.b64encode(buffer).decode('utf-8')
                    ws.send(frame_data)
                else:
                    print("Frame encoding failed")
            time.sleep(max(video_interval - (time.time()-start),0.01))
    except ssl.SSLEOFError as e:
        print(f"SSL EOF error in video_feed_ws: {e}")
    except Exception as e:
        print(f"video_feed_ws video feed error: {e}")
    finally:
        print("Client disconnected from video_feed_ws", flush=True)

@sock.route('/thresh_feed_ws')
def thresh_feed_ws(ws):
    last_valid_thresh = None
    last_yield = time.time()
    nframe = 0
    try:
        while camera is not None and camera.running:
            start = time.time()
            if start - last_yield > frame_timeout:
                print("Timeout from thresh_feed_ws", flush=True)
                break            
            thresh = autoguider.threshold
            if thresh is not last_valid_thresh and thresh is not None :
                last_yield = start
                last_valid_thresh = thresh
                #thresh_color = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
                #draw_info(thresh_color, nframe)
                #print(f"thresh frame {nframe} sent")
                nframe += 1
                ret, buffer = cv2.imencode('.jpg', thresh, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    # Send the frame as a Base64-encoded string
                    frame_data = base64.b64encode(buffer).decode('utf-8')
                    ws.send(frame_data)
                else:
                    print("Frame encoding failed")
            time.sleep(max(video_interval - (time.time()-start),0.01))
    except ssl.SSLEOFError as e:
        print(f"SSL EOF error in thresh_feed_ws: {e}")
    except Exception as e:
        print(f"thresh_feed_ws video feed error: {e}")
    finally:
        print("Client disconnected from thresh_feed_ws", flush=True)

@sock.route('/autoguider_socket')
def autoguider_socket(ws):
    while True:
        try:
            if autoguider.data_ready:
                autoguider.data_ready = False
                ws.send(json.dumps(form_properties()))
            time.sleep(0.1)
        except ssl.SSLEOFError as e:
            print(f"SSL EOF error in autoguider_socket: {e}")
        except Exception as e:  # Catches WebSocketConnectionClosedException
            break
    print("autoguider_socket disconnected")

    
@sock.route('/telescope_socket')
def telescope_socket(ws):
    last_yield = time.time()
    while True:
        try:
            start = time.time()
            if start - last_yield > 100:
                properties = {"function": "ping"}
                ws.send(json.dumps(properties))
                last_yield = start

            slew_request = None
            if telescopeserver.slew_request is not None:
                slew_request = telescopeserver.slew_request
                telescopeserver.slew_request = None
            elif telescope.slew_request is not None:
                slew_request = telescope.slew_request
                telescope.slew_request = None

            if slew_request is not None:
                ra, dec = slew_request
                properties = {
                    "function": "slew_request",
                    "ra": ra,
                    "dec": dec
                }
                ws.send(json.dumps(properties))
            time.sleep(0.1)
        except ssl.SSLEOFError as e:
            print(f"SSL EOF error in telescope_socket: {e}")
        except Exception as e:  # Catches WebSocketConnectionClosedException
            print(f"Unexpected error in telescope_socket: {e}")
            break
    print("telescope_socket disconnected")


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
        except ssl.SSLEOFError as e:
            print(f"SSL EOF error in command_terminal: {e}")
        except Exception as e:
            ws.send(f"error: {str(e)}")
            current_process = None


# TELESCOPE 
@app.route('/scope_info', methods=['GET'])
def scope_info():
    return jsonify(telescope.scope_info)

@app.route('/set_tracking', methods=['POST'])
def set_tracking():
    tracking = request.form.get('tracking', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    telescope.send_tracking(tracking)
    time.sleep(0.1)
    telescope.get_info()
    return jsonify({'status': 'success', 'message': f'Tracking set to {tracking}'})

@app.route('/set_quiet', methods=['POST'])
def set_quiet():
    quiet = request.form.get('quiet', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    telescope.set_quiet(quiet)
    return jsonify({'status': 'success', 'message': f'Quiet mode set to {quiet}'})

@app.route('/set_locked', methods=['POST'])
def set_locked():
    locked = request.form.get('locked', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    telescope.set_locked(locked)
    return jsonify({'status': 'success', 'message': f'Locked mode set to {locked}'})

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

@app.route('/command_slew_request', methods=['POST'])
def command_slew_request():
    data = request.json
    ra = data.get('ra')
    dec = data.get('ra')
    telescope.slew_request = (ra,dec)
    return jsonify({'status': 'success', 'message': f'slew_request set'})


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


# CAMERA
@app.route('/save_frame', methods=['POST'])
def save_frame():
    if camera is not None and camera.running:
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

@app.route('/set_pixel_scale', methods=['POST'])
def set_pixel_scale():
    new_scale = request.form.get('pixel_scale', type=float, default=autoguider.pixel_scale)
    if 0.1 <= new_scale <= 10.0:
        autoguider.pixel_scale = new_scale
    return jsonify({"status": "success"}), 200

@app.route('/set_hot_pixel_mask', methods=['POST'])
def set_hot_pixel_mask():
    reset = not request.form.get('hot_pixel_mask', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    if reset:
        camera.clear_hot_pixel_mask()
    else:
        camera.capture_hot_pixel_mask()
    return jsonify({"status": "success"}), 200

@app.route('/get_camera_properties', methods=['GET'])
def get_camera_properties():    
    if camera is not None:
        return jsonify(camera.get_direct_controls())
    else:
        return jsonify({"status": "error", "message": "Camera not available"}), 503


@app.route('/set_direct_camera_property', methods=['POST'])
def set_direct_camera_property():
    name = request.json.get('name')
    value = request.json.get('value')    
    if camera is not None and camera.set_direct_control(name, value):
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "error", 'message': 'Failed setting '+name+' to '+value}), 200

@app.route('/set_camera_properties', methods=['POST'])
def set_camera_properties():
    if camera is None:
        return jsonify({"status": "error", "message": "Camera not available"}), 503
    
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

    camera_color = request.json.get('camera_color')
    if camera_color is not None:
        camera.set_color(camera_color)

    exposure = request.json.get('camera_exposure')
    if exposure is not None:
        camera.set_exposure(int(exposure))

    camera_index = request.json.get('camera_index')
    if camera_index is not None:
        camera.select_camera(int(camera_index))    

    return jsonify({"status": "success"}), 200



# AUTOGUIDER
def form_properties():
    telescope = Telescope()
    if camera is not None:
        camera_index = camera.camera_index
        width = camera.width
        height = camera.height
        exposure = camera.get_exposure()
        integrate_frames = camera.integrate_frames
        r_channel = camera.r_channel
        g_channel = camera.g_channel
        b_channel = camera.b_channel
        actual_fps = camera.cam_fps
        cam_mode = camera.cam_mode
        camera_color = camera.color
    else:
        camera_index = 0
        width = 1
        height = 1
        exposure = 1
        integrate_frames = 1
        r_channel = 1
        g_channel = 1
        b_channel = 1
        actual_fps = 5
        cam_mode = "MJPEG"
        camera_color = True
    

    properties = {
        "width": width,
        "height": height,
        "tracked_centroids": autoguider.tracked_centroids,
        "current_centroids": autoguider.current_centroids,
        "pec_position": telescope.scope_info["pec"]["progress"],
        "save_frames" : autoguider.save_frames,
        "max_drift": autoguider.max_drift,
        "star_size": autoguider.star_size,
        "gray_threshold": autoguider.gray_threshold,
        "rotation_angle": autoguider.rotation_angle,
        "pixel_scale": autoguider.pixel_scale,
        "guide_method": autoguider.guide_method,
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
        "camera_index": camera_index,
        "exposure": exposure,
        "exposure_ms": exposure/10,
        "integrate_frames": integrate_frames,
        "r_channel": r_channel,
        "g_channel": g_channel,
        "b_channel": b_channel,
        "camera_fps": actual_fps,
        "resolution": { "width":width, "height":height },
        "video_mode": cam_mode,
        "camera_color": camera_color,
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
    new_threshold = request.form.get('threshold', type=int, default=autoguider.gray_threshold)
    if 0 <= new_threshold <= 255:
        autoguider.gray_threshold = new_threshold
    return jsonify({"status": "success"}), 200

@app.route('/set_max_drift', methods=['POST'])
def set_max_drift():
    new_max_drift = request.form.get('max_drift', type=int, default=autoguider.max_drift)
    if 0 <= new_max_drift <= 50:
        autoguider.max_drift = new_max_drift
    return jsonify({"status": "success"}), 200

@app.route('/set_star_size', methods=['POST'])
def set_star_size():
    new_star_size = request.form.get('star_size', type=int, default=autoguider.star_size)
    if 1 <= new_star_size <= 100:
        autoguider.star_size = new_star_size
    return jsonify({"status": "success"}), 200

@app.route('/set_rotation_angle', methods=['POST'])
def set_rotation_angle():
    new_angle = request.form.get('rotation_angle', type=float, default=autoguider.rotation_angle)
    if -180 <= new_angle <= 180:
        autoguider.rotation_angle = new_angle
    return jsonify({"status": "success"}), 200

@app.route('/set_guide_interval', methods=['POST'])
def set_guide_interval():
    guide_interval = request.form.get('guide_interval', type=float, default=1)
    autoguider.guide_interval = guide_interval
    print(f"set guide interval to {guide_interval} and is {autoguider.guide_interval}")
    return jsonify({"status": "success"}), 200

@app.route('/set_guide_method', methods=['POST'])
def set_guide_method():
    guide_method = request.form.get('guide_method', type=str, default='PID')
    autoguider.guide_method = guide_method
    return jsonify({"status": "success"}), 200

@app.route('/set_guide_pulse', methods=['POST'])
def set_guide_pulse():
    guide_pulse = request.form.get('guide_pulse', type=float, default=1)
    autoguider.guide_pulse = guide_pulse
    return jsonify({"status": "success"}), 200


@app.route('/set_guiding', methods=['POST'])
def set_guiding():
    guiding = request.form.get('guiding', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    autoguider.enable_guiding(guiding)
    return jsonify({"status": "success"}), 200

@app.route('/set_dec_guiding', methods=['POST'])
def set_dec_guiding():
    dec_guiding = request.form.get('dec_guiding', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    autoguider.enable_dec_guiding(dec_guiding)
    return jsonify({"status": "success"}), 200

@app.route('/set_save_frames', methods=['POST'])
def set_save_frames():
    save_frames = request.form.get('save_frames', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    autoguider.save_frames = save_frames
    return jsonify({"status": "success"}), 200

@app.route('/acquire', methods=['POST'])
def acquire():
    if camera is None:
        return jsonify({'status': 'error', 'message': 'Camera not available'}), 503

    x = request.form.get('x', type=float)
    y = request.form.get('y', type=float)
    add = request.form.get('add', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean

    if x is not None and y is not None:
        if not add:
            autoguider.remove_all_tracked_stars()
        autoguider.add_tracked_star(centroid=(x*camera.width, y*camera.height))
        print(f"Acquisition triggered at ({x*camera.width}, {y*camera.height})")
        return jsonify({'status': 'success', 'message': f"Acquisition triggered at ({x}, {y})"}), 200
    else:
        autoguider.remove_all_tracked_stars()
        autoguider.add_tracked_star()
        print(f"Acquisition of brightest star triggered")
        return jsonify({'status': 'success', 'message': f"Acquisition of brightest star triggered"}), 200

@app.route('/remove_tracked_star', methods=['POST'])
def remove_tracked_star():
    if camera is None:
        return jsonify({'status': 'error', 'message': 'Camera not available'}), 503

    x = request.form.get('x', type=float)
    y = request.form.get('y', type=float)
    if autoguider.remove_tracked_star(centroid=(x*camera.width, y*camera.height)):
        print(f"Star removed at ({x*camera.width}, {y*camera.height})")
        return jsonify({'status': 'success', 'message': f"Tracked star removed at ({x}, {y})"}), 200
    else:
        print(f"No star found at ({x*camera.width}, {y*camera.height})")
        return jsonify({'status': 'error', 'message': f"No tracked star at ({x}, {y})"}), 503

@app.route('/calibrate', methods=['POST'])
def calibrate():
    with_backlash = request.form.get('with_backlash', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    if autoguider.calibrate_angle(with_backlash):
        print(f"Calibration successful")
        return jsonify({'status': 'success', 'message': 'Calibration successful'})
    else:
        print("Failed to calibrate")
        return jsonify({'status': 'error', 'message': "Failed to calibrate"}), 400



# ANALYSIS
@app.route('/analyze', methods=['POST'])
def analyze():   
    analysis_snr = float(request.json.get('analysis_snr'))
    analysis_std = float(request.json.get('analysis_std'))
    analysis_fwhm = float(request.json.get('analysis_fwhm'))
    analyzer = Analyzer()
    frame = camera.frame
    #analyzer.analyze_snr2(frame,snr_threshold)
    retval= analyzer.analyze_snr(frame,analysis_snr,analysis_std, analysis_fwhm)
    return jsonify(retval), 200

@app.route('/plateSolve', methods=['POST'])
def plateSolve():   
    filename = request.json.get('filename')
    capture = request.json.get('capture')
    if capture and camera is not None and camera.running:
        frame = camera.frame
        if frame is not None and frame.size > 0:
            # Save the frame as an image file
            save_path = os.path.join(os.getcwd(), 'saved_frame.png')
            cv2.imwrite(save_path, frame, [cv2.IMWRITE_PNG_COMPRESSION, 4])  # Save as PNG with mid compression
            print(f"Frame saved to {save_path}")
        else:
            return jsonify({"status": "error", "message": "No valid frame available"}), 400
    else:
        return jsonify({"status": "error", "message": "Camera is not running"}), 503
    
    platesolver = PlateSolver()
    try:
        ra, dec, rot, scale = platesolver.solve(filename)
        raStr = deg_to_lx200_ra(float(ra))
        decStr = deg_to_lx200_dec(float(dec))
        retval = {
            'status': 'ok',
            'ra' : raStr,
            'dec' : decStr,
            'rotation' : rot,
            'scale' : scale
        }
        telescope.slew_request = (raStr, decStr)
        return jsonify(retval), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


# Shutdown APPLICATION
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


def cleanup():
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
        telescope.get_current_position()
        telescope.send_tracking(False)    #disable tracking to not spoil PEC position
        all_settings.update_telescope_settings(telescope)
        telescope.stop_bridge()
        telescope.close_connection()
        print("Telescope closed.")

        if camera is not None:
            print("Stopping autoguider camera..")        
            camera.stop_capture()
            camera.release_camera()
            all_settings.update_camera_settings(camera)
            print("Camera stopped.")

        cv2.destroyAllWindows()
        all_settings.save_settings()
        print("Resources released")

    except Exception as e:
        print(f"Error during cleanup: {e}")


class ServerThread(Thread):
    def __init__(self, app):
        Thread.__init__(self)
        # SSL Context
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ssl_context.load_cert_chain(certfile='cert/cert.pem', keyfile='cert/key.pem')

        # Make server on port 8443 (HTTPS)
        self.server = make_server('0.0.0.0', 8443, app, threaded=True)
        self.server.socket = self.ssl_context.wrap_socket(self.server.socket, server_side=True)

        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        print("Starting Flask server on 0.0.0.0:80")
        self.server.serve_forever()

    def shutdown(self):
        print("Shutting down Flask server")
        self.server.shutdown()


def signal_handler(sig, frame):
    print(f"Received signal {sig}, initiating shutdown", flush=True)
    if global_server:
        cleanup()
        global_server.shutdown()
    sys.exit(0)

if __name__ == '__main__':
    
    print("PipiTrek commander starting up...")
    all_settings = Settings()
    all_settings.load_settings()

    #telescope startup
    print("Connecting to telescope..")
    telescope = Telescope()
    time.sleep(2) # wait arduino
    all_settings.set_telescope_settings(telescope)
    telescope.start_bridge()
    print("telescope started.")

    print("Setting up autoguider camera..")
    try:
        camera = Camera()
        camera.init_camera()
        all_settings.set_camera_settings(camera)
        camera.load_hot_pixel_mask() 
        camera.start_capture()
        print("camera set up.")
    except Exception as e:
        print(f"Error initializing camera: {e}")
        camera = None

    print("Setting up autoguider..")
    autoguider = Autoguider()
    all_settings.set_autoguider_settings(autoguider)
    autoguider_thread = Thread(target=autoguider.run_autoguider)
    autoguider_thread.start()
    print("autoguider set up.")

    # TCP telescope server
    telescopeserver = TelescopeServer()
    telescopeserver.start()

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)    

    global_server = ServerThread(app)
    global_server.start()
    try:
        while global_server.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("KeyboardInterrupt received")
        signal_handler(signal.SIGINT, None)
    finally:
        global_server.join(timeout=10)
        if global_server.is_alive():
            print("Warning: Server thread did not stop in time")
        print("Application shut down gracefully")