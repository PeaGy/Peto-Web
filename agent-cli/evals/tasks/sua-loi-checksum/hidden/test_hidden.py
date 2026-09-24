import json
import struct
import unittest

from savetool.checksum import checksum
from savetool.format import SaveError, pack, unpack


def reference(data: bytes) -> int:
    return (sum(data) & 0xFFFFFFFF) ^ 0x5A5A5A5A


def real_save(data: dict) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = b"SAV1" + struct.pack("<I", len(payload)) + payload
    return body + struct.pack("<I", reference(body))


class HiddenChecksum(unittest.TestCase):
    def test_values(self):
        for data in [b"", b"\x00", b"\xff", b"SAV1", bytes(range(256)), b"\x01\x02\x03\x04\x05"]:
            self.assertEqual(checksum(data), reference(data), data[:8])

    def test_last_byte_counts(self):
        self.assertNotEqual(checksum(b"ab"), checksum(b"ac"))

    def test_real_saves(self):
        for data in [{"gold": 100}, {"gold": 0, "name": "Tí", "items": [1, 2]}]:
            self.assertEqual(unpack(real_save(data)), data)

    def test_tampered_last_payload_byte(self):
        raw = bytearray(pack({"gold": 7}))
        raw[-5] ^= 1
        with self.assertRaises(SaveError):
            unpack(bytes(raw))

    def test_round_trip(self):
        data = {"gold": 5, "name": "Peto", "level": 12}
        self.assertEqual(unpack(pack(data)), data)
        self.assertEqual(pack(data), real_save(data))


if __name__ == "__main__":
    unittest.main()
