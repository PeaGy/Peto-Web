import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from inventory import report, search, storage
from inventory.cli import main
from inventory.models import Item

OLD = {"items": [{"sku": "A-1", "name": "Bút", "qty": 2, "price": 3000}]}
NEW = {"items": [{"product_code": "A-1", "name": "Bút", "qty": 2, "price": 3000}]}


class Renamed(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.dir = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def write(self, name, data):
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_item_field(self):
        item = Item(product_code="A-1", name="Bút", qty=2, price=3000)
        self.assertEqual(item.product_code, "A-1")
        self.assertFalse(hasattr(item, "sku"))
        self.assertEqual(item.value, 6000)

    def test_load_old_and_new_files(self):
        old = storage.load(self.write("old.json", OLD))
        new = storage.load(self.write("new.json", NEW))
        self.assertEqual(old, new)
        self.assertEqual(old[0].product_code, "A-1")

    def test_save_uses_new_key(self):
        path = self.dir / "kho.json"
        storage.save(path, [Item(product_code="B-2", name="Vở", qty=1, price=18000)])
        row = json.loads(path.read_text(encoding="utf-8"))["items"][0]
        self.assertEqual(row.get("product_code"), "B-2")
        self.assertNotIn("sku", row)

    def test_find_by_code(self):
        items = [Item(product_code="A-1", name="Bút", qty=2, price=3000),
                 Item(product_code="B-2", name="Vở", qty=1, price=18000)]
        self.assertEqual(search.find_by_code(items, " b-2 ").name, "Vở")
        self.assertIsNone(search.find_by_code(items, "Z-9"))

    def test_report_shows_codes(self):
        items = [Item(product_code="A-1", name="Bút", qty=2, price=3000)]
        self.assertIn("A-1", report.format_table(items))
        self.assertEqual(report.low_stock(items, 5), items)

    def test_cli_find_code(self):
        path = self.write("kho.json", NEW)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = main(["--file", str(path), "find", "--code", "a-1"])
        self.assertEqual(code, 0)
        self.assertIn("Bút", out.getvalue())
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--file", str(path), "find", "--code", "Z-9"]), 1)

    def test_cli_reads_old_file(self):
        path = self.write("cu.json", OLD)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = main(["--file", str(path), "list"])
        self.assertEqual(code, 0)
        self.assertIn("A-1", out.getvalue())


if __name__ == "__main__":
    unittest.main()
