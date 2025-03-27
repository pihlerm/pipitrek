
from threading import RLock, Thread
import serial
import time
import subprocess
import json
import queue
from comm.virtual_port import VirtualSerialPort
from comm.btserial import BTSerial
from comm.tcpserial import TCPSerial
from telescope_commands import *

class Telescope:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Telescope, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.open_serial()
            self.pause = False
            self.scope_info = None
            self.bt_serial = BTSerial()
            #self.tcp_serial = TCPSerial()
            #self.tcp_serial.open()  
            self.lock = RLock()  # Thread lock for serial operations
            self.scope_info = {}
            self.scope_info["pec"] = {}
            self.scope_info["pec"]["progress"] = 0
            self.scope_info["pier"] = "W"
            self.scope_info["quiet"] = False
            self.scope_info["tracking"] = "disabled"
            self.scope_info["text"] = ""

            self.quiet = False
            self._thread = None


    def open_serial(self):
        self._serial_connection = serial.Serial(
            port='/dev/ttyUSB0',
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1,
            #dsrdtr=False  # Explicitly disable DTR (and DSR) handling
        )
        self._serial_connection.dtr = False  # Disable DTR to prevent reset
        self._serial_connection.flush()  # Clear the buffer
        print("Telescope serial connection initialized")

    def current_pecpos(self):
        if self.scope_info and "pec" in self.scope_info and "progress" in self.scope_info["pec"]:
            pec_progress = self.scope_info["pec"]["progress"]
            if isinstance(pec_progress, int) and 0 <= pec_progress <= 99:
                return pec_progress
        return 0


    def try_on_scope(self, func):
        with self.lock:
            while True:
                try:
                    if self._serial_connection.is_open:
                        return func()
                    else:
                        raise ConnectionError("Serial connection is not open")
                except serial.SerialException as se:
                    print(f"Serial error: {se} - Attempting to reset USB")
                    if self.reset_usb():
                        continue
                    else:
                        raise ConnectionError("USB reset failed")
                except Exception as e:
                    print(f"Serial exception: {e} - Attempting to reset USB")
                    if self.reset_usb():
                        continue
                    else:
                        raise ConnectionError("USB reset failed")

    def write_scope(self, data):
        #print(f"scope send: {data}")
        self.try_on_scope(lambda: self._serial_connection.write(data))

    def read_scope(self):
        data = self.try_on_scope(lambda: self._serial_connection.read(self._serial_connection.in_waiting))
        #print(f"scope read: {data}")
        return data

    def readline_scope(self, timeout=1):
        prevto = self._serial_connection.timeout
        self._serial_connection.timeout = timeout
        data =  self.try_on_scope(lambda: self._serial_connection.readline())
        self._serial_connection.timeout = prevto
        #print(f"scope readline: {data}")
        return data

    def read_scope_byte(self):
        data = self.try_on_scope(lambda: self._serial_connection.read(1))
        #print(f"scope read: {data}")
        return data

    def start_bridge(self):
        if self._thread is not None:
            print("telescope bridge started...")
            return
        self._thread = Thread(target=self.run_serial_bridge)
        self._thread.start()

    def stop_bridge(self):
        if self._thread is None:
            print("telescope bridge already stopped...")
            return
        self.running = False
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            print("Warning: Telescope bridge thread did not stop in time")


    def run_serial_bridge(self):
        self.running = True
        
        bt = self.bt_serial
        #tcp = self.tcp_serial

        self._serial_connection.timeout = 0  # Non-blocking mode
        # last ra/dec call time
        last_position_time = 0
        # last PEC call time
        last_pec_position_time = 0
        # last info call time
        last_info_time = 0

        print("Starting serial bridge...")
        while self.running:
            if not self.pause:
                current_time = time.time()
                
                if not self.quiet:  # in quiet mode, do not disturb traffic
                    # get ra/dec position every 4 seconds
                    if current_time - last_position_time >= 4:
                        self.get_current_position()
                        last_position_time = current_time
                    # get PEC position every 10 seconds
                    if current_time - last_pec_position_time >= 10:
                        self.get_PEC_position()
                        self.get_current_position()
                        last_pec_position_time = current_time
                    # get info every 33 seconds
                    if current_time - last_info_time >= 33:
                        self.get_info()
                        last_info_time = current_time

                # check if btserial open/closed; it will auto open/close serial port
                bt.check_status_bt()

                if bt.in_waiting() > 0:  # Check if there’s any data waiting
                    data = bt.read(bt.in_waiting())  # Read all available bytes
                    if data:                         
                        self.write_scope(data)  # Write it to scope


