#!/bin/bash

cd /home/pi/ || exit 1
sudo apt-get install -y git
git clone https://github.com/couchounou/fakeknxpv.git
sudo git config --global --add safe.directory /home/pi/fakeknxpv
sudo apt-get install -y python3-pip
python3 -m venv ./venv
source venv/bin/activate
pip install /home/pi/fakeknxpv/dist/fake_knx_pv-0.2.4-py3-none-any.whl
deactivate
sudo cp /home/pi/fakeknxpv/services/git-update.sh /home/pi/
sudo cp /home/pi/fakeknxpv/services/gitupdate.service /etc/systemd/system/
sudo cp /home/pi/fakeknxpv/services/fakeknxpv.service /etc/systemd/system/
sudo chmod +x /home/pi/git-update.sh
sudo cp ./fakeknxpv/fake_knx_pv/cyclic_send_toknx_pv_data.cfg /boot/firmware/
sudo chmod +r /boot/firmware/index_*.*
sudo systemctl daemon-reload
sudo systemctl enable gitupdate.service
sudo systemctl start gitupdate.service
sudo systemctl enable fakeknxpv.service
sudo systemctl start fakeknxpv.service
echo "Installation complete."

sudo apt clean
sudo apt autoclean
sudo apt autoremove -y
sudo rm -rf /tmp/* /var/tmp/*
sudo rm -rf /var/cache/apt/archives/*
sudo journalctl --rotate
sudo journalctl --vacuum-time=1d
