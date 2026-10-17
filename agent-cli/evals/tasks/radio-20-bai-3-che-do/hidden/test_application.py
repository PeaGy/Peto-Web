"""Kiểm kết quả bằng bộ đọc độc lập, nguồn PCM và metadata ban đầu."""

import hashlib
import json
import subprocess
import sys
import unittest
import wave
from pathlib import Path
import player

ROOT = Path(__file__).resolve().parents[1]


class ApplicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run([sys.executable, "build.py"], cwd=ROOT, capture_output=True, timeout=40)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", "replace"))

    def test_all_modes_match_all_sources(self):
        expected = {}
        for source in sorted((ROOT / "custom").glob("*.wav")):
            with wave.open(str(source), "rb") as wav:
                pcm = wav.readframes(wav.getnframes())
                expected[source.stem] = (hashlib.sha256(pcm).hexdigest(), wav.getframerate(),
                                         wav.getnchannels(), wav.getnframes())
        self.assertEqual(len(expected), 20)
        for mode in ("base", "lost", "ballad"):
            with self.subTest(mode=mode):
                rows = player.play(mode)
                self.assertEqual([row["station"] for row in rows], [f"station-{n:02}" for n in range(1, 24)])
                self.assertEqual({row["clip"] for row in rows}, set(expected))
                for row in rows:
                    self.assertEqual((row["sha256"], row["rate"], row["channels"], row["frames"]), expected[row["clip"]])

    def test_preserved_metadata(self):
        for mode in ("base", "lost", "ballad"):
            d = json.loads((ROOT / f"game/{mode}/catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(set(d), {"version", "advertising", "news", "missions", "stations"})
            self.assertEqual(d["version"], 2)
            self.assertEqual(d["advertising"], ["ad-001", "ad-002"])
            self.assertEqual(d["news"], {"enabled": True})
            self.assertEqual(d["missions"], {"phone": "speech-801", "intro": "scene-109"})
            self.assertEqual(len(d["stations"]), 23)
            for index, s in enumerate(d["stations"]):
                self.assertEqual(s["id"], f"station-{index + 1:02}")
                self.assertEqual(s["kind"], "talk" if index in (5, 12, 20) else "music")
                self.assertEqual(s["gain"], round(.6 + index * .01, 2))
                self.assertEqual(len(s["playlist"]), 1)

    def test_rebuild_is_identical(self):
        def snapshot():
            return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (ROOT / "game").rglob("*") if p.is_file()}
        before = snapshot()
        result = subprocess.run([sys.executable, "build.py"], cwd=ROOT, capture_output=True, timeout=40)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(snapshot(), before)

    def test_reference_vector_and_roundtrip(self):
        from pack import encode, decode
        for source in sorted((ROOT / "custom").glob("*.wav")):
            with wave.open(str(source), "rb") as wav:
                pcm, rate, channels = wav.readframes(wav.getnframes()), wav.getframerate(), wav.getnchannels()
            encoded = encode(pcm, rate, channels)
            self.assertEqual(decode(encoded), (pcm, rate, channels))
        reference = player.read_clip(ROOT / "references/stock.rdx")
        with wave.open(str(ROOT / "references/stock.wav"), "rb") as wav:
            self.assertEqual(reference["sha256"], hashlib.sha256(wav.readframes(wav.getnframes())).hexdigest())
