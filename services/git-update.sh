#!/bin/bash

cd /home/pi/fakeknxpv/ || exit 1
/usr/bin/git pull
sudo cp /home/pi/fakeknxpv/services/git-update.sh /home/pi/
sudo chmod +x /home/pi/git-update.sh
sudo systemctl restart fakeknxpv