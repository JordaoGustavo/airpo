"""Apple Accessory Protocol (AAP) client over L2CAP PSM 0x1001.

Packet formats come from the community reverse-engineering effort
(LibrePods / OpenPods / MagicPods). AirPods only answer on this channel
while the classic Bluetooth (ACL) link to this machine is up.
"""

import socket
import threading
from dataclasses import dataclass, field

PSM = 0x1001

HANDSHAKE = bytes.fromhex("00000400010002000000000000000000")
SET_FEATURES = bytes.fromhex("040004004d00ff0000000000000000")
REQUEST_NOTIFICATIONS = bytes.fromhex("040004000f00ffffffff")

HEADER = bytes.fromhex("04000400")
OP_BATTERY = 0x04
OP_EAR = 0x06
OP_CONTROL = 0x09
CTRL_NOISE = 0x0D

NOISE_MODES = {"off": 1, "anc": 2, "transparency": 3, "adaptive": 4}
NOISE_NAMES = {v: k for k, v in NOISE_MODES.items()}

BATTERY_PARTS = {0x01: "single", 0x02: "right", 0x04: "left", 0x08: "case"}
BATTERY_STATUS = {0x01: "charging", 0x02: "discharging", 0x04: "disconnected"}
EAR_STATES = {0: "in-ear", 1: "out", 2: "in-case"}


@dataclass
class Battery:
    level: int
    status: str

    def __str__(self):
        if self.status == "disconnected":
            return "--"
        return f"{self.level}%" + (" ⚡" if self.status == "charging" else "")


@dataclass
class AAPState:
    battery: dict = field(default_factory=dict)   # part -> Battery
    noise: str | None = None
    ear: tuple | None = None                       # (primary, secondary)


class AAPClient:
    """Keeps an AAP session open and parses notifications into AAPState."""

    def __init__(self, address, on_change=None):
        self.address = address
        self.on_change = on_change or (lambda state: None)
        self.state = AAPState()
        self._sock = None
        self._thread = None
        self._lock = threading.Lock()

    @property
    def connected(self):
        return self._sock is not None

    def open(self):
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        sock.settimeout(5)
        sock.connect((self.address, PSM))
        sock.settimeout(None)
        for packet in (HANDSHAKE, SET_FEATURES, REQUEST_NOTIFICATIONS):
            sock.send(packet)
        self._sock = sock
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def close(self):
        sock, self._sock = self._sock, None
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def set_noise_mode(self, mode):
        if mode not in NOISE_MODES:
            raise ValueError(f"unknown mode {mode!r}, use one of {list(NOISE_MODES)}")
        packet = HEADER + bytes([OP_CONTROL, 0x00, CTRL_NOISE, NOISE_MODES[mode], 0, 0, 0])
        with self._lock:
            if not self._sock:
                raise ConnectionError("AAP session not open")
            self._sock.send(packet)

    def _read_loop(self):
        while self._sock:
            try:
                data = self._sock.recv(1024)
            except OSError:
                break
            if not data:
                break
            if self._parse(data):
                self.on_change(self.state)
        self.close()
        self.on_change(self.state)

    def _parse(self, data):
        if len(data) < 7 or data[:4] != HEADER:
            return False
        opcode = data[4]
        if opcode == OP_BATTERY:
            count = data[6]
            battery = {}
            for i in range(count):
                off = 7 + i * 5
                if off + 4 > len(data):
                    break
                part = BATTERY_PARTS.get(data[off], f"0x{data[off]:02x}")
                battery[part] = Battery(data[off + 2], BATTERY_STATUS.get(data[off + 3], "unknown"))
            self.state.battery = battery
            return True
        if opcode == OP_CONTROL and len(data) >= 8 and data[6] == CTRL_NOISE:
            self.state.noise = NOISE_NAMES.get(data[7], f"0x{data[7]:02x}")
            return True
        if opcode == OP_EAR and len(data) >= 8:
            self.state.ear = (EAR_STATES.get(data[6], "?"), EAR_STATES.get(data[7], "?"))
            return True
        return False
