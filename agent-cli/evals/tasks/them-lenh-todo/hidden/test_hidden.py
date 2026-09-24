import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import todo


class DoneAndPending(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.file = Path(self.folder.name) / "todo.json"

    def tearDown(self):
        self.folder.cleanup()

    def run_cli(self, *args):
        out = io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(out):
                code = todo.main(["--file", str(self.file), *args])
        except SystemExit as exit:
            code = exit.code if isinstance(exit.code, int) else 1
        return code or 0, out.getvalue()

    def items(self):
        return json.loads(self.file.read_text(encoding="utf-8"))

    def test_done_marks_item(self):
        self.run_cli("add", "A")
        self.run_cli("add", "B")
        code, _ = self.run_cli("done", "1")
        self.assertEqual(code, 0)
        self.assertEqual([item["done"] for item in self.items()], [True, False])
        self.assertEqual(self.run_cli("list")[1].splitlines(), ["[x] 1. A", "[ ] 2. B"])

    def test_list_pending_only(self):
        for title in ("A", "B", "C"):
            self.run_cli("add", title)
        self.run_cli("done", "2")
        self.assertEqual(self.run_cli("list", "--chua-xong")[1].splitlines(), ["[ ] 1. A", "[ ] 3. C"])

    def test_done_unknown_id(self):
        self.run_cli("add", "A")
        before = self.file.read_text(encoding="utf-8")
        code, output = self.run_cli("done", "99")
        self.assertEqual(code, 1)
        self.assertIn("99", output)
        self.assertEqual(self.file.read_text(encoding="utf-8"), before)

    def test_plain_list_still_shows_everything(self):
        self.run_cli("add", "Mua sữa")
        self.run_cli("add", "Học bài")
        self.run_cli("done", "2")
        code, output = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertEqual(output.splitlines(), ["[ ] 1. Mua sữa", "[x] 2. Học bài"])

    def test_empty_list_message_unchanged(self):
        self.assertEqual(self.run_cli("list")[1].strip(), "Chưa có việc nào.")


if __name__ == "__main__":
    unittest.main()
