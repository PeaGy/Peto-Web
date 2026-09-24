import json
import tempfile
import unittest
from pathlib import Path

from inventory import storage
from inventory.models import Item


class StorageTest(unittest.TestCase):
    def test_save_then_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "kho.json"
            items = [Item(sku="A-1", name="Bút", qty=3, price=5000)]
            storage.save(path, items)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["items"][0]["sku"], "A-1")
            self.assertEqual(storage.load(path), items)

    def test_sample_file(self):
        items = storage.load("data/kho.json")
        self.assertEqual(len(items), 5)
        self.assertEqual(items[0].sku, "A-100")


if __name__ == "__main__":
    unittest.main()
