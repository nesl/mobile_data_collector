#!/usr/bin/env python3
"""Start and stop a mobile collection session over MQTT."""

from __future__ import annotations

import argparse
import os
import time

import paho.mqtt.client as mqtt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "stop"))
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--topic", default=os.getenv("MQTT_CONTROL_TOPIC", "ucla/ce_controller"))
    parser.add_argument("--session", default="local")
    parser.add_argument("--username", default=os.getenv("MQTT_USERNAME"))
    parser.add_argument("--password", default=os.getenv("MQTT_PASSWORD"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if args.username:
        client.username_pw_set(args.username, args.password)
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()
    if args.command == "start":
        handshake = f"handshake:{int(time.time() * 1000)}:{args.session}"
        client.publish(args.topic, handshake, qos=1).wait_for_publish()
        # Preserve ordering while allowing the phone to process the handshake.
        time.sleep(0.5)
        client.publish(args.topic, "start_record", qos=1).wait_for_publish()
    else:
        client.publish(args.topic, "end_record", qos=1).wait_for_publish()
    client.disconnect()
    client.loop_stop()


if __name__ == "__main__":
    main()
