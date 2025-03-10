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
	python3-requests


# Configure Nginx for HTTP proxy
echo "Setting up Nginx..."
rm -f /etc/nginx/sites-enabled/default
cat << 'EOF' > /etc/nginx/sites-available/autoguider
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
    }
}
EOF
ln -sf /etc/nginx/sites-available/autoguider /etc/nginx/sites-enabled/
systemctl restart nginx

echo "Installation complete! Please transfer webcam.py and autoguider.py via WinSCP and run them with:"
echo "  python3 ~/webcam.py &  # Start webcam server in background"
echo "  python3 ~/autoguider.py  # Run autoguider"