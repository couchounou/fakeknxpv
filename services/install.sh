#!/bin/bash

sudo cp ./git-update.sh /home/pi/
sudo cp ./gitupdate.service /etc/systemd/system/
sudo cp ./fakeknxpv.service /etc/systemd/system/
sudo chmod +x /home/pi/git-update.sh
sudo systemctl daemon-reload
sudo systemctl enable gitupdate.service
sudo systemctl start gitupdate.service
sudo systemctl enable fakeknxpv.service
sudo systemctl start fakeknxpv.service
echo "Installation complete."
