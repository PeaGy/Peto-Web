import unittest

from savetool.format import SaveError, pack, unpack

# File save thật của game, chép từ máy người chơi: {"gold":100}
REAL_SAVE = bytes.fromhex("534156310c0000007b22676f6c64223a3130307d8e5e5a5a")


class FormatTest(unittest.TestCase):
    def test_round_trip(self):
        data = {"gold": 5, "name": "Peto"}
        self.assertEqual(unpack(pack(data)), data)

    def test_reads_real_game_save(self):
        self.assertEqual(unpack(REAL_SAVE), {"gold": 100})

    def test_rejects_tampered_file(self):
        raw = bytearray(pack({"gold": 5}))
        raw[10] ^= 1
        with self.assertRaises(SaveError):
            unpack(bytes(raw))


if __name__ == "__main__":
    unittest.main()
