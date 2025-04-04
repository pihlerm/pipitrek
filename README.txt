1. Put files under /root/astro

2. To enable service:
		copy pipitrek.service to /etc/systemd/system 
		run commands: 
			sudo systemctl daemon-reload
			sudo systemctl enable pipitrek.service
			

3. Start/Stop service:
		sudo systemctl start pipitrek.service
		sudo systemctl stop pipitrek.service
		(also in start.sh / stop.sh)
		sudo systemctl status pipitrek.service
		
4. Log file is in astro/pipitrek/pipitrek.log

5. UVC driver reset
		sudo modprobe -r uvcvideo && sudo modprobe uvcvideo
		
6. Disable autosuspend for camera (IMX291):
   - echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="0c45", ATTRS{idProduct}=="6366", RUN+="/bin/sh -c \"echo -1 > /sys/bus/usb/devices/%k/power/autosuspend_delay_ms; echo on > /sys/bus/usb/devices/%k/power/control\""' | sudo tee /etc/udev/rules.d/99-usb-camera-autosuspend.rules
   
  - v4l2-ctl --list-ctrls -d /dev/video0
  - v4l2-ctl --list-ctrls-menus -d /dev/video0
  
  - v4l2-ctl -V -d /dev/video0
  - v4l2-ctl -D -d /dev/video0
  - v4l2-ctl --list-formats -d /dev/video0
  - v4l2-ctl --list-formats-ext
  - v4l2-ctl -d /dev/video0 -c exposure_time_absolute=1000
  - v4l2-ctl -d /dev/video0 -c white_balance_automatic=1
  - v4l2-ctl -d /dev/video0 -c white_balance_temperature=4500
  
  - time v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=20 --stream-to=/dev/null