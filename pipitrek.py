import datetime
import time as _startup_clock

_startup_started = _startup_clock.perf_counter()
_startup_last = _startup_started


def _startup_log(message):
    global _startup_last
    now = _startup_clock.perf_counter()
    print(
        f"[startup +{now - _startup_started:.2f}s, "
        f"step +{now - _startup_last:.2f}s] {message}",
        flush=True,
    )
    _startup_last = now


_startup_log("beginning module imports")

from asyncio import tasks

from flask import Flask, request, redirect, url_for, Response, jsonify, send_file
_startup_log("Flask imported")

from analyzer import Analyzer
_startup_log("Analyzer imported")

from autoguider import Autoguider
_startup_log("Autoguider imported")

from camera import Camera
from comm.telescopeserver import TelescopeServer
from platesolver import PlateSolver
from threading import Thread, Event
from conversions import deg_to_lx200_ra, deg_to_lx200_dec
from telescope_task_scheduler import TelescopeTaskScheduler
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
from telescope_task import PlateSolveTask, TelescopeImagingTask, TelescopeInitializePositionTask, TelescopeMeridianFlipTask, TelescopeParkTask, TelescopeSlewingTask, TelescopeStartAutoguiderTask, TelescopeStopAutoguiderTask
from v412_ctl import list_cameras
_startup_log("remaining application modules imported")

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
global autoguider, autoguider_sett, autoguider_thread, telescope_task_scheduler
current_process = None
autoguider = None
autoguider_sett  = None
autoguider_thread = None
all_settings = None
telescope = None
camera = None
telescopeserver = None
global_server = None
telescope_task_scheduler = None

log_index:dict[str, list[int]] = {}

video_interval = 0.5 # interval for generating video frames
frame_timeout = 30 # seconds before timeout
_startup_log("module setup complete")


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
    last_yield = time.time()-5
    while True:
        try:
            start = time.time()
            if start - last_yield > 5:
                properties = {"function": "telescopeStatus",
                              "status": telescope.get_status(),
                              "bluetooth": telescope.bt_serial.is_open,
                              "telescope_server_client_ip": telescopeserver.get_client_address()
                              }
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

@app.route('/get_log/<string:day>', methods=['GET'])
def get_log_endpoint(day):
    from_line = request.args.get('from_line', default=0, type=int)
    if day is None:
        day = datetime.datetime.now().strftime("%Y-%m-%d")
    lines = []
    lineindex = log_index.get(day)
    if lineindex is None:
        lineindex = []
        log_index[day] = lineindex

    with open(f"pipitrek.log", "r") as log_file:
        if from_line < len(lineindex):
            log_file.seek(lineindex[from_line])
        else:
            for _ in range(from_line):
                log_file.readline()
                lineindex.append(log_file.tell())
        while True:
            line = log_file.readline()
            if not line:
                break
            lineindex.append(log_file.tell())
            lines.append(line)
        
        return jsonify({'status': 'ok', 'task_log': lines})

    return jsonify({'status': 'error', 'message': 'Failed to read task log'})

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
    if speed in ['G', 'C', 'M', 'S','A']:
        print(f"Received speed: {speed}")
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
    print(f"Received PEC table: {pec_table}")
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

