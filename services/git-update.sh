#!/bin/bash

cd /home/pi/fakeknxpv/ || exit 1
/usr/bin/git pull
echo "Updating git-update.sh script and restarting service..."
sudo systemctl restart fakeknxpv
sudo cp /home/pi/fakeknxpv/services/git-update.sh /home/pi/
sudo chmod +x /home/pi/git-update.sh
