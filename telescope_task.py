from __future__ import annotations
import os
import cv2
from platesolver import PlateSolver
from telescope import Telescope
from conversions import *
import telescope
from telescope_commands import PTCCameraStart

class TelescopeTask:
    def __init__(self, telescope:Telescope):
        self.telescope = telescope
        self.executed = False
        self.needs_stop = False
        self.response = None
        self.time = 0
        self.start_time = 0
        self.end_time = 0

    def _start_timer(self):
        self.start_time = time.time()

    def _stop_timer(self):
        self.end_time = time.time()
        self.time = self.end_time - self.start_time

    def _exit(self,result):
        self._stop_timer()
        self.response = result
        self.executed = True
        return self.response
    
    def execute(self):
        self.executed = True
        # Implement the execution logic for the telescope task here
        # Update self.response and self.time as needed

    def stop(self):
        self.executed = True
        # Implement emergency stop logic for the telescope task here
        # Update self.response and self.time as needed

    def time_estimate(self):
        if self.executed:
            return 0
        if self.start_time == 0:
            return self.time   
        return self.time - (time.time() - self.start_time)

    def percent_complete(self):
        if self.time == 0:
            return 0
        return int(self.time_estimate()/ self.time * 100) if not self.executed else 100

    def is_finished(self):
        # Implement the logic to check if the telescope task is finished
        # Return True if finished, False otherwise
        return self.executed



class TelescopeImagingTask(TelescopeTask):
    def __init__(self, telescope:Telescope, exposure_time, exposure_count, camera=None, autoguider=None):
        super().__init__(telescope)
        self.exposure_time = exposure_time
        self.exposure_count = exposure_count
        self.camera = camera
        self.autoguider = autoguider
        self.time = (self.exposure_time+1) * self.exposure_count
        self.flip_task = None

    def execute(self):
        # during this task, we should monitor telescope position and watch for meridian flip.
        # In case of flip, stop the camera temporarily, perform flip, then continue imaging
        #     meridian flip
        #     telescope orientation/plate solving is required
        #     another move to the target coordinates
        #     resume imaging
        self._start_timer()
        self.telescope.send_camera(self.exposure_count,self.exposure_time)
        PTCCameraStart(True).execute(self.telescope)
        print("Starting camera.")
        last_position_check=time.time()
        while not self.is_finished():
            if self.needs_stop:
                return self._exit({'status': 'stopped', 'message': 'Task stopped due to user request.'})
            time.sleep(self.exposure_time/2)

            # position check every 30 seconds
            if time.time() - last_position_check >= 30:
                last_position_check = time.time()
                self.telescope.get_current_position()

                if not self.telescope.is_position_allowed():
                    print("Telescope position is not allowed. Waiting for meridian flip or repositioning.")
                    if self.telescope.does_position_require_flip():
                        print("Meridian flip required. Performing flip...")
                        print("Stopping camera for meridian flip.")
                        self.telescope.get_info()
                        remaining = self.telescope.scope_info["camera"]["shots"]
                        PTCCameraStart(False).execute(self.telescope)
                        
                        print("Stopping autoguider for meridian flip.")
                        if self.autoguider:
                            if self.autoguider.is_guiding():
                                self.autoguider.enable_guiding(False)

                        if self.needs_stop:
                            return self._exit({'status': 'stopped', 'message': 'Task stopped due to user request.'})
                            
                        self.flip_task = TelescopeMeridianFlipTask(self.telescope)
                        self.flip_task.execute()
                        self.flip_task = None

                        if self.needs_stop:
                            return self._exit({'status': 'stopped', 'message': 'Task stopped due to user request.'})

                        if self.camera and self.autoguider:
                            result = TelescopeInitializePositionTask(self.telescope, self.camera, self.autoguider).execute()
                            if result['status'] != 'ok':
                                self.executed=True
                                print("Failed to initialize telescope position after meridian flip.")
                                return self._exit({'status': 'error', 'message': 'Failed to initialize telescope position after meridian flip.'})
                            result =TelescopeStartAutoguiderTask(self.telescope, self.autoguider).execute()
                            if result['status'] != 'ok':
                                self.executed=True
                                print("Failed to start autoguider after meridian flip.")
                                return self._exit({'status': 'error', 'message': 'Failed to start autoguider after meridian flip.'})

                        self.telescope.send_camera(remaining,self.exposure_time)
                        PTCCameraStart(True).execute(self.telescope)
                        continue
                    else:
                        print("Repositioning required. Aborting job.")
                        PTCCameraStart(False).execute(self.telescope)
                        self.executed=True
                        return self._exit({'status': 'error', 'message': 'Repositioning required. Aborting job.'})

        print("Imaging task completed with success.")
        return self._exit({'status': 'ok', 'message': 'Imaging task completed with success.'})

    def stop(self):
        self.needs_stop = True
        # Implement emergency stop logic for the telescope task here
        if self.flip_task:
            self.flip_task.stop()
        self.telescope.send_camera(0,self.exposure_time)
        PTCCameraStart(False).execute(self.telescope)
        self.executed=True
        return self._exit({'status': 'stopped', 'message': 'Task stopped due to user request.'})

    def is_finished(self):
        # Send get info to telescope, parse camera status
        # Return True if finished, False otherwise
        if self.executed:
            return True
        self.telescope.get_info()
        self.executed = (self.telescope.scope_info["camera"]["state"] == "I")
        return self.executed

    def time_estimate(self):
        # Implement the logic to estimate the time required to finish
        self.telescope.get_info()
        tr = self.telescope.scope_info["camera"]["exposure"]*self.telescope.scope_info["camera"]["shots"]
        return tr


