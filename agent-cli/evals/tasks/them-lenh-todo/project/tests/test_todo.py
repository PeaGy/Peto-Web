import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import todo


def run(*args, file):
    out = io.StringIO()
    with redirect_stdout(out):
        code = todo.main(["--file", str(file), *args])
    return code, out.getvalue()


class TodoTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.file = Path(self.folder.name) / "todo.json"

    def tearDown(self):
        self.folder.cleanup()

    def test_add_and_list(self):
        run("add", "Mua sữa", file=self.file)
        run("add", "Học bài", file=self.file)
        code, output = run("list", file=self.file)
        self.assertEqual(code, 0)
        self.assertEqual(output.splitlines(), ["[ ] 1. Mua sữa", "[ ] 2. Học bài"])

    def test_empty_list(self):
        self.assertEqual(run("list", file=self.file)[1].strip(), "Chưa có việc nào.")


if __name__ == "__main__":
    unittest.main()
