import os
import tempfile
import unittest

from inventory import store


class StoreTest(unittest.TestCase):
    def test_add_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "db.json")
            store.add_item(db, "A1", "Widget", 3, 2.5)
            self.assertEqual(store.load(db)[0]["sku"], "A1")

    def test_duplicate_sku(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "db.json")
            store.add_item(db, "A1", "Widget", 3, 2.5)
            with self.assertRaises(ValueError):
                store.add_item(db, "A1", "Other", 1, 1.0)


if __name__ == "__main__":
    unittest.main()
