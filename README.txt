1. Put files under /root/astro

2. To enable service:
		copy autoguider.service to /etc/systemd/system 
		run commands: 
			sudo systemctl daemon-reload
			sudo systemctl enable autoguider.service
			

3. Start/Stop service:
		sudo systemctl start autoguider.service
		sudo systemctl stop autoguider.service
		(also in start.sh / stop.sh)
		sudo systemctl status autoguider.service
		
4. Log file is in astro/autoguide.log

5. UVC driver reset
		sudo modprobe -r uvcvideo && sudo modprobe uvcvideo