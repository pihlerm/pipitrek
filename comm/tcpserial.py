import socket
import threading
import time

class TCPSerial:
    def __init__(self):
        self.is_open = False
        self._server_socket = None  # Listening socket
        self._client_socket = None  # Connected client socket
        self._buffer = b''  # Buffer for readline
        self._lock = threading.Lock()  # Thread safety for socket access
        self._running = False  # Control listener thread

        # TCP configuration
        self.host = '0.0.0.0'  # Listen on all interfaces
        self.port = 5123       # Port to listen on


    def _listen_loop(self):
        """Background thread to listen for and manage TCP connections."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(1)
        print(f"TCP server listening on {self.host}:{self.port}")

        self._running = True
        while self._running:
            try:
                client_socket, addr = self._server_socket.accept()
                with self._lock:
                    if self._client_socket is not None:
                        self._client_socket.close()  # Close any existing connection
                    self._client_socket = client_socket
                    self._client_socket.setblocking(False)  # Non-blocking mode
                    self.is_open = True
                    self._buffer = b''  # Clear buffer
                print(f"TCP connection established with {addr}")
            except OSError as e:
                if self._running:  # Only print if not shutting down
                    print(f"Error accepting connection: {e}")
            except Exception as e:
                print(f"Unexpected error in listen loop: {e}")
            time.sleep(0.1)  # Brief delay to avoid tight loop on errors

    def open(self):
        """Start or ensure the TCP listener is running."""
        if not self._running:
            self._running = True
            self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._listen_thread.start()
        # No immediate action needed; listener thread handles connection

    def close(self):
        """Close the TCP connection and stop the listener."""
        self._running = False
        with self._lock:
            if self._client_socket is not None:
                self._client_socket.close()
                self._client_socket = None
            if self._server_socket is not None:
                self._server_socket.close()
                self._server_socket = None
            self.is_open = False
            self._buffer = b''  # Clear buffer on close
        print("TCP server and connection closed")

    def client_disconnected(self):
        print("TCP client disconnected")
        self._client_socket = None
        self.is_open = False

    def read(self, size=1):
        with self._lock:
            if not self.is_open or self._client_socket is None:
                return b''

            data = b''
            remaining = size

            # Use buffer first if available
            if self._buffer:
                if len(self._buffer) >= size:
                    data = self._buffer[:size]
                    self._buffer = self._buffer[size:]
                    return data  # Early return if buffer is sufficient
                else:
                    data = self._buffer
                    self._buffer = b''
                    remaining = size - len(data)

            # Read remaining bytes from socket if needed
            if remaining > 0:
                try:
                    socket_data = self._client_socket.recv(remaining)
                    if socket_data:
                        data += socket_data
                    elif socket_data == b'':  # Client disconnected gracefully
                        self.client_disconnected()
                except BlockingIOError:  # No data available
                    pass
                except (OSError, ConnectionResetError):  # Client disconnected
                    self.client_disconnected()

            return data
                    
    def write(self, data):
        with self._lock:
            if self._client_socket is not None and self.is_open:
                try:
                    bytes_sent = self._client_socket.send(data)
                    return bytes_sent
                except (BlockingIOError, BrokenPipeError, ConnectionResetError):
                    self.client_disconnected()
                    return 0
        return 0

    def readline(self):
        with self._lock:
            if self._client_socket is not None and self.is_open:
                try:
                    while True:
                        chunk = self._client_socket.recv(1024)
                        if not chunk:  # Connection closed
                            self.client_disconnected()
                            break
                        self._buffer += chunk
                        newline_idx = self._buffer.find(b'\n')
                        if newline_idx != -1:
                            line = self._buffer[:newline_idx + 1]
                            self._buffer = self._buffer[newline_idx + 1:]
                            return line
                except BlockingIOError:  # No data available
                    pass
            # Check buffer for a complete line
            newline_idx = self._buffer.find(b'\n')
            if newline_idx != -1:
                line = self._buffer[:newline_idx + 1]
                self._buffer = self._buffer[newline_idx + 1:]
                return line
        return b''

    def in_waiting(self):
        with self._lock:
            if self.is_open and self._client_socket is not None:
                try:
                    data = self._client_socket.recv(1024, socket.MSG_PEEK)
                    return len(data) + len(self._buffer)
                except BlockingIOError:
                    return len(self._buffer)
                except (OSError, ConnectionResetError):
                    self.client_disconnected()
                    return 0
        return 0

    def __del__(self):
        self.close()