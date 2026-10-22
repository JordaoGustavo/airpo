"""Top-bar icon, speaking the StatusNotifierItem + dbusmenu protocols directly
over D-Bus (same as Slack/Electron), so no GTK/AppIndicator libraries are
needed. Shows a headphone icon with the battery label, like macOS."""

import asyncio
import os

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.service import PropertyAccess, ServiceInterface, dbus_property, method, signal

from .cli import fmt_battery, request

MODES = [("Cancelamento de Ruído", "anc"), ("Transparência", "transparency"),
         ("Adaptativo", "adaptive"), ("Desligado", "off")]
PARTS = [("left", "Esquerdo"), ("right", "Direito"), ("case", "Estojo")]
ICON_ON = "audio-headphones-symbolic"
ICON_OFF = "audio-headphones"
MENU_PATH = "/MenuBar"
ITEM_PATH = "/StatusNotifierItem"


def safe_request(**payload):
    try:
        return request(**payload)
    except SystemExit:
        return {}


class StatusNotifierItem(ServiceInterface):
    def __init__(self, tray):
        super().__init__("org.kde.StatusNotifierItem")
        self.tray = tray
        self.icon = ICON_OFF
        self.label = ""

    @dbus_property(access=PropertyAccess.READ)
    def Category(self) -> "s":
        return "Hardware"

    @dbus_property(access=PropertyAccess.READ)
    def Id(self) -> "s":
        return "airpo"

    @dbus_property(access=PropertyAccess.READ)
    def Title(self) -> "s":
        return "AirPods"

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return "Active"

    @dbus_property(access=PropertyAccess.READ)
    def IconName(self) -> "s":
        return self.icon

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def ItemIsMenu(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Menu(self) -> "o":
        return MENU_PATH

    @dbus_property(access=PropertyAccess.READ)
    def ToolTip(self) -> "(sa(iiay)ss)":
        return ["", [], "AirPods", self.label]

    # Ubuntu's AppIndicator extension shows this text next to the icon.
    @dbus_property(access=PropertyAccess.READ)
    def XAyatanaLabel(self) -> "s":
        return self.label

    @dbus_property(access=PropertyAccess.READ)
    def XAyatanaLabelGuide(self) -> "s":
        return "100%"

    @method()
    def Activate(self, x: "i", y: "i"):
        self.tray.send(cmd="toggle")

    @method()
    def SecondaryActivate(self, x: "i", y: "i"):
        pass

    @method()
    def ContextMenu(self, x: "i", y: "i"):
        pass

    @method()
    def Scroll(self, delta: "i", orientation: "s"):
        pass

    @signal()
    def NewIcon(self):
        pass

    @signal()
    def NewToolTip(self):
        pass

    @signal()
    def XAyatanaNewLabel(self) -> "ss":
        return [self.label, "100%"]


class DBusMenu(ServiceInterface):
    def __init__(self, tray):
        super().__init__("com.canonical.dbusmenu")
        self.tray = tray
        self.revision = 1
        self.items = []  # [(id, props, callback)]

    def set_items(self, items):
        self.items = items
        self.revision += 1
        self.LayoutUpdated()

    def _layout(self):
        children = [Variant("(ia{sv}av)", [i, props, []]) for i, props, _ in self.items]
        return [0, {"children-display": Variant("s", "submenu")}, children]

    @dbus_property(access=PropertyAccess.READ)
    def Version(self) -> "u":
        return 3

    @dbus_property(access=PropertyAccess.READ)
    def TextDirection(self) -> "s":
        return "ltr"

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return "normal"

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "as":
        return []

    @method()
    def GetLayout(self, parent_id: "i", depth: "i", props: "as") -> "u(ia{sv}av)":
        return [self.revision, self._layout()]

    @method()
    def GetGroupProperties(self, ids: "ai", props: "as") -> "a(ia{sv})":
        return [[i, p] for i, p, _ in self.items if not ids or i in ids]

    @method()
    def GetProperty(self, id: "i", name: "s") -> "v":
        for i, p, _ in self.items:
            if i == id and name in p:
                return p[name]
        return Variant("s", "")

    @method()
    def Event(self, id: "i", event_id: "s", data: "v", timestamp: "u"):
        if event_id == "clicked":
            for i, _, callback in self.items:
                if i == id and callback:
                    callback()

    @method()
    def EventGroup(self, events: "a(isvu)") -> "ai":
        for id, event_id, data, ts in events:
            self.Event(id, event_id, data, ts)
        return []

    @method()
    def AboutToShow(self, id: "i") -> "b":
        return False

    @method()
    def AboutToShowGroup(self, ids: "ai") -> "aiai":
        return [[], []]

    @signal()
    def LayoutUpdated(self) -> "ui":
        return [self.revision, 0]

    @signal()
    def ItemsPropertiesUpdated(self) -> "a(ia{sv})a(ias)":
        return [[], []]


def text(label, enabled=True):
    return {"label": Variant("s", label), "enabled": Variant("b", enabled)}


SEPARATOR = {"type": Variant("s", "separator")}


class Tray:
    def __init__(self):
        self.item = StatusNotifierItem(self)
        self.menu = DBusMenu(self)
        self.status = None
        self.loop = None

    def send(self, **payload):
        async def work():
            await asyncio.to_thread(safe_request, **payload)
            await self.refresh()
        self.loop.create_task(work())

    def build_items(self, st):
        connected = st.get("connected", False)
        bat = st.get("battery", {})
        if not st:
            title = "airpo daemon parado"
        else:
            where = "Conectado" if connected else ("Por perto" if st.get("nearby") else "Longe")
            title = f"{st.get('model', 'AirPods')} — {where}"
        items = [(1, text(title, False), None)]
        for n, (part, name) in enumerate(PARTS, start=2):
            level = fmt_battery(bat[part]) if part in bat else "--"
            items.append((n, text(f"{name}: {level}", False), None))
        items.append((10, SEPARATOR, None))
        items.append((11, text("Desconectar" if connected else "Conectar a este computador"),
                      lambda: self.send(cmd="toggle")))
        items.append((12, SEPARATOR, None))
        for n, (name, mode) in enumerate(MODES, start=20):
            props = text(name, connected)
            props["toggle-type"] = Variant("s", "radio")
            props["toggle-state"] = Variant("i", 1 if st.get("noise") == mode else 0)
            items.append((n, props, lambda m=mode: self.send(cmd="noise", mode=m)))
        items.append((30, SEPARATOR, None))
        items.append((31, text("Sair"), lambda: self.loop.stop()))
        return items

    async def refresh(self):
        st = await asyncio.to_thread(safe_request, cmd="status")
        if st == self.status:
            return
        self.status = st
        bat = st.get("battery", {})
        buds = [bat[p]["level"] for p in ("left", "right")
                if p in bat and bat[p]["status"] != "disconnected"]
        icon = ICON_ON if st.get("connected") else ICON_OFF
        label = f"{min(buds)}%" if buds else ""
        if icon != self.item.icon:
            self.item.icon = icon
            self.item.NewIcon()
        if label != self.item.label:
            self.item.label = label
            self.item.XAyatanaNewLabel()
            self.item.NewToolTip()
        self.menu.set_items(self.build_items(st))

    async def run(self):
        self.loop = asyncio.get_running_loop()
        bus = await MessageBus().connect()
        bus.export(ITEM_PATH, self.item)
        bus.export(MENU_PATH, self.menu)
        name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        await bus.request_name(name)
        await self.refresh()

        intro = await bus.introspect("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher")
        watcher = bus.get_proxy_object("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", intro)
        await watcher.get_interface("org.kde.StatusNotifierWatcher").call_register_status_notifier_item(name)

        while True:
            await asyncio.sleep(5)
            await self.refresh()


def main():
    try:
        asyncio.run(Tray().run())
    except RuntimeError:  # loop.stop() from "Sair"
        pass
