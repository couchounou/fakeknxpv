#!/usr/bin/env bash
set -Eeuo pipefail

readonly REPO_URL="https://github.com/couchounou/fakeknxpv.git"
readonly REPO_DIR="/home/pi/fakeknxpv"
readonly VENV_DIR="/home/pi/venv"
readonly BOOT_CONFIG_DIR="/boot/firmware"

if [[ "$(id -un)" != "pi" ]]; then
    echo "Run this installer as the pi user, not with sudo." >&2
    exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
    echo "sudo is required to install system packages and services." >&2
    exit 1
fi

sudo apt-get update
sudo apt-get install -y git python3-venv

if [[ -d "$REPO_DIR" ]]; then
    if [[ ! -d "$REPO_DIR/.git" ]]; then
        echo "$REPO_DIR exists but is not a Git repository; refusing to overwrite it." >&2
        exit 1
    fi
else
    git clone "$REPO_URL" "$REPO_DIR"
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -e "$REPO_DIR"

if [[ -d "$BOOT_CONFIG_DIR" ]]; then
    config_path="$BOOT_CONFIG_DIR/cyclic_send_toknx_pv_data.cfg"
    if [[ ! -e "$config_path" ]]; then
        sudo install -m 0644 \
            "$REPO_DIR/fake_knx_pv/cyclic_send_toknx_pv_data.cfg.exemple" \
            "$config_path"
        echo "Created $config_path from the example. Edit it before relying on live data."
    else
        echo "Keeping existing configuration: $config_path"
    fi
else
    config_path="$REPO_DIR/fake_knx_pv/cyclic_send_toknx_pv_data.cfg"
    echo "Using repository configuration: $config_path"
fi

install -m 0755 "$REPO_DIR/services/git-update.sh" /home/pi/git-update.sh
sudo install -m 0644 \
    "$REPO_DIR/services/gitupdate.service" \
    /etc/systemd/system/gitupdate.service
sudo install -m 0644 \
    "$REPO_DIR/services/fakeknxpv.service" \
    /etc/systemd/system/fakeknxpv.service

sudo systemctl daemon-reload
sudo systemctl enable --now gitupdate.service
sudo systemctl enable --now fakeknxpv.service

echo "Installation complete."
echo "Configuration: $config_path"
echo "Check service status with: sudo systemctl status fakeknxpv.service"
echo "View service logs with: sudo journalctl -u fakeknxpv.service -f"
