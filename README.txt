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
		
4. Log file is in astro/pipitrek/autoguide.log

5. UVC driver reset
		sudo modprobe -r uvcvideo && sudo modprobe uvcvideo