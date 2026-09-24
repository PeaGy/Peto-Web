import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from inventory.cli import main


def run(*args):
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        code = main(["--file", "data/kho.json", *args])
    return code, out.getvalue()


class CliTest(unittest.TestCase):
    def test_find(self):
        code, output = run("find", "--code", "b-200")
        self.assertEqual(code, 0)
        self.assertIn("Vở 200 trang", output)

    def test_find_missing(self):
        self.assertEqual(run("find", "--code", "Z-1")[0], 1)

    def test_low(self):
        code, output = run("low", "--threshold", "5")
        self.assertEqual(code, 0)
        self.assertIn("Bút chì 2B", output)
        self.assertNotIn("Balo", output)


if __name__ == "__main__":
    unittest.main()
