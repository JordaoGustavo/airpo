"""System tray icon: battery in the tooltip/menu, connect toggle and noise modes."""

import threading
import time

import pystray
from PIL import Image, ImageDraw

from .cli import fmt_battery, request

MODES = [("Noise Cancellation", "anc"), ("Transparency", "transparency"),
         ("Adaptive", "adaptive"), ("Off", "off")]


def icon_image(connected):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (255, 255, 255, 255) if connected else (140, 140, 140, 255)
    for x in (14, 38):  # two stylised buds
        d.ellipse((x, 10, x + 14, 30), fill=color)
        d.rounded_rectangle((x + 4, 24, x + 10, 54), radius=3, fill=color)
    return img


class Tray:
    def __init__(self):
        self.status = {}
        self.icon = pystray.Icon("airpo", icon_image(False), "AirPods", menu=self.menu())

    def safe_status(self):
        try:
            return request(cmd="status")
        except SystemExit:
            return {}

    def label(self, part):
        b = self.status.get("battery", {}).get(part)
        return lambda _: f"{part.capitalize()}: {fmt_battery(b) if b else '--'}"

    def menu(self):
        mode_items = [
            pystray.MenuItem(name, self.setter(mode), radio=True,
                             checked=lambda _, m=mode: self.status.get("noise") == m,
                             enabled=lambda _: self.status.get("connected", False))
            for name, mode in MODES
        ]
        return pystray.Menu(
            pystray.MenuItem(self.label("left"), None, enabled=False),
            pystray.MenuItem(self.label("right"), None, enabled=False),
            pystray.MenuItem(self.label("case"), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _: "Disconnect" if self.status.get("connected") else "Connect to this computer",
                lambda: self.send(cmd="toggle"), default=True),
            pystray.Menu.SEPARATOR,
            *mode_items,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self.icon.stop()),
        )

    def setter(self, mode):
        return lambda: self.send(cmd="noise", mode=mode)

    def send(self, **payload):
        threading.Thread(target=lambda: (self.safe_send(payload), self.update()), daemon=True).start()

    def safe_send(self, payload):
        try:
            request(**payload)
        except SystemExit:
            pass

    def update(self):
        self.status = self.safe_status()
        bat = self.status.get("battery", {})
        tip = "  ".join(f"{k[0].upper()} {fmt_battery(v)}" for k, v in bat.items()) or "AirPods"
        self.icon.icon = icon_image(self.status.get("connected", False))
        self.icon.title = tip
        self.icon.update_menu()

    def loop(self):
        while True:
            self.update()
            time.sleep(5)

    def run(self):
        threading.Thread(target=self.loop, daemon=True).start()
        self.icon.run()


def main():
    Tray().run()
