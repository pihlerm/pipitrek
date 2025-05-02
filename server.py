import http.server
import ssl
import os

# Directory to serve
os.chdir(os.path.dirname(__file__))

# Set up server
server_address = ('0.0.0.0', 8443)
httpd = http.server.HTTPServer(server_address, http.server.SimpleHTTPRequestHandler)

# Wrap with SSL
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile='cert/cert.pem', keyfile='cert/key.pem')
context.minimum_version = ssl.TLSVersion.TLSv1_2
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

# Start server
print("Serving HTTPS on https://192.168.1.5:8443")
httpd.serve_forever()