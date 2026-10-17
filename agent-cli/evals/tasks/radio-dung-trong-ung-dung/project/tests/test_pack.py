"""Kiểm việc tự đọc lại của công cụ đóng gói."""

import unittest
from pack import decode, encode


class PackTests(unittest.TestCase):
    def test_roundtrip(self):
        songs = {"one": b"abc", "two": b"defgh"}
        self.assertEqual(decode(encode(songs)), songs)
