#!/bin/bash

cd /home/pi/fakeknxpv/ || exit 1
/usr/bin/git pull
sudo chmod +x /home/pi/fakeknxpv/fake_knx_pv/services/git-update.sh
sudo systemctl restart fakeknxpv