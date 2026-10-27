#!/usr/bin/env bash
# Installs airpo for the current user and enables the background service + tray.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install --user --break-system-packages . 2>/dev/null || python3 -m pip install --user .
BIN="$(python3 -m site --user-base)/bin/airpo"

mkdir -p ~/.config/systemd/user ~/.config/autostart
sed "s|@BIN@|$BIN|" systemd/airpo.service > ~/.config/systemd/user/airpo.service
sed "s|@BIN@|$BIN|" systemd/airpo-tray.desktop > ~/.config/autostart/airpo-tray.desktop

# Run bluetoothd with experimental features so the daemon can scan passively
# (a nonstop active scan knocks BLE keyboards/mice off on many adapters).
BTD="$(systemctl cat bluetooth.service 2>/dev/null | sed -n 's/^ExecStart=\([^ ]*bluetoothd\).*/\1/p' | tail -1)"
DROPIN=/etc/systemd/system/bluetooth.service.d/airpo-experimental.conf
if [ -n "$BTD" ] && ! systemctl cat bluetooth.service | grep -q "^ExecStart=.*bluetoothd.* \(-E\|--experimental\)"; then
    echo "Enabling BlueZ experimental features (needs sudo; Bluetooth restarts briefly)"
    sudo mkdir -p "$(dirname "$DROPIN")"
    printf '[Service]\nExecStart=\nExecStart=%s -E\n' "$BTD" | sudo tee "$DROPIN" >/dev/null
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    sleep 2
fi

systemctl --user daemon-reload
systemctl --user enable airpo.service
systemctl --user restart airpo.service
pkill -f "airpo tray" || true
nohup "$BIN" tray >/dev/null 2>&1 &

echo "airpo installed. Config: ~/.config/airpo/config.toml"
echo "Try: airpo status"
