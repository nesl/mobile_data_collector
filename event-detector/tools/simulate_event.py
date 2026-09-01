#!/usr/bin/env python3
"""Publish a mobile-format event sequence for testing the detector and UI."""

import argparse
import json
import time

import paho.mqtt.client as mqtt

from language import event_names, load_catalog, load_event


def vision(device, timestamp, *labels):
    return device, {"dev_id": device, "detectionResults": [{
        "dev_id": device, "timestamp": int(timestamp * 1000),
        "bboxes": [{"clsName": label, "cnf": 0.9} for label in labels],
    }], "audioResults": []}


def audio(device, timestamp, label):
    return device, {"dev_id": device, "detectionResults": [], "audioResults": [{
        "timestamp": int(timestamp * 1000),
        "events": [{"first": label, "second": 0.9}],
    }]}


def sequence(name, devices):
    now = time.time()
    outside = devices.get("OUTSIDE", "outside_phone")
    building = devices.get("BUILDING", "building_phone")
    if name == "gunshot":
        return [audio(building, now, "Gunshot, gunfire")]
    if name == "car_gunshot_person":
        return [vision(outside, now, "car"),
                audio(building, now + 1, "Gunshot, gunfire"),
                vision(outside, now + 2, "person")]
    if name == "iobt_ce1":
        return [vision(outside, now, "car", "car", "car", "car"),
                vision(outside, now + 1, "truck"), vision(outside, now + 2),
                vision(outside, now + 6)]
    if name == "iobt_ce2":
        events = []
        for offset in (0, 9, 18):
            events += [vision(outside, now + offset, "car"),
                       vision(outside, now + offset + 3, "car"),
                       vision(outside, now + offset + 4),
                       vision(outside, now + offset + 8)]
        return events
    return [vision(outside, now, "car"), vision(outside, now + 1, "person"),
            vision(building, now + 2, "person"),
            audio(building, now + 3, "Gunshot, gunfire"),
            vision(outside, now + 4, "person"), vision(outside, now + 5),
            vision(outside, now + 9)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--topic", default="ucla/ce_mobile")
    parser.add_argument("--event", choices=event_names(), default="iobt_ce3")
    args = parser.parse_args()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(args.host, args.port, 30)
    client.loop_start()
    definition = load_event(load_catalog()[args.event])
    for device, body in sequence(args.event, definition.devices):
        client.publish(args.topic, "detection::" + json.dumps(body), qos=1).wait_for_publish()
        print(f"Published {args.event} observation from {device}")
        time.sleep(0.2)
    client.disconnect()
    client.loop_stop()


if __name__ == "__main__":
    main()
