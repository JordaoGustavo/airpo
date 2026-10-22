"""Thin wrappers around bluetoothctl and PipeWire/PulseAudio tools."""

import re
import shutil
import subprocess


def _run(*args, timeout=15):
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 1, ""
    return out.returncode, out.stdout + out.stderr


def paired_airpods():
    """[(mac, name)] of paired devices whose name looks like AirPods."""
    code, out = _run("bluetoothctl", "devices", "Paired")
    if code != 0 or "Device " not in out:  # BlueZ < 5.65 (e.g. Ubuntu 22.04)
        _, out = _run("bluetoothctl", "paired-devices")
    found = re.findall(r"Device ([0-9A-F:]{17}) (.+)", out)
    return [(mac, name) for mac, name in found if "airpods" in name.lower()]


def is_connected(mac):
    _, out = _run("bluetoothctl", "info", mac)
    return "Connected: yes" in out


def connect(mac):
    _run("bluetoothctl", "trust", mac)
    code, out = _run("bluetoothctl", "connect", mac, timeout=20)
    ok = code == 0 and "successful" in out.lower()
    if ok:
        make_default_sink(mac)
    return ok, out.strip()


def disconnect(mac):
    code, out = _run("bluetoothctl", "disconnect", mac)
    return code == 0, out.strip()


def make_default_sink(mac):
    """Route audio to the AirPods (A2DP) as soon as they connect."""
    if not shutil.which("pactl"):
        return
    card = "bluez_card." + mac.replace(":", "_")
    _run("pactl", "set-card-profile", card, "a2dp-sink")
    _, sinks = _run("pactl", "list", "short", "sinks")
    for line in sinks.splitlines():
        name = line.split("\t")[1] if "\t" in line else ""
        if mac.replace(":", "_") in name:
            _run("pactl", "set-default-sink", name)
            return
