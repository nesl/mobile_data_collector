"""MongoDB event-history storage shared by the detector and history API."""

from __future__ import annotations

import time
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError


class MongoStore:
    """Persist detector updates while allowing the live service to run offline."""

    def __init__(self, uri: str, database: str, collection: str):
        self.uri = uri
        self.database = database
        self.collection_name = collection
        self.client: MongoClient | None = None
        self.collection: Any = None
        self.last_connect_attempt = 0.0
        self.last_error = ""

    def _connect(self) -> bool:
        if self.collection is not None:
            return True
        now = time.monotonic()
        if now - self.last_connect_attempt < 5:
            return False
        self.last_connect_attempt = now
        try:
            client = MongoClient(self.uri, serverSelectionTimeoutMS=1000)
            client.admin.command("ping")
            collection = client[self.database][self.collection_name]
            collection.create_index([("session", ASCENDING), ("received_at", DESCENDING)])
            collection.create_index([("kind", ASCENDING), ("received_at", DESCENDING)])
            self.client, self.collection = client, collection
            self.last_error = ""
            return True
        except PyMongoError as error:
            self.last_error = str(error)
            return False

    def save(self, kind: str, payload: dict, received_at: float) -> bool:
        if not self._connect():
            return False
        document = {**payload, "kind": kind, "received_at": received_at}
        document.setdefault("session", "default")
        try:
            self.collection.insert_one(document)
            return True
        except PyMongoError as error:
            self.last_error = str(error)
            self.collection = None
            return False

    def history(self, session: str, limit: int = 100) -> list[dict]:
        if not self._connect():
            return []
        query = {"session": session} if session else {}
        try:
            return list(self.collection.find(
                query, {"_id": 0}, sort=[("received_at", DESCENDING)], limit=limit
            ))
        except PyMongoError as error:
            self.last_error = str(error)
            self.collection = None
            return []

    @property
    def available(self) -> bool:
        return self.collection is not None
