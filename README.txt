references:
https://github.com/ofrohn/d3-celestial

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
		
6. Guider camera (IMX291):
  - Disable autosuspend ?
  - echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="0c45", ATTRS{idProduct}=="6366", RUN+="/bin/sh -c \"echo -1 > /sys/bus/usb/devices/%k/power/autosuspend_delay_ms; echo on > /sys/bus/usb/devices/%k/power/control\""' | sudo tee /etc/udev/rules.d/99-usb-camera-autosuspend.rules
  - to achieve high gain, turn on autoexposure for several seconds, then off
   
   
  - v4l2-ctl --list-ctrls -d /dev/video0
  - v4l2-ctl --list-ctrls-menus -d /dev/video0 
  - v4l2-ctl -V -d /dev/video0
  - v4l2-ctl -D -d /dev/video0
  - v4l2-ctl --list-formats -d /dev/video0
  - v4l2-ctl --list-formats-ext
  - v4l2-ctl -d /dev/video0 -c exposure_time_absolute=1000  
  - time v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=20 --stream-to=/dev/null
  
  
  
7. ASTROMETRY.NET plate solver installation:

	1. sudo apt install astrometry.net
	2. download index files (https://data.astrometry.net/) - for guide cam images, 4100 series is excellent
	3. put index files in a dir, eg /root/astro/astrometry
	4. edit /etc/astrometry.cfg  , set path to index files line "add_path /root/astro/astrometry"
	5. solve-field your_image.png --scale-units arcminwidth --scale-low 50 --scale-high 110 --downsample 2 --cpulimit 60 --no-plots --overwrite

8. HTTPS server certificates are created using cert/gencert.sh or cert/gencerts.bat
	1. self signed cert is in certs/cert.pem and certs/key.pem
	
	
9. Moving dome sound https://www.youtube.com/watch?v=Hb6h99cfBqA&ab_channel=AlexandreSanterne





