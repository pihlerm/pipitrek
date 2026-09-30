#!/bin/bash

# Exit on any error
set -e

# Update and upgrade system
echo "Updating and upgrading DietPi..."
apt update && apt upgrade -y

# Install base dependencies for webcam and autoguider
echo "Installing base system packages..."

apt install -y \
    python3 \
    python3-pip \
    python3-dev \
    git \
    build-essential \
    libatlas-base-dev \
    libopenblas-dev \
    nginx \
	python3-serial \
	python3-opencv \
	python3-flask \
	python3-requests \
	gpiod \
	libgpiod2 \
	python3-libgpiod
	
pip3 install flask flask-sock --break-system-packages

# Configure Nginx to serve static assets directly and reverse-proxy everything else
# (including websockets) to the Flask/werkzeug backend on 8443.
# Serving /static/ via nginx instead of Flask's dev server avoids assets randomly failing
# to load: the Python backend's own CPU-bound threads (camera capture, autoguider loop,
# telescope serial polling) can starve werkzeug's request threads of the GIL, occasionally
# stalling/timing out concurrent CSS/JS/font requests. nginx serves static files itself,
# so page loads no longer race the backend's workload.
echo "Setting up Nginx..."
rm -f /etc/nginx/sites-enabled/default
cat << 'EOF' > /etc/nginx/sites-available/autoguider
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /root/astro/pipitrek/cert/cert.pem;
    ssl_certificate_key /root/astro/pipitrek/cert/key.pem;

    location /static/ {
        alias /root/astro/pipitrek/static/;
        expires 1h;
        access_log off;
    }

    location = /favicon.ico {
        alias /root/astro/pipitrek/static/favicon.png;
        access_log off;
    }

    location / {
        proxy_pass https://127.0.0.1:8443;
        proxy_ssl_verify off;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
    }
}

server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}
EOF
ln -sf /etc/nginx/sites-available/autoguider /etc/nginx/sites-enabled/
systemctl restart nginx

echo "Installation complete! Start the service with:"
echo "  sudo systemctl start pipitrek.service"