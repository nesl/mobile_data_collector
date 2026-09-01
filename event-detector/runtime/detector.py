#!/usr/bin/env python3
"""Run compiled complex events over bundled mobile YOLO and YAMNet results."""

from __future__ import annotations

import argparse
import json
import os
from urllib import error, request

from .fsm import Observation
from language import compile_event, load_event


class VisualizationClient:
    def __init__(self, base_url: str):
        self.url = base_url.rstrip("/") + "/api/update" if base_url else ""

    def update(self, data: dict) -> None:
        if not self.url:
            return
        body = json.dumps(data).encode()
        try:
            request.urlopen(request.Request(
                self.url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            ), timeout=0.25).close()
        except (error.URLError, TimeoutError):
            pass


def _pair(pair) -> tuple[str, float] | None:
    if isinstance(pair, dict):
        label, confidence = pair.get("first"), pair.get("second", 0)
    elif isinstance(pair, list) and pair:
        label, confidence = pair[0], pair[1] if len(pair) > 1 else 0
    else:
        return None
    if not isinstance(label, str):
        return None
    return label, float(confidence)


def observations_from_payload(payload: bytes, min_confidence: float = 0) -> list[Observation]:
    text = payload.decode("utf-8")
    if not text.startswith("detection::"):
        return []
    bundle = json.loads(text[len("detection::"):])
    device = str(bundle.get("dev_id", "unknown"))
    observations: list[Observation] = []

    for result in bundle.get("detectionResults", []):
        labels, scores, colors = [], [], []
        for box in result.get("bboxes", []):
            label = box.get("clsName")
            if isinstance(label, str) and float(box.get("cnf", 1)) >= min_confidence:
                labels.append(label)
                scores.append(float(box.get("cnf", 1)))
                color = box.get("color")
                if isinstance(color, str):
                    colors.append(color)
        observations.append(Observation(
            device=str(result.get("dev_id", device)),
            timestamp=float(result["timestamp"]) / 1000,
            modality="vision",
            labels=tuple(labels),
            scores=tuple(scores),
            colors=tuple(colors),
        ))

    for result in bundle.get("audioResults", []):
        labels, scores = [], []
        for raw_event in result.get("events", []):
            event = _pair(raw_event)
            if event is not None and event[1] >= min_confidence:
                labels.append(event[0])
                scores.append(event[1])
        observations.append(Observation(
            device=device,
            timestamp=float(result["timestamp"]) / 1000,
            modality="audio",
            labels=tuple(labels),
            scores=tuple(scores),
        ))

    return sorted(observations, key=lambda observation: observation.timestamp)


def labels_from_payload(payload: bytes) -> tuple[str, list[str]]:
    observations = observations_from_payload(payload)
    if not observations:
        return "unknown", []
    return observations[0].device, [label for item in observations for label in item.labels]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "definition",
        help="path to the YAML complex-event definition to parse and compile",
    )
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--topic", default=os.getenv("MQTT_TOPIC", "ucla/ce_mobile"))
    parser.add_argument("--username", default=os.getenv("MQTT_USERNAME"))
    parser.add_argument("--password", default=os.getenv("MQTT_PASSWORD"))
    parser.add_argument("--min-confidence", type=float, default=float(os.getenv("CE_MIN_CONFIDENCE", "0")))
    parser.add_argument("--visualization-url", default=os.getenv("CE_VISUALIZATION_URL", "http://localhost:5000"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    import paho.mqtt.client as mqtt

    detector = compile_event(load_event(args.definition))
    visualization = VisualizationClient(args.visualization_url)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if args.username:
        client.username_pw_set(args.username, args.password)

    def on_connect(client, _userdata, _flags, reason_code, _properties):
        if reason_code != 0:
            raise RuntimeError(f"MQTT connection failed: {reason_code}")
        print(
            f"Compiled {detector.complex_event_name} from {args.definition}; "
            f"listening on {args.host}:{args.port}/{args.topic}"
        )
        client.subscribe(args.topic)
        visualization.update({
            "topic": args.topic,
            "completed": False,
            "fsm": detector.status(),
            "observations": [],
        })

    def on_message(_client, _userdata, message):
        try:
            observations = observations_from_payload(message.payload, args.min_confidence)
            completed = False
            for observation in observations:
                print(json.dumps({
                    "device": observation.device,
                    "modality": observation.modality,
                    "labels": observation.labels,
                }))
                if detector.observe(observation):
                    completed = True
                    print(json.dumps({"complex_event": detector.complex_event_name, "device": observation.device}))
            if observations:
                visualization.update({
                    "topic": message.topic,
                    "completed": completed,
                    "fsm": detector.status(),
                    "observations": [
                        {
                            "device": item.device,
                            "timestamp": item.timestamp,
                            "modality": item.modality,
                            "labels": item.labels,
                            "scores": item.scores,
                        }
                        for item in observations
                    ],
                })
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            print(f"Ignored malformed message: {error}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, keepalive=60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("Detector stopped by user.")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
