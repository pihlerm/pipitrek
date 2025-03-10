
import serial

class Telescope:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Telescope, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._serial_connection = serial.Serial(
                port='/dev/ttyUSB0',
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            print("Telescope serial connection initialized")

    def send_command(self, command):
        if self._serial_connection.is_open:
            self._serial_connection.write(command.encode())
        else:
            raise ConnectionError("Serial connection is not open")

    def close_connection(self):
        if self._serial_connection.is_open:
            self._serial_connection.close()
            print("Telescope serial connection closed")

    def send_move(self, direction):
        self.send_command(f":M{direction}#")

    def send_stop(self, direction=""):
        self.send_command(f":Q{direction}#")

    def __del__(self):
        self.close_connection()