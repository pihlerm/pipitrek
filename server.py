import http.server
import ssl
import os
import urllib.parse

# Directory to serve
os.chdir(os.path.dirname(__file__))

basepath = './static/upload/'

# Custom handler to support PUT requests
class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_PUT(self):
        """Handle PUT requests by saving the uploaded file."""
        # Get the file path from the request URL
        path = urllib.parse.unquote(self.path)
        # Sanitize path to prevent directory traversal
        filename = os.path.basename(path.strip('/'))
        
        if not filename:
            self.send_response(400)  # Bad Request
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'No filename specified')
            return

        # Get content length
        content_length = int(self.headers.get('Content-Length', 0))
        
        filename = basepath+filename
        # Read the uploaded data
        try:
            with open(filename, 'wb') as f:
                f.write(self.rfile.read(content_length))
            
            # Respond with success
            self.send_response(201)  # Created
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f'File {filename} uploaded successfully'.encode())
        except Exception as e:
            self.send_response(500)  # Internal Server Error
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f'Error uploading file: {str(e)}'.encode())

# Set up server
server_address = ('0.0.0.0', 8443)
httpd = http.server.HTTPServer(server_address, CustomHTTPRequestHandler)

# Wrap with SSL
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile='cert/cert.pem', keyfile='cert/key.pem')
context.minimum_version = ssl.TLSVersion.TLSv1_2
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

# Start server
print("Serving HTTPS on https://192.168.1.16:8443")
httpd.serve_forever()