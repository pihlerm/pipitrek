import socket
import struct
import time
import threading
import math
from telescope import Telescope

# RA/Dec conversion helpers
def deg_to_stellarium_ra(deg):
    rad = math.radians(deg)
    return int(rad * (0x80000000 / math.pi)) & 0xFFFFFFFF  # Unsigned 32-bit

def deg_to_stellarium_dec(deg):
    rad = math.radians(deg)
    return int(rad * (0x80000000 / math.pi))  # Signed 32-bit

def stellarium_to_deg(ra_or_dec, is_ra=True):
    rad = ra_or_dec * (math.pi / 0x80000000)
    deg = math.degrees(rad)
    if is_ra:
        return deg % 360
    return max(min(deg, 90), -90)

def deg_to_lx200_ra(deg):
    ra_hours = deg / 15
    h = int(ra_hours)
    m = int((ra_hours - h) * 60)
    s = int(((ra_hours - h) * 60 - m) * 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def deg_to_lx200_dec(deg):
    sign = '+' if deg >= 0 else '-'
    deg_abs = abs(deg)
    d = int(deg_abs)
    m = int((deg_abs - d) * 60)
    s = int(((deg_abs - d) * 60 - m) * 60)
    return f"{sign}{d:02d}*{m:02d}:{s:02d}"

def lx200_to_ra_deg(ra_str):
    """Convert LX200 RA string (HH:MM:SS) to degrees."""
    try:
        h, m, s = map(int, ra_str.split(':'))
        return h * 15 + m * 15 / 60 + s * 15 / 3600
    except ValueError:
        raise ValueError(f"Invalid RA format: {ra_str}")

def lx200_to_dec_deg(dec_str):
    """Convert LX200 DEC string (+DD*MM:SS or -DD*MM:SS) to degrees."""
    try:
        sign = 1 if dec_str[0] == '+' else -1
        d, m, s = map(int, dec_str[1:].replace('*', ':').split(':'))
        return sign * (d + m / 60 + s / 3600)
    except ValueError:
        raise ValueError(f"Invalid DEC format: {dec_str}")

class ExponentialBuffer:
    def __init__(self, data: bytes):
        self.buffer = bytearray(data)

    def read_double_exponential(self) -> int:
        value = 0
        for i in range(8):
            value += self.buffer[i] << (i * 8)
        return value
    
    def write_double_exponential(self, value: int):
        for i in range(8):
            self.buffer[i] = (value >> (i * 8)) & 0xFF

    def get_bytes(self) -> bytes:
        return bytes(self.buffer)

class TelescopeServer:
    def __init__(self):
        self._running = False
        self.slewing = False
        self.conn_active = threading.Event()
        self.is_open = False
        self._server_socket = None  # Listening socket
        self._client_socket = None  # Connected client socket
        self._send_thread = None
        self._listen_thread = None

        # TCP configuration
        self.host = '0.0.0.0'  # Listen on all interfaces
        self.port = 10000      # Port to listen on

        self.slew_request = None


    def send_position(self, conn):
        self.conn_active.set()
        telescope = Telescope()
        while self._running and self.conn_active.is_set():
            ra = telescope.scope_info["coordinates"]["ra"]
            dec = telescope.scope_info["coordinates"]["dec"]
            ra_deg = lx200_to_ra_deg(ra)
            dec_deg = lx200_to_dec_deg(dec)
            ra_int = deg_to_stellarium_ra(ra_deg)
            dec_int = deg_to_stellarium_dec(dec_deg)

            # Type 0 message: 24 bytes 
            msg = self.pack(ra_int, dec_int, time.time())
            try:
                conn.sendall(msg)
                # print(f"Sent position: RA={deg_to_lx200_ra(ra_deg)}, Dec={deg_to_lx200_dec(dec_deg)}")
            except (ConnectionError, OSError) as e:
                print(f"Send error: {e}")
                break
            time.sleep(0.5)

            

    def pack(self, ra, dec, time):
        
        buffer_size = 24
        obuffer =bytearray(buffer_size)  
        tmbuf = ExponentialBuffer(bytearray(8))  
        tmbuf.write_double_exponential(int(time * 1e6))           # Microseconds

        # Write data into the buffer
        obuffer[0:2] = struct.pack('<H', buffer_size)  # Size
        obuffer[2:4] = struct.pack('<H', 0)            # Reserved
        obuffer[4:12] = tmbuf.get_bytes()              # Timestamp
        obuffer[12:16] = struct.pack('<I', ra)  # RA integer
        obuffer[16:20] = struct.pack('<i', dec)  # DEC integer
        obuffer[20:24] = struct.pack('<I', 0)  # Reserved
        return obuffer

    def unpack(self, raw):
        # Read values from buffer
        length = struct.unpack_from('<H', raw, 0)[0]
        type_ = struct.unpack_from('<H', raw, 2)[0]
        tmb = ExponentialBuffer(raw[4:12])       
        time = tmb.read_double_exponential()
        ra_int = struct.unpack_from('<I', raw, 12)[0]
        dec_int = struct.unpack_from('<i', raw, 16)[0]
        return length, type_, ra_int, dec_int


    def handle_goto(self, data):
        size, msg_type, ra_int, dec_int = self.unpack(data)
        if msg_type == 0:
            #print(f"size: {size}, msg_type: {msg_type}, ra_int: {ra_int}, dec_int: {dec_int}")
            ra_deg = stellarium_to_deg(ra_int, is_ra=True)
            dec_deg = stellarium_to_deg(dec_int, is_ra=False)
            print(f"Goto command received: RA={deg_to_lx200_ra(ra_deg)}, Dec={deg_to_lx200_dec(dec_deg)}")
            self.slew_request = (deg_to_lx200_ra(ra_deg),deg_to_lx200_dec(dec_deg))

    def handle_sync(self, data):
        size, msg_type, ra_int, dec_int = self.unpack(data)
        if msg_type == 2 and size == 16:
            ra_deg = stellarium_to_deg(ra_int, is_ra=True)
            dec_deg = stellarium_to_deg(dec_int, is_ra=False)
            print(f"Sync command received: RA={deg_to_lx200_ra(self.ra_deg)}, Dec={deg_to_lx200_dec(self.dec_deg)}")

    def handle_client_message(self, data):
        if len(data) < 8:
            print(f"Invalid message: {data}")
            return
        size, msg_type = struct.unpack('<HH', data[:4])
        if size != len(data):
            print(f"Message size mismatch: expected {size}, got {len(data)}")
            return
        if msg_type == 0:
            self.handle_goto(data)
        elif msg_type == 2:
            self.handle_sync(data)
        else:
            print(f"Unknown message type: {msg_type}")

    def _listen_loop(self):
        """Background thread to listen for and manage TCP connections."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(1)
        self._server_socket.settimeout(1)  # Set a timeout for the accept() call
        print(f"TCP server listening on {self.host}:{self.port}")

        while self._running:
            try:
                conn, addr = self._server_socket.accept()
                print(f"Connected by {addr}")
                conn.settimeout(1)  # Set a timeout for the recv() call

                if self._client_socket is not None:
                    self._client_socket.close()  # Close any existing connection

                self.conn_active.set()
                self._client_socket = conn
                self._send_thread = threading.Thread(target=self.send_position, args=(self._client_socket,), daemon=True)
                self._send_thread.start()

                try:
                    while self._running:
                        try:
                            data = self._client_socket.recv(20)
                            if not data:
                                break
                            self.handle_client_message(data)
                        except socket.timeout:
                            continue  # Timeout reached, check self._running
                except ConnectionError:
                    print(f"Disconnected from {addr}")
                finally:
                    self.conn_active.clear()
                    if self._client_socket is not None:
                        self._client_socket.close()
            except socket.timeout:
                continue  # Timeout reached, check self._running
            except OSError as e:
                print(f"Socket error: {e}")
                break
            time.sleep(0.1)  # Brief delay to avoid tight loop on errors


    def start(self):
        """Start or ensure the TCP listener is running."""
        if not self._running:
            self._running = True
            self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._listen_thread.start()
        # No immediate action needed; listener thread handles connection

    def stop(self):
        """Close the TCP connection and stop the listener."""
        self._running = False
        if self._server_socket is not None:
            self._server_socket.close()
            self._server_socket = None
        self.conn_active.clear()
        
        # Wait for the listener thread to stop
        if self._listen_thread is not None:
            self._listen_thread.join(timeout=10)
            if self._listen_thread.is_alive():
                print("Warning: _listen_thread did not stop in time")

        # Wait for the send thread to stop
        if self._send_thread is not None:
            self._send_thread.join(timeout=10)
            if self._send_thread.is_alive():
                print("Warning: _send_thread did not stop in time")

        print("TelescopeServer and connection closed")
