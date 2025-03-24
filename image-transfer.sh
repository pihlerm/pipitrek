#!/bin/bash
echo "Plug in USB cable, then press Enter"
read
DEVICE=$(lsblk -l -o NAME,VENDOR | grep "Sony" | awk '{print $1}' | head -1)  # Get sda
if [ -z "$DEVICE" ]; then
    echo "A580 not detected! Check USB."
    exit 1
fi
PARTITION="${DEVICE}1"  # Append 1 for sda1
if [ ! -b "/dev/$PARTITION" ]; then
    echo "Partition /dev/$PARTITION not found!"
    exit 1
fi
sudo mount /dev/"$PARTITION" /mnt/a580
cp /mnt/a580/DCIM/101MSDCF/* ~/astro/images/
sudo umount /mnt/a580
echo "Images transferred. Unplug USB now."