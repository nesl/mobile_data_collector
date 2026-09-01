#!/usr/bin/env python3
"""Assign stable, human-friendly device IDs over MQTT."""

import argparse
import json
import os
import re
import sqlite3
import time
from urllib.request import Request, urlopen

import paho.mqtt.client as mqtt

REQUEST_TOPIC = "ucla/ce_registry/request"
RESPONSE_PREFIX = "ucla/ce_registry/response/"


class RegistryStore:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS devices (install_id TEXT PRIMARY KEY, device_id TEXT UNIQUE NOT NULL, last_seen REAL NOT NULL)")
        self.db.commit()

    def assign(self, install_id: str, preferred_id: str = "") -> str:
        preferred_id = re.sub(r"[^A-Za-z0-9_-]", "-", preferred_id.strip())[:40]
        row = self.db.execute("SELECT device_id FROM devices WHERE install_id=?", (install_id,)).fetchone()
        current = row[0] if row else None
        candidate = preferred_id or current
        if candidate:
            owner = self.db.execute("SELECT install_id FROM devices WHERE device_id=?", (candidate,)).fetchone()
            if owner and owner[0] != install_id:
                if preferred_id:
                    raise ValueError(f"requested device name {candidate!r} is already assigned")
                candidate = None
        if not candidate:
            number = 1
            while self.db.execute("SELECT 1 FROM devices WHERE device_id=?", (f"phone-{number}",)).fetchone():
                number += 1
            candidate = f"phone-{number}"
        self.db.execute(
            "INSERT INTO devices VALUES (?, ?, ?) ON CONFLICT(install_id) DO UPDATE SET device_id=excluded.device_id, last_seen=excluded.last_seen",
            (install_id, candidate, time.time()),
        )
        self.db.commit()
        return candidate


def notify_visualization(url: str, payload: dict):
    if not url:
        return
    try:
        request = Request(url.rstrip("/") + "/api/registry", json.dumps(payload).encode(), {"Content-Type": "application/json"})
        urlopen(request, timeout=2).read()
    except OSError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--database", default=os.getenv("REGISTRY_DB", "registry.db"))
    parser.add_argument(
        "--visualization-url",
        default=os.getenv("CE_VISUALIZATION_URL", "http://localhost:5000"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    host, port = args.host, args.port
    store = RegistryStore(args.database)
    visualization = args.visualization_url
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(client, _userdata, _flags, reason_code, _properties):
        if reason_code != 0:
            raise RuntimeError(f"MQTT connection failed: {reason_code}")
        client.subscribe(REQUEST_TOPIC)
        print(f"Device registry listening on {host}:{port}/{REQUEST_TOPIC}")

    def on_message(client, _userdata, message):
        try:
            request = json.loads(message.payload)
            install_id = str(request["install_id"]).strip()
            if not install_id:
                return
            payload = {"install_id": install_id, "device_id": store.assign(install_id, str(request.get("preferred_id", ""))), "last_seen": time.time()}
            client.publish(RESPONSE_PREFIX + install_id, json.dumps(payload), qos=1, retain=True)
            notify_visualization(visualization, payload)
            print(json.dumps(payload))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            print(f"Ignored invalid registration: {error}")

    client.on_connect, client.on_message = on_connect, on_message
    client.connect(host, port, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
