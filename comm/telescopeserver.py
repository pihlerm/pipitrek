import socket
import struct
import time
import threading
import math

# TCP server settings
TCP_HOST = '0.0.0.0'
TCP_PORT = 10000

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

class TelescopeSimulator:
    def __init__(self):
        self.ra_deg = 0.0  # Degrees
        self.dec_deg = 0.0
        self.running = False
        self.sock = None
        self.slewing = False
        self.target_ra = None
        self.target_dec = None
        self.sidereal_rate = 15.041 / 3600  # Degrees per second
        self.conn_active = threading.Event()

    def get_position(self):
        if not self.slewing:
            self.ra_deg = (self.ra_deg + self.sidereal_rate * 0.5) % 360
        elif self.target_ra is not None and self.target_dec is not None:
            slew_speed = 1.0
            ra_diff = (self.target_ra - self.ra_deg + 180) % 360 - 180
            dec_diff = self.target_dec - self.dec_deg
            if abs(ra_diff) > slew_speed:
                self.ra_deg += slew_speed * (1 if ra_diff > 0 else -1)
            else:
                self.ra_deg = self.target_ra
            if abs(dec_diff) > slew_speed:
                self.dec_deg += slew_speed * (1 if dec_diff > 0 else -1)
            else:
                self.dec_deg = self.target_dec
            if self.ra_deg == self.target_ra and self.dec_deg == self.target_dec:
                self.slewing = False
        return self.ra_deg, self.dec_deg

    def send_position(self, conn):
        self.conn_active.set()
        while self.running and self.conn_active.is_set():
            ra_deg, dec_deg = self.get_position()
            ra_int = deg_to_stellarium_ra(ra_deg)
            dec_int = deg_to_stellarium_dec(dec_deg)
            
            # Type 0 message: 24 bytes 
            msg = self.pack(ra_int, dec_int, time.time())
            try:
                conn.sendall(msg)
                #print(f"Sent position: RA={deg_to_lx200_ra(self.ra_deg)}, Dec={deg_to_lx200_dec(self.dec_deg)}, Slewing={self.slewing}")
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
            print(f"size: {size}, msg_type: {msg_type}, ra_int: {ra_int}, dec_int: {dec_int}")
            ra_deg = stellarium_to_deg(ra_int, is_ra=True)
            dec_deg = stellarium_to_deg(dec_int, is_ra=False)
            self.target_ra = ra_deg
            self.target_dec = dec_deg
            self.slewing = True
            print(f"Goto command received: RA={deg_to_lx200_ra(ra_deg)}, Dec={deg_to_lx200_dec(dec_deg)}")

    def handle_sync(self, data):
        size, msg_type, ra_int, dec_int = self.unpack(data)
        if msg_type == 2 and size == 16:
            self.ra_deg = stellarium_to_deg(ra_int, is_ra=True)
            self.dec_deg = stellarium_to_deg(dec_int, is_ra=False)
            self.slewing = False
            self.target_ra = None
            self.target_dec = None
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

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((TCP_HOST, TCP_PORT))
        self.sock.listen(1)
        print(f"Listening on {TCP_HOST}:{TCP_PORT}")
        self.running = True

        while True:
            conn, addr = self.sock.accept()
            print(f"Connected by {addr}")
            self.conn_active.set()
            send_thread = threading.Thread(target=self.send_position, args=(conn,), daemon=True)
            send_thread.start()
            try:
                while self.running:
                    data = conn.recv(20)
                    if not data:
                        break
                    self.handle_client_message(data)
            except ConnectionError:
                print(f"Disconnected from {addr}")
            finally:
                self.conn_active.clear()
                conn.close()

    def stop(self):
        self.running = False
        self.sock.close()

if __name__ == "__main__":
    sim = TelescopeSimulator()
    try:
        sim.start()
    except KeyboardInterrupt:
        sim.stop()