class TelescopeSlewingTask(TelescopeTask):
    def __init__(self, telescope:Telescope, target_ra, target_dec, autoguider:Autoguider=None):
        super().__init__(telescope)
        self.autoguider = autoguider
        self.target_ra_deg = lx200_to_ra_deg(target_ra)
        self.target_dec_deg = lx200_to_dec_deg(target_dec)
        self.time = 0   # at task creation time it's difficult to estimate, since we don't know the current position and potential meridian flips

    def execute(self):


        self._start_timer()

        if self.telescope is None:
            return self._exit({'status': 'error', 'message': 'Telescope is not initialized'})   

        if self.autoguider is not None:
            self.autoguider.enable_guiding(False)

        self.telescope.get_current_position()

        speed = 1.5
        self.time = (abs(self.telescope.dec_deg-self.target_dec_deg)+abs(self.telescope.ra_deg-self.target_ra_deg))/speed
        pier = self.telescope.scope_info.get('pier')
        needflip = self.telescope.does_move_need_meridian_flip(self.telescope.ra_deg, self.telescope.dec_deg, self.target_ra_deg, self.target_dec_deg,pier)
        if needflip:
            self.time += 200  # Add estimated time for meridian flip


        pier = self.telescope.scope_info.get('pier')
        if pier not in ('E', 'W'):
            return self._exit({'status': 'error', 'message': f'Invalid current pier side: {pier}'})

        start_ra_deg = self.telescope.ra_deg
        start_dec_deg = self.telescope.dec_deg

        if None in (start_ra_deg, start_dec_deg, self.target_ra_deg, self.target_dec_deg):
            return self._exit({'status': 'error', 'message': 'Current or target coordinates are uninitialized'})

        segments = self.telescope.split_move(start_ra_deg, start_dec_deg, self.target_ra_deg, self.target_dec_deg, pier)
        allowed = segments is not None
        
        if allowed:
            for segment_ra, segment_dec, segment_pier in segments:
                if self.needs_stop:
                    return self._exit({'status': 'stopped', 'message': 'Task stopped due to user request.'})

                ra_ = deg_to_lx200_ra(segment_ra)
                dec_ = deg_to_lx200_dec(segment_dec)

                if(segment_pier != pier):
                    TelescopeMeridianFlipTask(self.telescope).execute()

                if self.needs_stop:
                    return self._exit({'status': 'stopped', 'message': 'Task stopped due to user request.'})

                self.telescope.send_go_to(ra_, dec_)
                print(f"Moving to segment: RA={ra_}, DEC={dec_}, PIER={segment_pier}")
                while self.telescope.getSlewDistance()=="1":
                    time.sleep(2)
        else:
            return self._exit({'status': 'error', 'message': 'Slewing not allowed due to invalid segments'})

        return self._exit({'status': 'ok', 'message': 'Slewing finished.'})

    def stop(self):        
        self.needs_stop = True
        self.telescope.send_stop()
        return self._exit({'status': 'stopped', 'message': 'Task stopped due to user request.'})


class TelescopeMeridianFlipTask(TelescopeTask):
    def __init__(self, telescope:Telescope):
        super().__init__(telescope)
        self.time = 200 # Estimated time for the meridian flip in seconds

    def execute(self):
        self._start_timer()
        print(f"Performing pier flip")
        self.telescope.send_pier('F')
        while self.telescope.getSlewDistance()=="1":
            time.sleep(2)
        return self._exit({'status': 'ok', 'message': 'Pier flip finished.'})

    def stop(self):        
        self.telescope.send_stop()
        return self._exit({'status': 'stopped', 'message': 'Task stopped due to user request.'})

    def is_finished(self):
        if self.executed:
            return True
        return self.telescope.getSlewDistance()!="1"


