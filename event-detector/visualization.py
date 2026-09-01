#!/usr/bin/env python3
"""Serve a small live dashboard for the mobile complex-event detector."""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HTML = Path(__file__).with_name("visualization.html").read_bytes()
lock = threading.Lock()
state = {"fsm": None, "messages": deque(maxlen=100), "completed_count": 0,
         "devices": {}, "registrations": {}, "last_update": None}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            self.wfile.write(HTML)
        elif self.path == "/api/state":
            with lock:
                self.send_json({
                    "fsm": state["fsm"],
                    "messages": list(state["messages"]),
                    "completed_count": state["completed_count"],
                    "devices": state["devices"],
                    "registrations": state["registrations"],
                    "last_update": state["last_update"],
                    "server_time": time.time(),
                })
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path not in ("/api/update", "/api/registry"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            update = json.loads(self.rfile.read(length))
            received_at = time.time()
            with lock:
                if self.path == "/api/registry":
                    state["registrations"][update["install_id"]] = update
                    self.send_json({"status": "ok"})
                    return
                state["last_update"] = received_at
                state["fsm"] = update.get("fsm")
                if update.get("completed"):
                    state["completed_count"] += 1
                for item in update.get("observations", []):
                    state["devices"][item.get("device", "unknown")] = received_at
                    state["messages"].append({
                        "topic": update.get("topic", ""),
                        "received_at": received_at,
                        **item,
                    })
            self.send_json({"status": "ok"})
        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_json({"status": "invalid request"}, 400)

    def log_message(self, format, *args):
        if args and str(args[1]) != "200":
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    print(f"Visualization available at http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
