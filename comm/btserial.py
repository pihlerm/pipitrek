import gpiod
import serial


class BTSerial:

    def __init__(self):       
        self.bt_state_pin = 22
        self.bt_chip = gpiod.Chip('gpiochip0')
        self.bt_line = self.bt_chip.get_line(self.bt_state_pin)
        self.bt_line.request(consumer="hc05-state", type=gpiod.LINE_REQ_DIR_IN) # Set as input
        self.last_state = None  # Track previous state to detect changes
        self.is_open = False
        self._serial_connection = None

    def open(self):
        self.open_serial()
        self.is_open = self._serial_connection.is_open
    
    def close(self):
        self.close_connection()
        self.is_open = False

    def open_serial(self):
        self._serial_connection = serial.Serial(
            port='/dev/ttyAML1',
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        )
        self._serial_connection.flush()  # Clear the buffer
        self._serial_connection.timeout = 0  # Non-blocking mode
        print("Bluetooth serial connection initialized")

    def check_status_bt(self):
        current_state = self.bt_line.get_value()
        if current_state != self.last_state:
            if current_state == 1:  # HIGH = Connected
                print("HC-05 Connected - Opening serial port")
                self.open()
            else:  # LOW = Disconnected
                print("HC-05 Disconnected - Closing serial port")
                self.close()
            self.last_state = current_state
                
    def close_connection(self):
        if self._serial_connection and self._serial_connection.is_open:
            self._serial_connection.close()
            print("Bluetooth serial connection closed")

    def read(self,size=1):
        #and self._serial_connection.in_waiting > 0
        if self._serial_connection and self._serial_connection.is_open:
            return self._serial_connection.read(size)
        else:
            return b''  # Return empty bytes
        
    def write(self, data): 
        if self._serial_connection and self._serial_connection.is_open:
            return self._serial_connection.write(data)
        else:
            return 0

    def readline(self):
        if self._serial_connection and self._serial_connection.is_open:
            return self._serial_connection.readline()
        else:
            return b''  # Return empty bytes
    
    def in_waiting(self):
        if self._serial_connection and self._serial_connection.is_open:
            return self._serial_connection.in_waiting
        else:
            return 0


    def __del__(self):
        self.bt_chip.close()  # Release GPIO resources