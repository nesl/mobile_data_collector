import tempfile
import unittest

from registry import RegistryStore


class RegistryTests(unittest.TestCase):
    def test_assignments_are_stable_and_unique(self):
        with tempfile.NamedTemporaryFile() as database:
            store = RegistryStore(database.name)
            self.assertEqual(store.assign("a"), "phone-1")
            self.assertEqual(store.assign("a"), "phone-1")
            self.assertEqual(store.assign("b", "outside"), "outside")
            self.assertEqual(store.assign("c", "outside"), "outside-2")

    def test_preferred_id_is_sanitized(self):
        with tempfile.NamedTemporaryFile() as database:
            store = RegistryStore(database.name)
            self.assertEqual(store.assign("a", "Room One!"), "Room-One-")


if __name__ == "__main__":
    unittest.main()
