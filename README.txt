references:
https://github.com/ofrohn/d3-celestial

1. Put files under /root/astro
   Install dependencies, nginx etc with install-depends.sh

2. To enable service:
	Run sudo bash ./install-service.sh. This installs pipitrek.service in
	/etc/systemd/system, reloads systemd, and enables it at boot. It does not
	start it immediately.

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





Pipitrek persistent Wi-Fi mode files

Files in this bundle:
- install-service.sh
- wlan-mode.sh
- pipitreklocal-mode.service
- pipitreklocal-ip.service
- pipitreklocal.conf                 (hostapd systemd drop-in)
- pipitreklocal-dnsmasq.conf         (hotspot DHCP configuration)

IMPORTANT:
1. Keep your existing pipitrek.service in the same repository directory. This
   installer deliberately does not replace its contents with a guessed version.
2. The installer backs up /etc/network/interfaces once to
   /etc/network/interfaces.pipitreklocal-backup, then removes the exact old
   Wi-Fi/NAT stanza that made boot depend on wlan0. The eth0 stanza is retained.
3. The first installation defaults to hotspot. Later runs preserve
   /etc/pipitreklocal-mode.
4. Wi-Fi client mode uses /etc/wpa_supplicant/wpa_supplicant.conf and dhclient.
   Check that this config contains the intended saved network before switching.
5. Run as root from the repository:
      sudo ./install-service.sh
   Then select a mode:
      sudo /usr/local/sbin/wlan-mode.sh hotspot
      sudo /usr/local/sbin/wlan-mode.sh wlan
      sudo /usr/local/sbin/wlan-mode.sh off
6. Each command saves the selected mode for the next boot. If the USB Wi-Fi
   dongle is absent at boot, Ethernet remains independent; the selected Wi-Fi
   mode is logged as not activated.
7. This controller does not automatically re-activate Wi-Fi if the dongle is
   plugged back in while the OS is already running. Run the mode command again.

The hotspot config /etc/hostapd/hostapd.conf is intentionally left untouched
because it contains the locally configured SSID and passphrase.









