"""airpo — AirPods on Linux, Mac-style.

  airpo daemon                 run the background service
  airpo tray                   tray icon (battery + controls)
  airpo status                 battery / noise mode
  airpo connect | disconnect | toggle
  airpo anc | transparency | off | adaptive
"""

import json
import socket
import sys

from . import config


def request(**payload):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(30)
    try:
        s.connect(str(config.SOCKET_PATH))
    except OSError:
        sys.exit("airpo daemon is not running (systemctl --user start airpo)")
    s.sendall(json.dumps(payload).encode() + b"\n")
    data = b""
    while chunk := s.recv(4096):
        data += chunk
    return json.loads(data)


def fmt_battery(b):
    if b["status"] == "disconnected":
        return "--"
    return f"{b['level']}%" + (" ⚡" if b["status"] == "charging" else "")


def print_status(st):
    state = "connected here" if st["connected"] else ("nearby" if st["nearby"] else "away")
    print(f"{st.get('model', 'AirPods')} [{st['mac']}]: {state}")
    bat = st["battery"]
    if bat:
        parts = [f"{k.capitalize()}: {fmt_battery(bat[k])}" for k in ("left", "right", "case") if k in bat]
        src = " (via BLE)" if st.get("battery_source") == "ble" else ""
        print("  " + "   ".join(parts) + src)
    if st["noise"]:
        print(f"  Noise: {st['noise']}")
    if st["ear"]:
        print(f"  Ear: {st['ear'][0]} / {st['ear'][1]}")


def main():
    args = sys.argv[1:] or ["status"]
    cmd = args[0]
    if cmd == "daemon":
        from .daemon import main as run
        return run()
    if cmd == "tray":
        from .tray import main as run
        return run()
    if cmd == "status":
        st = request(cmd="status")
        if "--json" in args:
            print(json.dumps(st))
        else:
            print_status(st)
        return
    if cmd in ("connect", "disconnect", "toggle"):
        resp = request(cmd=cmd)
    elif cmd in ("anc", "transparency", "off", "adaptive"):
        resp = request(cmd="noise", mode=cmd)
    else:
        sys.exit(__doc__)
    if not resp.get("ok"):
        sys.exit(resp.get("msg", "failed"))


if __name__ == "__main__":
    main()