class PlateSolveTask(TelescopeTask):
    # capture image, plate solve
    def __init__(self, telescope:Telescope, camera, filename, capture):
        super().__init__(telescope)
        self.camera = camera
        self.time = 20
        self.filename = filename
        self.capture = capture

    def execute(self):        
        self._start_timer()        
        frame = None
        if self.capture and (self.camera is None or not self.camera.running):
            self.executed = True
            return self._exit({"status": "error", "message": "Camera is not running"}, 503)
        if self.capture:
            frame = self.camera.frame
            if frame is not None and frame.size > 0:
                # Save the frame as an image file
                save_path = os.path.join(os.getcwd(), self.filename)
                cv2.imwrite(save_path, frame, [cv2.IMWRITE_PNG_COMPRESSION, 4])  # Save as PNG with mid compression
            else:
                self.executed = True
                return self._exit({"status": "error", "message": "No valid frame available"})
    
        platesolver = PlateSolver()
        
        try:
            ra, dec, rot, scale = platesolver.solve(self.filename)
            raStr = deg_to_lx200_ra(float(ra))
            decStr = deg_to_lx200_dec(float(dec))
            retval = {
                'status': 'ok',
                'ra' : raStr,
                'dec' : decStr,
                'rotation' : rot,
                'scale' : scale
            }
            self.executed = True
            return self._exit(retval)
        
        except Exception as e:
            return self._exit({'status': 'error', 'message': str(e)})


class TelescopeInitializePositionTask(TelescopeTask):
    # capture image, plate solve, set coordinates
    def __init__(self, telescope:Telescope, camera, autoguider):
        super().__init__(telescope)
        if autoguider is None:
            from autoguider import Autoguider  # deferred: autoguider.py imports telescope.py, which imports this module
            autoguider = Autoguider()
        self.autoguider = autoguider
        self.camera = camera if camera is not None else self.autoguider.camera if self.autoguider is not None else None
        self.time = 20 

    def execute(self):
        self._start_timer()
        result = PlateSolveTask(self.telescope, self.camera, "saved_frame.png", True).execute()
        if result.get('status') == 'error':
            return self._exit(result)

        self.telescope.send_set_to(result.get('ra'), result.get('dec'))
        self.telescope.send_lst()
        if -180 <= result.get('rotation') <= 180:
            self.autoguider.rotation_angle = result.get('rotation')
            self.autoguider.pixel_scale = result.get('scale')

        return self._exit(result)



class TelescopeStartAutoguiderTask(TelescopeTask):
    # capture image, plate solve, set coordinates
    def __init__(self, telescope:Telescope, autoguider, calibrate_axis=False):
        super().__init__(telescope)
        self.autoguider = autoguider
        self.calibrate_axis = calibrate_axis
        self.time = 7 

    def execute(self):
        self._start_timer()
        # WAIT FOR TELESCOPE TO SETTLE
        time.sleep(5)  
        # prepare telescope for autoguiding
        if self.calibrate_axis:
            self.autoguider.calibrate_angle()

        if self.autoguider.auto_add_tracked_stars(5) is None:
            return self._exit({'status': 'error', 'message': 'Failed to auto-add tracked stars'})
        self.autoguider.enable_guiding(True)
        result = {"status": "ok"}
        return self._exit(result)

    def stop(self):        
        self.needs_stop = True
        self.autoguider.enable_guiding(False)


class TelescopeStopAutoguiderTask(TelescopeTask):
    # capture image, plate solve, set coordinates
    def __init__(self, telescope:Telescope, autoguider):
        super().__init__(telescope)
        self.autoguider = autoguider
        self.time = 2 

    def execute(self):
        self._start_timer()
        self.autoguider.enable_guiding(False)
        result = {"status": "ok"}
        self.executed = True
        return self._exit(result)


class TelescopeParkTask(TelescopeTask):
    def __init__(self, telescope:Telescope):
        super().__init__(telescope)
        self.time = 60  # Estimated time to park the telescope
        self.slewing_task = None

    def execute(self):
        self._start_timer()
        park_position = self.telescope.get_park_position()
        raStr = deg_to_lx200_ra(float(park_position[0]))
        decStr = deg_to_lx200_dec(float(park_position[1]))        
        # stop tracking before parking
        self.telescope.send_tracking(False)
        self.slewing_task = TelescopeSlewingTask(self.telescope, raStr, decStr)
        result = self.slewing_task.execute()
        self.slewing_task = None
        return self._exit(result)

    def stop(self):        
        self.needs_stop = True
        if self.slewing_task is not None:
            self.slewing_task.stop()
        return self._exit({'status': 'stopped', 'message': 'Task stopped due to user request.'})
