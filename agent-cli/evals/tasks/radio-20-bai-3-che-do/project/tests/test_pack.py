"""Test nhanh có sẵn của công cụ build."""

import struct
import unittest
from pack import encode, decode


class PackTest(unittest.TestCase):
    def test_roundtrip(self):
        for channels in (1, 2):
            pcm = struct.pack("<" + "h" * 203 * channels, *range(203 * channels))
            self.assertEqual(decode(encode(pcm, 11025, channels)), (pcm, 11025, channels))