@app.route('/set_pec_enabled', methods=['POST'])
def set_pec_enabled():
    try:
        enable = request.form.get('enable', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
        if enable is None:
            raise ValueError("PEC enable flag is missing or invalid")
        
        telescope.send_PEC_enabled(enable)
        return jsonify({'status': 'success', 'message': f'PEC set to {enable}'})
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
    ret = TelescopeSlewingTask(telescope, ra, dec).execute()
    return jsonify(ret)

@app.route('/command_goto_direct', methods=['POST'])
def command_goto_direct():
    data = request.json
    ra = data.get('ra')
    dec = data.get('dec')
    print(f"DIRECT GOTO command received: RA={ra}, DEC={dec}")
    ret = telescope.send_go_to(ra, dec)
    print(f"DIRECTLY Moving to segment: RA={ra}, DEC={dec}, PIER={segment_pier}")
    return jsonify(ret)

@app.route('/command_set_to', methods=['POST'])
def command_set_to():
    data = request.json
    ra = data.get('ra')
    dec = data.get('dec')
    print(f"SET TO command received: RA={ra}, DEC={dec}")
    telescope.send_set_to(ra,dec)
    telescope.send_lst()
    return jsonify({'status': 'success', 'message': f'SET TO RA={ra}, DEC={dec}'})



### Task scheduler endpoints
@app.route('/start_scheduler', methods=['POST'])
def start_scheduler_endpoint():
    if telescope_task_scheduler is None:
        return jsonify({'status': 'error', 'message': 'Telescope task scheduler is not initialized'}), 503
    
    if telescope_task_scheduler.start():
        return jsonify({'status': 'ok', 'message': 'Scheduler started'})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to start scheduler'})

@app.route('/stop_scheduler', methods=['POST'])
def stop_scheduler_endpoint():
    if telescope_task_scheduler is None:
        return jsonify({'status': 'error', 'message': 'Telescope task scheduler is not initialized'}), 503
    
    telescope_task_scheduler.stop();    
    return jsonify({'status': 'ok', 'message': 'Scheduler stopped'})

@app.route('/task_list_status', methods=['GET'])
def task_list_status_endpoint():
    if telescope_task_scheduler is None:
        return jsonify({'status': 'error', 'message': 'Telescope task scheduler is not initialized'}), 503   
    
    return jsonify(telescope_task_scheduler.get_task_list_status())

@app.route('/get_task_list', methods=['GET'])
def get_task_list_endpoint():
    if telescope_task_scheduler is None:
        return jsonify({'status': 'error', 'message': 'Telescope task scheduler is not initialized'}), 503
    
    return jsonify(telescope_task_scheduler.get_task_list())

@app.route('/add_tasks', methods=['POST'])
def add_tasks_endpoint():
    if telescope_task_scheduler is None:
        return jsonify({'status': 'error', 'message': 'Telescope task scheduler is not initialized'}), 503

    tasks = request.json
    if not isinstance(tasks, list) or not tasks:
        return jsonify({'status': 'error', 'message': 'Expected a non-empty JSON array of tasks'}), 400

    telescope_task_scheduler.add_to_task_list(tasks)
    return jsonify({'status': 'ok', 'message': f'Added {len(tasks)} task(s)'})

@app.route('/remove_task/<int:task_id>', methods=['POST', 'DELETE'])
def remove_task_endpoint(task_id):
    if telescope_task_scheduler is None:
        return jsonify({'status': 'error', 'message': 'Telescope task scheduler is not initialized'}), 503

    if not telescope_task_scheduler.remove_from_task_list(task_id):
        return jsonify({'status': 'error', 'message': 'Task not found'}), 409

    return jsonify({'status': 'ok', 'message': f'Removed task {task_id}'})

@app.route('/get_task/<int:task_id>', methods=['GET'])
def get_task_endpoint(task_id):
    if telescope_task_scheduler is None:
        return jsonify({'status': 'error', 'message': 'Telescope task scheduler is not initialized'}), 503

    task = telescope_task_scheduler.get_task(task_id)
    if task is None:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404

    return jsonify({'status': 'ok', 'task': task})


@app.route('/get_task_log/<string:day>', methods=['GET'])
def get_task_log_endpoint(day):
    if telescope_task_scheduler is None:
        return jsonify({'status': 'error', 'message': 'Telescope task scheduler is not initialized'}), 503

    from_line = request.args.get('from_line', default=0, type=int)
    task_log = telescope_task_scheduler.get_task_log(day,from_line)
    return jsonify({'status': 'ok', 'task_log': task_log})



# CAMERA

@app.route('/get_camera_list')
def get_camera_list():
    list = list_cameras()
    print(list)
    return jsonify(list)


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
        "max_drift_ra": autoguider.max_drift_ra,
        "max_drift_dec": autoguider.max_drift_dec,
        "min_star_size": autoguider.min_star_size,
        "max_star_size": autoguider.max_star_size,
        "gray_threshold": autoguider.gray_threshold,
        "auto_threshold": autoguider.auto_threshold,
        "rotation_angle": autoguider.rotation_angle,
        "pixel_scale": autoguider.pixel_scale,
        "guide_method_ra": autoguider.guide_method_ra,
        "guide_method_dec": autoguider.guide_method_dec,
        "guiding": autoguider.guiding,
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
        "ra_pid_p": autoguider.ra_pid.Kp,
        "ra_pid_i": autoguider.ra_pid.Ki,
        "ra_pid_d": autoguider.ra_pid.Kd,
        "dec_pid_p": autoguider.dec_pid.Kp,
        "dec_pid_i": autoguider.dec_pid.Ki,
        "dec_pid_d": autoguider.dec_pid.Kd
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
    autoguider.ra_pid.Kp = float(data.get('ra_pid_p', 0.5))
    autoguider.dec_pid.Kp = float(data.get('dec_pid_p', 0.5))

    autoguider.ra_pid.Ki = float(data.get('ra_pid_i', 0.1))
    autoguider.dec_pid.Ki = float(data.get('dec_pid_i', 0.1))
    
    autoguider.ra_pid.Kd = float(data.get('ra_pid_d', 0.2))
    autoguider.dec_pid.Kd = float(data.get('dec_pid_d', 0.2))
    return jsonify({"status": "success"}), 200

@app.route('/set_threshold', methods=['POST'])
def set_threshold():
    new_threshold = request.form.get('threshold', type=int, default=autoguider.gray_threshold)
    auto_threshold = request.form.get('auto_threshold', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    if 0 <= new_threshold <= 255:
        autoguider.gray_threshold = new_threshold
    autoguider.auto_threshold = auto_threshold
    return jsonify({"status": "success"}), 200

@app.route('/set_auto_threshold', methods=['POST'])
def set_auto_threshold():
    auto_threshold = request.form.get('auto_threshold', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    autoguider.auto_threshold = auto_threshold
    return jsonify({"status": "success"}), 200

@app.route('/set_max_drift', methods=['POST'])
def set_max_drift():
    new_max_drift = request.form.get('max_drift', type=int, default=autoguider.max_drift_ra)
    axis = request.form.get('axis', type=str, default='ra')
    if 0 <= new_max_drift <= 50:
        if axis == 'ra':
            autoguider.max_drift_ra = new_max_drift
            print(f"set max drift RA to {new_max_drift} and is {autoguider.max_drift_ra}")
        elif axis == 'dec':
            autoguider.max_drift_dec = new_max_drift
            print(f"set max drift DEC to {new_max_drift} and is {autoguider.max_drift_dec}")
    return jsonify({"status": "success"}), 200

@app.route('/set_min_star_size', methods=['POST'])
def set_min_star_size():
    new_star_size = request.form.get('min_star_size', type=int, default=autoguider.star_size)
    if 1 <= new_star_size <= 100:
        autoguider.min_star_size = new_star_size
    return jsonify({"status": "success"}), 200

@app.route('/set_max_star_size', methods=['POST'])
def set_max_star_size():
    new_star_size = request.form.get('max_star_size', type=int, default=autoguider.max_star_size)
    if 1 <= new_star_size <= 1000:
        autoguider.max_star_size = new_star_size
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
    axis = request.form.get('axis', type=str, default='ra')
    if axis == 'ra':
        autoguider.guide_method_ra = guide_method
    elif axis == 'dec':
        autoguider.guide_method_dec = guide_method
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

@app.route('/set_save_frames', methods=['POST'])
def set_save_frames():
    save_frames = request.form.get('save_frames', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    autoguider.save_frames = save_frames
    return jsonify({"status": "success"}), 200

@app.route('/auto_add_tracked_stars', methods=['POST'])
def auto_add_tracked_stars():
    number_to_add = request.form.get('number_to_add', type=int, default=5)
    centroids = autoguider.auto_add_tracked_stars(number_to_add)
    if centroids is not None:
        return jsonify({'status': 'success', 'message': f"Added {len(centroids)} tracked stars"}), 200
    else:
        return jsonify({'status': 'error', 'message': f"No tracked stars added"}), 503
    
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

@app.route('/reset_centroids', methods=['POST'])
def reset_centroids():
    if autoguider is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not available'}), 503
    autoguider.reset_centroids()
    print(f"Centroids reset to current star positions")
    return jsonify({'status': 'success', 'message': "Centroids reset to current star positions"}), 200

@app.route('/clear_centroids', methods=['POST'])
def clear_centroids():
    if autoguider is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not available'}), 503
    autoguider.remove_all_tracked_stars()
    print(f"Centroids cleared")
    return jsonify({'status': 'success', 'message': "Centroids cleared"}), 200

@app.route('/calibrate', methods=['POST'])
def calibrate():
    if autoguider is None:
        return jsonify({'status': 'error', 'message': 'Autoguider not available'}), 503
    
    with_backlash = request.form.get('with_backlash', type=lambda v: v.lower() == 'true')  # Convert "true"/"false" to boolean
    result = False
    if not with_backlash:
        result = autoguider.calibrate_angle_with_tracking(num_seconds=30)
    else:
        result = autoguider.calibrate_angle(with_backlash)

    if result:
        return jsonify({'status': 'success', 'message': 'Calibration successful'})
    else:
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
    result = PlateSolveTask(telescope, camera, filename, capture).execute()
    return jsonify(result),     result.get('status') == 'error' and 503 or 200


@app.route('/orient', methods=['POST'])
def orient():
    if camera is None or not camera.running:
        return jsonify({"status": "error", "message": "Camera is not running"}) , 503
    retval = TelescopeInitializePositionTask(telescope, camera, autoguider).execute()
    status = retval.get('status') == 'error' and 503 or 200
    return jsonify(retval), status



# Shutdown APPLICATION
@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Gracefully shut down the Flask app and perform cleanup. Optionally powers off the host afterwards."""
    if request.method != 'POST':
        return jsonify({"error": "Method not allowed"}), 405

    body = request.get_json(silent=True) or {}
    poweroff = bool(body.get('poweroff', False))

    print(f"Shutdown requested via /shutdown (poweroff={poweroff})")
    shutdown_event.set()  # Signal threads to stop

    cleanup()

    def _exit_process():
        time.sleep(1)
        if poweroff:
            print("Powering off Linux host...")
            os.system("poweroff")
        os._exit(0)

    # Attempt Werkzeug shutdown
    func = request.environ.get('werkzeug.server.shutdown')
    if func is not None:
        func()
        print("Werkzeug server shutdown initiated")
    else:
        print("Not running with Werkzeug server, forcing shutdown")

    # Always force the process (and optionally the host) down after cleanup, since make_server doesn't expose werkzeug.server.shutdown
    Thread(target=_exit_process).start()
    message = "Server shutting down" + (" and powering off" if poweroff else "")
    return jsonify({"message": message}), 200


def cleanup():
    try:        
        print("Stopping TCP telescope server..")
        telescopeserver.stop()
        
        print("Stopping telescope task scheduler..")
        if telescope_task_scheduler is not None:
            telescope_task_scheduler.stop()
            telescope_task_scheduler.save_task_list("task_list.json")
    
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

    _startup_log("PipiTrek commander starting up")
    _startup_log("loading settings")
    all_settings = Settings()
    all_settings.load_settings()
    _startup_log("settings loaded")

    #telescope startup
    _startup_log("connecting to telescope")
    telescope = Telescope()
    _startup_log("telescope object initialized; waiting 2 seconds for Arduino")
    time.sleep(2) # wait arduino
    all_settings.set_telescope_settings(telescope)
    _startup_log("starting telescope bridge")
    telescope.start_bridge()
    _startup_log("telescope started")

    _startup_log("setting up autoguider camera")
    try:
        camera = Camera()
        _startup_log("camera object initialized; opening camera")
        camera.init_camera()
        _startup_log("camera opened; loading settings and hot-pixel mask")
        all_settings.set_camera_settings(camera)
        camera.load_hot_pixel_mask() 
        camera.start_capture()
        _startup_log("camera capture started")
    except Exception as e:
        _startup_log(f"camera initialization failed: {e}")
        camera = None

    _startup_log("setting up autoguider")
    autoguider = Autoguider()
    all_settings.set_autoguider_settings(autoguider)
    _startup_log("starting autoguider thread")
    autoguider_thread = Thread(target=autoguider.run_autoguider)
    autoguider_thread.start()
    _startup_log("autoguider thread started")

    _startup_log("initializing telescope task scheduler")
    telescope_task_scheduler = TelescopeTaskScheduler(camera, telescope, autoguider)
    _startup_log("telescope task scheduler initialized")
    # must be started by user
    # telescope_task_scheduler.start()  

    # TCP telescope server
    _startup_log("starting TCP telescope server")
    telescopeserver = TelescopeServer()
    telescopeserver.start()
    _startup_log("TCP telescope server started")

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)    

    _startup_log("creating HTTPS web server")
    global_server = ServerThread(app)
    _startup_log("starting HTTPS web server")
    global_server.start()
    _startup_log("web server thread started; entering service loop")
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