#!/usr/bin/env python3
"""Serve the live dashboard for the mobile complex-event detector."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .persistence import MongoStore


HTML = Path(__file__).with_name("visualization.html").read_bytes()
lock = threading.Lock()
state = {"fsm": None, "messages": deque(maxlen=100), "completed_count": 0,
         "devices": {}, "registrations": {}, "last_update": None, "session": None}
store: MongoStore | None = None


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            self.wfile.write(HTML)
        elif parsed.path == "/api/state":
            with lock:
                self.send_json({
                    "fsm": state["fsm"],
                    "messages": list(state["messages"]),
                    "completed_count": state["completed_count"],
                    "devices": state["devices"],
                    "registrations": state["registrations"],
                    "last_update": state["last_update"],
                    "session": state["session"],
                    "server_time": time.time(),
                    "persistence": {
                        "enabled": store is not None,
                        "available": bool(store and store.available),
                        "error": store.last_error if store else "",
                    },
                })
        elif parsed.path == "/api/history":
            if store is None:
                self.send_json({"status": "persistence disabled", "items": []}, 503)
                return
            query = parse_qs(parsed.query)
            session = query.get("session", [""])[0][:100]
            try:
                limit = min(max(int(query.get("limit", ["100"])[0]), 1), 500)
            except ValueError:
                self.send_json({"status": "invalid limit"}, 400)
                return
            self.send_json({"session": session, "items": store.history(session, limit)})
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
                state["session"] = update.get("session", "default")
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
    global store
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    mongo_uri = os.getenv("MONGODB_URI", "")
    if mongo_uri:
        store = MongoStore(
            mongo_uri,
            os.getenv("MONGODB_DATABASE", "iobt_db"),
            os.getenv("MONGODB_COLLECTION", "event_history"),
        )
        if store._connect():
            print("MongoDB history reader connected.")
        else:
            print(f"MongoDB unavailable; live mode will continue and retry: {store.last_error}")
    print(f"Visualization available at http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
