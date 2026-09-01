import unittest
from unittest.mock import MagicMock

from services.persistence import MongoStore


class PersistenceTests(unittest.TestCase):
    def test_save_adds_kind_session_and_receipt_time(self):
        store = MongoStore("mongodb://unused", "iobt_db", "history")
        store.collection = MagicMock()
        self.assertTrue(store.save("detector_update", {"session": "demo", "topic": "events"}, 123.5))
        store.collection.insert_one.assert_called_once_with({
            "session": "demo", "topic": "events", "kind": "detector_update", "received_at": 123.5,
        })

    def test_save_uses_default_session(self):
        store = MongoStore("mongodb://unused", "iobt_db", "history")
        store.collection = MagicMock()
        store.save("registration", {"device_id": "phone-1"}, 10)
        document = store.collection.insert_one.call_args.args[0]
        self.assertEqual(document["session"], "default")

    def test_history_is_bounded_and_excludes_mongo_id(self):
        store = MongoStore("mongodb://unused", "iobt_db", "history")
        store.collection = MagicMock()
        store.collection.find.return_value = iter([{"session": "demo"}])
        self.assertEqual(store.history("demo", 25), [{"session": "demo"}])
        store.collection.find.assert_called_once_with(
            {"session": "demo"}, {"_id": 0}, sort=[("received_at", -1)], limit=25
        )


if __name__ == "__main__":
    unittest.main()
