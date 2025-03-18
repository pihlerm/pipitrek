
from threading import RLock
import serial
import time
import subprocess
import json
from comm.virtual_port import VirtualSerialPort
from comm.btserial import BTSerial
from comm.tcpserial import TCPSerial

class Telescope:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Telescope, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._virtual_port = VirtualSerialPort()
            self._virtual_port.open()
            self.open_serial()
            self.pause = False
            self.scope_info = None
            self.bt_serial = BTSerial()
            self.tcp_serial = TCPSerial()
            self.tcp_serial.open()  
            self.lock = RLock()  # Thread lock for serial operations
            time.sleep(2) # wait arduino
            self.get_info()

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
        data =  self.try_on_scope(lambda: self._serial_connection.readline())
        #print(f"scope readline: {data}")
        return data

    def run_serial_bridge(self):
        self.running = True
        
        virt = self._virtual_port
        bt = self.bt_serial
        tcp = self.tcp_serial

        self._serial_connection.timeout = 0  # Non-blocking mode
        print("Starting serial bridge...")
        while self.running:
            if not self.pause:
                # check if btserial open/closed; it will auto open/close serial port
                bt.check_status_bt()

                if bt.in_waiting() > 0:  # Check if there’s any data waiting
                    data = bt.read(bt.in_waiting())  # Read all available bytes
                    if data:                         
                        self.write_scope(data)  # Write it to scope

                if virt.in_waiting_tx() > 0:  # Check if there’s any data waiting
                    data = virt.read_tx(virt.in_waiting_tx())  # Read all available bytes
                    if data:
                        self.write_scope(data)  # Write it to the other port

                if tcp.in_waiting() > 0:  # Check if there’s any data waiting
                    data = tcp.read(tcp.in_waiting())  # Read all available bytes
                    if data:
                        self.write_scope(data)  # Write it to the other port

                with self.lock:
                    if self._serial_connection.in_waiting > 0:  # Check if there’s any data waiting
                        data = self.read_scope()  # Read all available bytes
                        if data:  # Ensure data was read                        
                            bt.write(data)       # will write if open
                            tcp.write(data)  # will write if open
                            virt.write_rx(data)  # will write if open
                
                # Brief sleep to avoid high CPU usage
                time.sleep(0.01)  # 10ms delay

        print("Stopping serial bridge...")


    def close_connection(self):
        if self._serial_connection and self._serial_connection.is_open:
            self._serial_connection.dtr = False  # Disable DTR to prevent reset
            self._serial_connection.close()
            print("Telescope serial connection closed")
        self.tcp_serial.close()

    def reset_arduino(self):
        with self.lock:
            self._serial_connection.dtr = True
            time.sleep(0.5)
            self._serial_connection.dtr = False
            self.close_connection()
            time.sleep(2)
            self.open_serial()

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


    def send_command(self, command):
        self._virtual_port.write_tx(command.encode())

    def read_response(self, timeout=10):
        return self._virtual_port.readline_rx(timeout=timeout).decode().strip()

    def read_until_timeout(self, timeout=1):       
        return self._virtual_port.readline_rx(timeout = timeout).decode().strip()

    def send_move(self, direction):
        self.send_command(f":M{direction}#")

    def send_stop(self, direction=""):
        self.send_command(f":Q{direction}#")

    def send_tracking(self, tracking=True):
        if tracking:
            self.send_command("!TE#")
        else:
            self.send_command("!TD#")

    
    def send_direct_command(self, command):
        self.write_scope(command.encode())

    def read_direct_response(self):
        self._serial_connection.timeout = 1
        data =  self.readline_scope().decode().strip()
        self._serial_connection.timeout = 0
        return data

    def clear_direct_inbuffer(self):
        self._serial_connection.timeout = 1
        while self._serial_connection.in_waiting:
            self._serial_connection.read(1)             
        self._serial_connection.timeout = 0


    def send_pier(self, pier):
        if pier not in ['W', 'E']:
            return False
        self.send_command(f"!M{pier}#")
        return True

    def send_correction(self, direction, t=0.5):
        self.send_command(f":M{direction}#")
        time.sleep(t)
        self.send_command(f":Q{direction}#")

    def get_info(self):
        with self.lock:
            self.clear_direct_inbuffer()
            self.send_direct_command(f"!IN#")
            info = ""
            resp ="X"
            while resp != "":
                resp = self.read_direct_response()
                info += resp + "\n"

            lines = info.strip().split('\n')
            data = {}
            # Line 1: Software and version
            software_parts = lines[0].split()
            data["software"] = {
                "name": software_parts[0],
                "version": software_parts[1]
            }
            # Line 2: Memory
            data["memory"] = int(lines[1].split()[1])
            # Line 3: Uptime
            data["uptime"] = int(lines[2].split()[1])
            # Line 4: RA
            ra = lines[3].split()[1].rstrip('#')
            data["coordinates"] = {"ra": ra}
            # Line 5: DEC
            dec = lines[4].split()[1].rstrip('#').replace('*', ':')
            data["coordinates"]["dec"] = dec
            # Line 6: Pier side
            data["pier"] = lines[5].split()[1]
            # Line 7: PEC
            pec_parts = lines[6].split()
            data["pec"] = {
                "progress": pec_parts[1].lstrip('@'),
                "value": int(pec_parts[2])
            }
            # Line 8: Camera
            camera_parts = lines[7].split()
            data["camera"] = {
                "exposure": int(camera_parts[2]),
                "shots": int(camera_parts[4].rstrip(':')),
                "state": camera_parts[5]
            }
            # Line 9: Tracking
            data["tracking"] = lines[8].split()[1]
            self.scope_info = data
            return info

    def send_pec_table(self, pec_table):

        self.read_until_timeout(0.1) # clear in buffer
        self.send_command(f"!PI#")

        num_points = len(pec_table) // 2
        self.send_command(f"PEC {num_points} ")
        
        data_str = ",".join(map(str, pec_table)) + "\n"
        self.send_command(data_str)
        
        print("PEC table sent.")
        data = self.read_until_timeout(0.3)
        return data

    def receive_pec_table(self):

        self.read_until_timeout(0.1) # clear in buffer
        self.send_command("!PO#")  # Request PEC table from Arduino

        # Read first response line, expecting "PEC num_points 1,2,3,...,4"
        response = self.read_response()
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
        except ValueError:
            print("Error: Non-integer values found in PEC table.")
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
        self.tcp_serial.close()