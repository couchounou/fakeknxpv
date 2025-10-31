#!/bin/bash

cd /home/pi/fakeknxpv/ || exit 1
/usr/bin/git pull
systemctl restart fakeknxpv