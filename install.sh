#!/usr/bin/env bash
# Installs airpo for the current user and enables the background service + tray.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install --user --break-system-packages . 2>/dev/null || python3 -m pip install --user .
BIN="$(python3 -m site --user-base)/bin/airpo"

mkdir -p ~/.config/systemd/user ~/.config/autostart
sed "s|@BIN@|$BIN|" systemd/airpo.service > ~/.config/systemd/user/airpo.service
sed "s|@BIN@|$BIN|" systemd/airpo-tray.desktop > ~/.config/autostart/airpo-tray.desktop

systemctl --user daemon-reload
systemctl --user enable --now airpo.service
nohup "$BIN" tray >/dev/null 2>&1 &

echo "airpo installed. Config: ~/.config/airpo/config.toml"
echo "Try: airpo status"
