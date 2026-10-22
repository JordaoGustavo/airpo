"""Top-bar indicator (Ubuntu/GNOME AppIndicator): headphone icon + battery label,
with a macOS-like menu for battery, connection and noise modes."""

import threading

import gi

gi.require_version("Gtk", "3.0")
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except (ValueError, ImportError):
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as AppIndicator
    except (ValueError, ImportError):
        raise SystemExit(
            "AppIndicator library not found. Install it with:\n"
            "  sudo apt install gir1.2-ayatanaappindicator3-0.1\n"
            "(on older systems: sudo apt install gir1.2-appindicator3-0.1)"
        ) from None
from gi.repository import GLib, Gtk

from .cli import fmt_battery, request

MODES = [("Cancelamento de Ruído", "anc"), ("Transparência", "transparency"),
         ("Adaptativo", "adaptive"), ("Desligado", "off")]
PARTS = [("left", "Esquerdo"), ("right", "Direito"), ("case", "Estojo")]
ICON_ON = "audio-headphones-symbolic"
ICON_OFF = "audio-headphones"


def safe_request(**payload):
    try:
        return request(**payload)
    except SystemExit:
        return {}


class Tray:
    def __init__(self):
        self.status = {}
        self.updating = False
        self.ind = AppIndicator.Indicator.new(
            "airpo", ICON_OFF, AppIndicator.IndicatorCategory.HARDWARE)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.build_menu()
        self.refresh()
        GLib.timeout_add_seconds(5, self.refresh)

    def build_menu(self):
        menu = Gtk.Menu()
        self.title = Gtk.MenuItem(label="AirPods")
        self.title.set_sensitive(False)
        menu.append(self.title)
        self.battery_items = {}
        for part, name in PARTS:
            item = Gtk.MenuItem(label=f"{name}: --")
            item.set_sensitive(False)
            self.battery_items[part] = (item, name)
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())

        self.connect_item = Gtk.MenuItem(label="Conectar a este computador")
        self.connect_item.connect("activate", lambda _: self.send(cmd="toggle"))
        menu.append(self.connect_item)
        menu.append(Gtk.SeparatorMenuItem())

        self.mode_items = {}
        group = None
        for name, mode in MODES:
            item = Gtk.RadioMenuItem.new_with_label_from_widget(group, name)
            group = item
            item.connect("toggled", self.on_mode, mode)
            self.mode_items[mode] = item
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Sair")
        quit_item.connect("activate", lambda _: Gtk.main_quit())
        menu.append(quit_item)
        menu.show_all()
        self.ind.set_menu(menu)

    def on_mode(self, item, mode):
        if item.get_active() and not self.updating and self.status.get("noise") != mode:
            self.send(cmd="noise", mode=mode)

    def send(self, **payload):
        def work():
            safe_request(**payload)
            GLib.idle_add(self.refresh)
        threading.Thread(target=work, daemon=True).start()

    def refresh(self):
        threading.Thread(target=lambda: GLib.idle_add(self.apply, safe_request(cmd="status")),
                         daemon=True).start()
        return True

    def apply(self, st):
        self.status = st
        self.updating = True
        connected = st.get("connected", False)
        bat = st.get("battery", {})

        # Top-bar label: lowest bud level, like the macOS menu bar widget.
        buds = [bat[p]["level"] for p in ("left", "right")
                if p in bat and bat[p]["status"] != "disconnected"]
        self.ind.set_icon_full(ICON_ON if connected else ICON_OFF, "AirPods")
        self.ind.set_label(f"{min(buds)}%" if buds else "", "100%")

        if not st:
            self.title.set_label("airpo daemon parado")
        else:
            where = "Conectado" if connected else ("Por perto" if st.get("nearby") else "Longe")
            self.title.set_label(f"{st.get('model', 'AirPods')} — {where}")
        for part, (item, name) in self.battery_items.items():
            item.set_label(f"{name}: {fmt_battery(bat[part]) if part in bat else '--'}")
        self.connect_item.set_label("Desconectar" if connected else "Conectar a este computador")
        for mode, item in self.mode_items.items():
            item.set_sensitive(connected)
            if st.get("noise") == mode:
                item.set_active(True)
        self.updating = False
        return False


def main():
    Tray()
    Gtk.main()