#                if tcp.in_waiting() > 0:  # Check if there’s any data waiting
#                    data = tcp.read(tcp.in_waiting())  # Read all available bytes
#                    if data:
#                        self.write_scope(data)  # Write it to the other port

                with self.lock:
                    if self._serial_connection.in_waiting > 0:  # Check if there’s any data waiting
                        data = self.read_scope()  # Read all available bytes
                        if data:  # Ensure data was read                        
                            bt.write(data)       # will write if open
#                           tcp.write(data)  # will write if open
                
                # Brief sleep to avoid high CPU usage
                time.sleep(0.05)  # 50ms delay

        print("Stopping serial bridge...")


    def close_connection(self):
        if self._serial_connection and self._serial_connection.is_open:
            self._serial_connection.dtr = False  # Disable DTR to prevent reset
            self._serial_connection.close()
            print("Telescope serial connection closed")
        #self.tcp_serial.close()

    def reset_arduino(self):
        with self.lock:
            # get PEC
            self.get_PEC_position()
            self._serial_connection.dtr = True
            time.sleep(0.5)
            self._serial_connection.dtr = False
            self.close_connection()
            time.sleep(2)
            self.open_serial()
            time.sleep(2)
            self.send_PEC_position(self.current_pecpos())
            self.send_tracking(True)    #now enable tracking

    def reset_usb(self):
        try:
            # Close the connection without resetting
            if self._serial_connection and self._serial_connection.is_open:
                self._serial_connection.dtr = False
                self.close_connection()
            # Use sudo with modprobe commands
            subprocess.run("sudo modprobe -r ch341", shell=True, check=True)
            subprocess.run("sudo modprobe ch341", shell=True, check=True)
            #subprocess.run(["sudo", "modprobe", "-r", "ch341"], check=True)
            #time.sleep(0.5)
            #subprocess.run(["sudo", "modprobe", "ch341"], check=True)
            time.sleep(2)
            self.open_serial()
            print("USB reset successfully")
            return self._serial_connection.is_open
        except subprocess.CalledProcessError as e:
            print(f"Error resetting USB: {e.stderr.decode()}")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False

    def set_quiet(self, quiet):
        self.scope_info["quiet"] = quiet
        self.quiet= quiet

    def send_move(self, direction):
        LXMove(direction).execute(self)

    def send_stop(self, direction=""):
        LXStop(direction).execute(self)

    def send_speed(self, speed):
        LXSpeed(speed).execute(self)

    def send_start_movement_speed(self, ra, dec):
        PTCStartMove(ra,dec).execute(self)

    def send_set_to(self, ra, dec):
        LXSetRa(ra).execute(self)
        LXSetDec(dec).execute(self)
        LXSetTO().execute(self)

    def send_go_to(self, ra, dec):
        LXSetRa(ra).execute(self)
        LXSetDec(dec).execute(self)
        LXSlew().execute(self)
        
    def get_current_position(self):
        ra = LXGetRa().execute(self).decode().rstrip('#')
        dec = LXGetDec().execute(self).decode().rstrip('#')
        self.scope_info["coordinates"] = {"ra": ra, "dec": dec}

    def send_PEC_position(self, position=0):
        try:
            cmd = PTCSetPECPos(position)
            cmd.execute(self)
        except ValueError as ve:
            print(ve)

    def get_PEC_position(self):
        try:
            cmd = PTCGetPECPos()
            cmd.execute(self)
            pos = cmd.response.decode().rstrip("!\n")
        except ValueError:
            pos = 0
        self.scope_info["pec"]["progress"] = pos

    def send_tracking(self, tracking=True):
        try:
            PTCSetTracking(tracking).execute(self)
        except ValueError as ve:
            print(ve)

    def send_pier(self, pier):
        try:
            PTCSetPier(pier).execute(self)
        except ValueError as ve:
            print(ve)

    def send_correction(self, direction, t=0.5):
        LXMove(direction).execute(self)
        time.sleep(t)
        LXStop(direction).execute(self)

    def send_backlash_comp_ra(self, comp):
        PTCSetBacklashRA(comp).execute(self)

    def send_backlash_comp_dec(self, comp):
        PTCSetBacklashDEC(comp).execute(self)

    def send_camera(self, shots, exposure):
        try:
            PTCCameraSetExp(exposure).execute(self)
            PTCCameraSetShots(shots).execute(self)
        except ValueError as ve:
            print(f"{ve}")
            return False

    def get_info(self):
        cmd = PTCInfo()
        cmd.execute(self)
        info = cmd.response.decode()
        try:
            lines = info.strip().split('\n')
            line = 0
            data = {}
            # Software and version
            software_parts = lines[line].split()
            data["software"] = {
                "name": software_parts[0],
                "version": software_parts[1]
            }
            line+=1

            # Memory
            data["memory"] = int(lines[line].split()[1])
            line+=1

            # Uptime
            data["uptime"] = int(lines[line].split()[1])
            line+=1

            # Looptime
            data["looptime"] = int(lines[line].split()[1])
            line+=1

            # tracktime
            data["tracktime"] = int(lines[line].split()[1])
            line+=1

            # RA
            ra = lines[line].split()[1].rstrip('#')
            data["coordinates"] = {"ra": ra}
            line+=1

            # DEC
            dec = lines[line].split()[1].rstrip('#')
            data["coordinates"]["dec"] = dec
            line+=1

            # Pier side
            data["pier"] = lines[line].split()[1]
            line+=1

            # PEC
            pec_parts = lines[line].split()
            if pec_parts[1]=='disabled':
                data["pec"] = {
                    "progress": pec_parts[1],
                    "value": 0
                }
            else:
                data["pec"] = {
                    "progress": pec_parts[1][2:].rstrip('%'),
                    "value": int(pec_parts[2])
                }
            line+=1

            # BC
            bc_parts = lines[line].split()
            if bc_parts[0]=='BC':
                data["bc"] = { "ra": bc_parts[2], "dec": bc_parts[4] }
                line+=1
            else:
                data["bc"] = { "ra": 0, "dec": 0 }

            # Camera
            camera_parts = lines[line].split()
            data["camera"] = {
                "exposure": int(camera_parts[2]),
                "shots": int(camera_parts[4].rstrip(':')),
                "state": camera_parts[5]
            }
            line+=1

            # Tracking
            data["tracking"] = lines[line].split()[1]
            line+=1

            self.scope_info = data
        except:
            print("get info failed to parse")

        self.scope_info["text"]=info
        return info

    def send_pec_table(self, pec_table):
        cmd = PTCSetPEC(pec_table)
        cmd.execute(self)
        return cmd.response.decode()

    def receive_pec_table(self):

        cmd =  PTCGetPEC()
        cmd.execute(self)
        response = cmd.response.decode().rstrip("!\n")
        
        print(f"{response}")

        if not response.startswith("PEC "):
            print(f"Invalid response from Arduino")
            return []

        try:
            # Extract "PEC num_points" and the rest of the data
            parts = response.split(" ", 2)  # Limit split to only the first two spaces
            num_points = int(parts[1])  # Extract number of points
            data_str = parts[2]  # Extract the comma-separated values
        except (IndexError, ValueError):
            print("Error: Invalid PEC header format.")
            return []

        try:
            pec_table = list(map(int, data_str.split(',')))  # Convert to integer list
        except ValueError as ve:
            print(f"Error: Non-integer values found in PEC table. {ve}")
            return []

        if len(pec_table) != num_points * 2:
            print(f"Error: Expected {num_points * 2} values, but received {len(pec_table)}")
            return []

        print(f"Received PEC table with {num_points} points.")
        return pec_table

    def upload_firmware(self, file_path):
        command = f"avrdude -D -c arduino -p m328p -P /dev/ttyUSB0 -b 57600 -U flash:w:{file_path}"
        self.pause = True
        time.sleep(0.1)
        try:
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(result.stdout.decode())
            print(result.stderr.decode())
            print("Firmware uploaded successfully.")
            self.pause = False
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error uploading firmware: {e.stderr.decode()}")
            self.pause = False
            return False
            
    def __del__(self):
        self.close_connection()
        #self.tcp_serial.close()