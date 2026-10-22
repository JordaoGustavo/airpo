import os
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "airpo"
CONFIG_FILE = CONFIG_DIR / "config.toml"
SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "airpo.sock"

DEFAULT = """\
# MAC of your AirPods (leave empty to auto-detect from paired devices)
mac = ""

# Connect automatically when the case is opened near this machine.
auto_connect = true

# Minimum BLE signal to consider the AirPods "near" (higher = closer).
rssi_threshold = -65

# Seconds the AirPods must be unseen before a new sighting counts as "case opened".
reappear_after = 20

# Only auto-connect if this machine had keyboard/mouse input in the last N seconds
# (0 = ignore). Needs `xprintidle` (X11) or works off logind IdleHint.
max_idle = 120

# Noise mode applied right after connecting: "", "anc", "transparency", "off", "adaptive"
default_noise = ""
"""


@dataclass
class Config:
    mac: str = ""
    auto_connect: bool = True
    rssi_threshold: int = -65
    reappear_after: int = 20
    max_idle: int = 120
    default_noise: str = ""


def load():
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(DEFAULT)
    data = tomllib.loads(CONFIG_FILE.read_text())
    return Config(**{k: v for k, v in data.items() if k in Config.__dataclass_fields__})
