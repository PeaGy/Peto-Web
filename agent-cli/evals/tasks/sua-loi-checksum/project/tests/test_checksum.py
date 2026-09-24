import unittest

from savetool.checksum import MAGIC_XOR, checksum


class ChecksumTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(checksum(b""), MAGIC_XOR)

    def test_matches_readme(self):
        # Theo README: tổng mọi byte rồi XOR 0x5A5A5A5A.
        self.assertEqual(checksum(b"SAV1"), (0x53 + 0x41 + 0x56 + 0x31) ^ 0x5A5A5A5A)


if __name__ == "__main__":
    unittest.main()
