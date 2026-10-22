"""Background service: watches BLE, manages the connection and AAP session,
and answers JSON commands on a unix socket (used by the CLI and tray)."""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time

from bleak import BleakScanner

from . import aap, ble, bluez, config

log = logging.getLogger("airpo")


def idle_seconds():
    if shutil.which("xprintidle") and os.environ.get("DISPLAY"):
        try:
            return int(subprocess.check_output(["xprintidle"], text=True)) / 1000
        except (subprocess.CalledProcessError, ValueError):
            pass
    try:
        sid = os.environ.get("XDG_SESSION_ID", "auto")
        out = subprocess.check_output(
            ["loginctl", "show-session", sid, "-p", "IdleHint", "-p", "LockedHint"], text=True)
        if "=yes" in out:
            return float("inf")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return 0


class Daemon:
    def __init__(self, cfg):
        self.cfg = cfg
        self.mac = cfg.mac or self._detect_mac()
        self.connected = False
        self.proximity = None
        self.last_seen = 0.0
        self.last_auto_attempt = 0.0
        self.aap = aap.AAPClient(self.mac) if self.mac else None
        self._busy = asyncio.Lock()

    @staticmethod
    def _detect_mac():
        found = bluez.paired_airpods()
        if not found:
            log.warning("no paired AirPods found; pair them first (see README)")
            return ""
        log.info("using %s (%s)", found[0][1], found[0][0])
        return found[0][0]

    # ---- BLE -------------------------------------------------------------

    def on_advertisement(self, device, adv):
        payload = adv.manufacturer_data.get(ble.APPLE_COMPANY_ID)
        if not payload:
            return
        prox = ble.parse(payload, adv.rssi)
        if not prox or adv.rssi < self.cfg.rssi_threshold:
            return
        now = time.monotonic()
        reappeared = now - self.last_seen > self.cfg.reappear_after
        self.last_seen = now
        self.proximity = prox
        if reappeared and not self.connected:
            log.info("AirPods appeared nearby (%s, rssi %d)", prox.model_name, prox.rssi)
            asyncio.get_running_loop().create_task(self.maybe_auto_connect())

    async def maybe_auto_connect(self):
        cfg = self.cfg
        if not (cfg.auto_connect and self.mac) or self.connected:
            return
        if time.monotonic() - self.last_auto_attempt < 30:
            return
        if cfg.max_idle and await asyncio.to_thread(idle_seconds) > cfg.max_idle:
            log.info("machine idle/locked, not stealing the AirPods")
            return
        self.last_auto_attempt = time.monotonic()
        await self.connect()

    # ---- connection ------------------------------------------------------

    async def connect(self):
        async with self._busy:
            ok, out = await asyncio.to_thread(bluez.connect, self.mac)
            log.info("connect: %s", "ok" if ok else out)
        if ok:
            await self.refresh()
        return ok, out

    async def disconnect(self):
        async with self._busy:
            self.aap.close()
            return await asyncio.to_thread(bluez.disconnect, self.mac)

    async def refresh(self):
        was = self.connected
        self.connected = await asyncio.to_thread(bluez.is_connected, self.mac)
        if self.connected and not self.aap.connected:
            try:
                await asyncio.to_thread(self.aap.open)
                log.info("AAP session open")
                if not was and self.cfg.default_noise:
                    await asyncio.sleep(1)
                    self.aap.set_noise_mode(self.cfg.default_noise)
            except OSError as e:
                log.debug("AAP open failed: %s", e)
        elif not self.connected and self.aap.connected:
            self.aap.close()

    async def poll(self):
        while True:
            if not self.mac:  # paired after the daemon started
                self.mac = await asyncio.to_thread(self._detect_mac)
                if self.mac:
                    self.aap = aap.AAPClient(self.mac)
            if self.mac:
                await self.refresh()
            await asyncio.sleep(3)

    # ---- status / IPC ----------------------------------------------------

    def status(self):
        st = {"mac": self.mac, "connected": self.connected, "battery": {}, "noise": None,
              "ear": None, "nearby": time.monotonic() - self.last_seen < 10}
        if self.aap and self.aap.connected:
            s = self.aap.state
            st["battery"] = {k: {"level": b.level, "status": b.status} for k, b in s.battery.items()}
            st["noise"] = s.noise
            st["ear"] = s.ear
        if not st["battery"] and self.proximity and st["nearby"]:
            p = self.proximity
            st["model"] = p.model_name
            for part, level, chg in (("left", p.left, p.left_charging),
                                     ("right", p.right, p.right_charging),
                                     ("case", p.case, p.case_charging)):
                st["battery"][part] = {
                    "level": level if level is not None else 0,
                    "status": "disconnected" if level is None
                    else "charging" if chg else "discharging",
                }
            st["battery_source"] = "ble"
        return st

    async def handle(self, reader, writer):
        try:
            req = json.loads(await reader.readline() or b"{}")
            cmd = req.get("cmd")
            if cmd == "status":
                resp = self.status()
            elif cmd == "connect":
                ok, out = await self.connect()
                resp = {"ok": ok, "msg": out}
            elif cmd == "disconnect":
                ok, out = await self.disconnect()
                resp = {"ok": ok, "msg": out}
            elif cmd == "toggle":
                ok, out = await (self.disconnect() if self.connected else self.connect())
                resp = {"ok": ok, "msg": out}
            elif cmd == "noise":
                self.aap.set_noise_mode(req["mode"])
                resp = {"ok": True}
            else:
                resp = {"ok": False, "msg": f"unknown command {cmd!r}"}
        except Exception as e:  # report errors to the client instead of dying
            resp = {"ok": False, "msg": str(e)}
        writer.write(json.dumps(resp).encode() + b"\n")
        await writer.drain()
        writer.close()

    async def run(self):
        sock = config.SOCKET_PATH
        if sock.exists():
            sock.unlink()
        server = await asyncio.start_unix_server(self.handle, path=str(sock))
        scanner = BleakScanner(self.on_advertisement)
        await scanner.start()
        log.info("airpo daemon running (socket %s)", sock)
        async with server:
            await self.poll()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(Daemon(config.load()).run())
