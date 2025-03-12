import queue
import time

# Virtual serial port simulation
class VirtualSerialPort:
    def __init__(self):
        # Thread-safe queues for the virtual serial port
        self.rx_queue = queue.Queue()  # Incoming data (from physical ports)
        self.tx_queue = queue.Queue()  # Outgoing data (to physical ports)
        self.is_open = False
        self.timeout = 0  # Non-blocking mode
    
    def open(self):
        self.is_open = True
    
    def close(self):
        self.is_open = False

    def read_rx(self, size=1):
        return self.read(self.rx_queue, size)
    def read_tx(self, size=1):
        return self.read(self.tx_queue, size)
    
    def read(self, q, size=1):
        # Read up to 'size' bytes from rx_queue, blocking if needed
        data = bytearray()
        while len(data) < size:
            try:
                byte = q.get(timeout=self.timeout)
                data.extend(byte)
            except queue.Empty:
                break  # Return what we have if no more data
        return bytes(data[:size])  # Return requested size or less

    def readline_rx(self, timeout=None):
        return self.readline(self.rx_queue, timeout)

    def readline_tx(self, timeout=None):
        return self.readline(self.tx_queue, timeout)

    def readline(self, q, timeout=None):
        # Read until a newline (\n) is found or timeout occurs.
        if not self.is_open:
            return None
        line = bytearray()
        start_time = time.time()
        while True:
            if timeout is not None and (time.time() - start_time) >= timeout:
                return bytes(line)
            try:
                byte = q.get(timeout=timeout)
                line.append(byte[0])
                if byte == b'\n':
                    return bytes(line)
            except queue.Empty:
                if timeout is None or (time.time() - start_time) < timeout:
                    continue
                return bytes(line)
        
    def write_rx(self, data):
        return self.write(self.rx_queue, data)

    def write_tx(self, data):
        return self.write(self.tx_queue, data)

    def write(self, q, data):
        """Write each byte of the data to the tx_queue separately."""
        if not self.is_open:
            return 0
        
        if not isinstance(data, bytes):
            raise TypeError("Data must be bytes")
        bytes_written = 0
        for byte in data:
            q.put(bytes([byte]))  # Put each byte as a single-byte bytes object
            bytes_written += 1
        return bytes_written

    def in_waiting_rx(self):
        # Return number of bytes in rx_queue
        if self.is_open:
            return self.rx_queue.qsize()
        else:
            return 0

    def in_waiting_tx(self):
        # Return number of bytes in tx_queue
        if self.is_open:
            return self.tx_queue.qsize()        
        else:
            return 0
