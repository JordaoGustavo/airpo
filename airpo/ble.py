"""Parse Apple "proximity pairing" BLE advertisements (manufacturer 0x004C, type 0x07).

These are broadcast by the AirPods even when they are connected to another
device (e.g. the Mac), which lets us show battery and detect "case opened"
without holding a connection. AirPods use a random BLE address, so they are
matched by model + signal strength rather than by MAC.
"""

from dataclasses import dataclass

APPLE_COMPANY_ID = 0x004C
PROXIMITY_PAIRING = 0x07

MODELS = {
    0x0220: "AirPods 1",
    0x0F20: "AirPods 2",
    0x1320: "AirPods 3",
    0x0E20: "AirPods Pro",
    0x1420: "AirPods Pro 2",
    0x2420: "AirPods Pro 2 (USB-C)",
    0x0A20: "AirPods Max",
}


@dataclass
class Proximity:
    model: int
    model_name: str
    left: int | None
    right: int | None
    case: int | None
    left_charging: bool
    right_charging: bool
    case_charging: bool
    lid_open: bool
    rssi: int


def _level(nibble):
    if nibble == 0xF:
        return None
    return min(nibble, 10) * 10


def parse(data: bytes, rssi: int) -> Proximity | None:
    """`data` is the manufacturer payload for company 0x004C (without the company id)."""
    if len(data) < 9 or data[0] != PROXIMITY_PAIRING:
        return None
    model = (data[3] << 8) | data[4]
    status = data[5]
    pods = data[6]
    flags, case = data[7] >> 4, data[7] & 0xF
    # Bit 0x20 tells which bud is the "primary"; nibbles are swapped accordingly.
    flipped = not (status & 0x20)
    hi, lo = pods >> 4, pods & 0xF
    left, right = (hi, lo) if flipped else (lo, hi)
    return Proximity(
        model=model,
        model_name=MODELS.get(model, f"Apple 0x{model:04x}"),
        left=_level(left),
        right=_level(right),
        case=_level(case),
        left_charging=bool(flags & (0b10 if flipped else 0b01)),
        right_charging=bool(flags & (0b01 if flipped else 0b10)),
        case_charging=bool(flags & 0b100),
        lid_open=not (data[8] & 0x08) if len(data) > 8 else False,
        rssi=rssi,
    )
