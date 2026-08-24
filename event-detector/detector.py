#!/usr/bin/env python3
"""Minimal two-stage complex-event detector for the mobile collector."""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass

import paho.mqtt.client as mqtt


def labels_from_payload(payload: bytes) -> tuple[str, list[str]]:
    text = payload.decode("utf-8")
    if not text.startswith("detection::"):
        return "unknown", []

    bundle = json.loads(text[len("detection::"):])
    labels: list[str] = []
    for result in bundle.get("detectionResults", []):
        labels.extend(
            box["clsName"]
            for box in result.get("bboxes", [])
            if isinstance(box.get("clsName"), str)
        )
    for result in bundle.get("audioResults", []):
        for event in result.get("events", []):
            if isinstance(event, dict):
                label = event.get("first")
            elif isinstance(event, list) and event:
                label = event[0]
            else:
                label = None
            if isinstance(label, str):
                labels.append(label)
    return str(bundle.get("dev_id", "unknown")), labels


@dataclass
class SequenceDetector:
    first: str
    second: str
    within_seconds: float
    first_seen_at: float | None = None

    def observe(self, labels: list[str], now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        normalized = {label.casefold() for label in labels}
        if self.first_seen_at is not None and now - self.first_seen_at > self.within_seconds:
            self.first_seen_at = None
        if self.first.casefold() in normalized:
            self.first_seen_at = now
        if self.first_seen_at is not None and self.second.casefold() in normalized:
            self.first_seen_at = None
            return True
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--topic", default=os.getenv("MQTT_TOPIC", "ucla/ce_mobile"))
    parser.add_argument("--username", default=os.getenv("MQTT_USERNAME"))
    parser.add_argument("--password", default=os.getenv("MQTT_PASSWORD"))
    parser.add_argument("--first", default=os.getenv("CE_FIRST_LABEL", "person"))
    parser.add_argument("--second", default=os.getenv("CE_SECOND_LABEL", "gunshot"))
    parser.add_argument("--within", type=float, default=float(os.getenv("CE_WITHIN_SECONDS", "30")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    detector = SequenceDetector(args.first, args.second, args.within)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if args.username:
        client.username_pw_set(args.username, args.password)

    def on_connect(client, _userdata, _flags, reason_code, _properties):
        if reason_code != 0:
            raise RuntimeError(f"MQTT connection failed: {reason_code}")
        print(f"Listening on {args.host}:{args.port}/{args.topic}")
        client.subscribe(args.topic)

    def on_message(_client, _userdata, message):
        try:
            device, labels = labels_from_payload(message.payload)
            if labels:
                print(json.dumps({"device": device, "labels": labels}))
            if detector.observe(labels):
                print(json.dumps({"complex_event": f"{args.first} -> {args.second}", "device": device}))
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            print(f"Ignored malformed message: {error}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
